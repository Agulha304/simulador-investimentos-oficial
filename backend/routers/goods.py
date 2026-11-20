"""Bens e patrimônio: mercado simulado, compra/venda, imóveis (moradia e aluguel), custos e financiamentos."""
from decimal import Decimal

from fastapi import APIRouter, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.dependencies import CurrentUser, DbSession
from backend.models import (
    Good, GoodCategory, GoodCost, GoodEvent, GoodStatus, GoodValue, InstallmentStatus, LedgerEntry, Loan,
    LoanInstallment, Occupancy, RealEstateDetails, RecurringItem, ShortStayMonth, VehicleDetails,
)
from backend.routers.budget import _run
from backend.schemas import goods as s
from backend.services import budget_service as bs
from backend.services import goods_rules as rules
from backend.services import economy_service, short_stay
from backend.services import goods_service as gs
from backend.services import finance_ledger, wealth_service
from backend.services.finance_ledger import FinanceError, NotFoundError

router = APIRouter(prefix="/goods", tags=["goods"])


# ------------------------------------------------------------------ montagem de respostas

def _listing_out(db, listing, price, owned) -> s.ListingOut:
    t = rules.FINANCING.get(listing.category)
    fee, parts = rules.purchase_fee(listing.category, price, listing.location)
    breakdown = [{"name": n, "rate_pct": str(r), "amount": str(a)} for n, r, a in parts]
    rent = rules.market_rent(listing.category, price) if listing.category in (GoodCategory.RESIDENTIAL, GoodCategory.COMMERCIAL) else None
    return s.ListingOut(
        key=listing.key, category=listing.category, name=listing.name, description=listing.description, price=price,
        purchase_fee=fee, fee_breakdown=breakdown, location=listing.location, condition=listing.condition, property_type=listing.property_type,
        address=listing.address, area_m2=listing.area_m2, bedrooms=listing.bedrooms, suggested_rent=rent, owned=owned,
        financing=s.FinancingOut(max_ltv_pct=t.max_ltv_pct, min_down_payment=quantize_money(price * (100 - t.max_ltv_pct) / 100),
                                 annual_rate_pct=t.annual_rate_pct, max_term_months=t.max_term_months) if t else None)


def _good_out(db: Session, g: Good) -> s.GoodOut:
    det = db.get(RealEstateDetails, g.id)
    loan = db.scalar(select(Loan).where(Loan.good_id == g.id))
    return s.GoodOut(
        id=g.id, name=g.name, category=g.category, status=g.status, condition=g.condition, location=g.location,
        acquired_on=g.acquired_on, purchase_price=g.purchase_price, acquisition_cost=g.acquisition_cost,
        current_value=g.current_value, unrealized_result=quantize_money(g.current_value - g.acquisition_cost)
        if g.status == GoodStatus.ACTIVE else Decimal("0.00"),
        occupancy=det.occupancy if det else None, monthly_rent=det.monthly_rent if det else None,
        loan_balance=loan.balance if loan else None, sold_on=g.sold_on, sale_result=g.sale_result)


def _inst_out(i: LoanInstallment) -> s.InstallmentOut:
    return s.InstallmentOut(number=i.number, due_month=i.due_month, payment=i.payment, interest=i.interest,
                            amortization=i.amortization, balance_after=i.balance_after, status=i.status)


def _detail(db: Session, user_id: int, g: Good) -> s.GoodDetailOut:
    det = db.get(RealEstateDetails, g.id)
    veh = db.get(VehicleDetails, g.id)
    loan = db.scalar(select(Loan).where(Loan.good_id == g.id))
    loan_out = None
    prefix = [f"good:{g.id}:%"]
    if loan:
        insts = list(db.scalars(select(LoanInstallment).where(LoanInstallment.loan_id == loan.id).order_by(LoanInstallment.number)))
        pending = next((i for i in insts if i.status == InstallmentStatus.PENDING), None)
        loan_out = s.LoanOut(
            principal=loan.principal, down_payment=loan.down_payment, annual_rate_pct=loan.annual_rate_pct,
            term_months=loan.term_months, system=loan.system, start_month=loan.start_month, end_month=loan.end_month,
            balance=loan.balance, status=loan.status, paid_installments=sum(1 for i in insts if i.status == InstallmentStatus.PAID),
            next_payment=pending.payment if pending else None, installments=[_inst_out(i) for i in insts])
        prefix.append(f"loan:{loan.id}:%")
    entries = list(db.scalars(select(LedgerEntry).where(
        LedgerEntry.user_id == user_id, or_(*[LedgerEntry.origin_ref.like(p) for p in prefix])).order_by(LedgerEntry.id.desc())))
    income = sum((e.amount for e in entries if e.kind.value == "INCOME" and not e.capital), Decimal("0.00"))
    expense = sum((e.amount for e in entries if e.kind.value == "EXPENSE" and not e.capital), Decimal("0.00"))
    return s.GoodDetailOut(
        good=_good_out(db, g), description=g.description,
        real_estate=s.RealEstateOut(
            property_type=det.property_type, address=det.address, area_m2=det.area_m2, bedrooms=det.bedrooms,
            occupancy=det.occupancy, monthly_rent=det.monthly_rent, rent_tax_pct=det.rent_tax_pct,
            market_rent=rules.market_rent(g.category, g.current_value),
            market_nightly=rules.market_nightly(g.category, g.current_value) if g.category == GoodCategory.RESIDENTIAL else None,
            nightly_rate=det.nightly_rate, management=det.management, str_rating=det.str_rating,
            management_hours=short_stay.STR_HOURS if det.occupancy == Occupancy.SHORT_STAY and det.management == "SELF" else 0,
            stay_months=[{"month": r.ref_month.isoformat(), "nights": r.nights, "occupancy_pct": str(r.occupancy_pct), "gross": str(r.gross),
                          "net": str(r.gross - r.platform_fee - r.manager_fee - r.cleaning - r.iss), "note": r.note}
                         for r in db.scalars(select(ShortStayMonth).where(ShortStayMonth.good_id == g.id).order_by(ShortStayMonth.ref_month.desc()).limit(12))]) if det else None,
        vehicle_usage_km_month=veh.usage_km_month if veh else None,
        costs=[s.CostOut(id=c.id, kind=c.kind, name=c.name, amount=c.amount, frequency=c.frequency,
                         start_month=c.start_month, active=c.active)
               for c in db.scalars(select(GoodCost).where(GoodCost.good_id == g.id).order_by(GoodCost.id))],
        values=[s.ValueOut(ref_month=v.ref_month, value=v.value, source=v.source)
                for v in db.scalars(select(GoodValue).where(GoodValue.good_id == g.id).order_by(GoodValue.ref_month, GoodValue.id))],
        events=[s.EventOut(ref_month=e.ref_month, type=e.type, description=e.description, amount=e.amount, created_at=e.created_at)
                for e in db.scalars(select(GoodEvent).where(GoodEvent.good_id == g.id).order_by(GoodEvent.id.desc()))],
        loan=loan_out,
        entries=[s.GoodEntryOut(id=e.id, kind=e.kind.value, amount=e.amount, description=e.description,
                                ref_month=e.ref_month, capital=e.capital, origin=e.origin.value) for e in entries],
        income_total=income, expense_total=expense,
        appraisal=s.AppraisalOut(**gs.appraise(db, g)) if g.status == GoodStatus.ACTIVE
        else s.AppraisalOut(estimate=Decimal("0.00"), low=Decimal("0.00"), high=Decimal("0.00"), uncertainty_pct=Decimal("0")))


# ------------------------------------------------------------------ visão geral e mercado

@router.get("/overview", response_model=s.WealthOverviewOut)
def overview(user: CurrentUser, db: DbSession):
    def go():
        bs.ensure_setup(db, user.id)
        return wealth_service.overview(db, user.id)
    return _run(db, go)


@router.get("/market", response_model=list[s.ListingOut])
def market(user: CurrentUser, db: DbSession, category: GoodCategory | None = None, q: str | None = Query(None, max_length=60),
           min_price: Decimal | None = Query(None, ge=0), max_price: Decimal | None = Query(None, ge=0)):
    def go():
        month = bs.ensure_setup(db, user.id)
        return [_listing_out(db, l, p, owned) for l, p, owned in gs.listings_for_user(
            db, user.id, month.ref_month, category=category, q=q, min_price=min_price, max_price=max_price)]
    return _run(db, go)


@router.post("/market/simulate", response_model=s.SimulationOut)
def simulate(body: s.SimulateIn, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        listing = rules.CATALOG_BY_KEY.get(body.listing_key)
        if listing is None:
            raise NotFoundError("anúncio não encontrado")
        price = gs.market_price(listing, month.ref_month, gs.load_rules(db))
        rate, rows = gs.simulate_financing(listing.category, price, body.down_payment, body.term_months, body.system, body.annual_rate_pct,
                                      economy_service.financing_rate_add(db, user.id, month.ref_month))
        fee, _parts = rules.purchase_fee(listing.category, price, listing.location)
        down = quantize_money(body.down_payment)
        return s.SimulationOut(
            price=price, down_payment=down, financed=price - down, annual_rate_pct=rate, first_payment=rows[0].payment,
            last_payment=rows[-1].payment, total_interest=sum((r.interest for r in rows), Decimal("0.00")),
            total_paid=sum((r.payment for r in rows), Decimal("0.00")) + down, purchase_fee=fee, cash_needed_now=down + fee,
            preview=[s.InstallmentOut(number=r.number, due_month=bs.shift_month(month.ref_month, r.number), payment=r.payment,
                                      interest=r.interest, amortization=r.amortization, balance_after=r.balance_after)
                     for r in rows[:6]])
    return _run(db, go)


@router.post("/purchase", response_model=s.GoodDetailOut, status_code=status.HTTP_201_CREATED)
def purchase(body: s.PurchaseIn, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        g = gs.purchase(db, user.id, month, listing_key=body.listing_key, purchase_key=body.idempotency_key,
                        financed=body.financed, down_payment=body.down_payment, term_months=body.term_months,
                        system=body.system, annual_rate_pct=body.annual_rate_pct, extra_costs=body.extra_costs,
                        usage_km_month=body.usage_km_month)
        return _detail(db, user.id, g)
    return _run(db, go)


# ------------------------------------------------------------------ meus bens

@router.get("", response_model=list[s.GoodOut])
def my_goods(user: CurrentUser, db: DbSession, category: GoodCategory | None = None, status_: GoodStatus | None = Query(None, alias="status")):
    def go():
        bs.ensure_setup(db, user.id)
        personal = finance_ledger.personal_account(db, user.id)
        q = select(Good).where(Good.user_id == user.id, Good.owner_account_id == personal.id).order_by(Good.id.desc())
        if category:
            q = q.where(Good.category == category)
        if status_:
            q = q.where(Good.status == status_)
        return [_good_out(db, g) for g in db.scalars(q)]
    return _run(db, go)


@router.get("/housing-candidates", response_model=list[s.HousingCandidateOut])
def housing_candidates(user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        out = []
        for r in gs.housing_candidates(db, user.id):
            out.append(s.HousingCandidateOut(id=r.id, name=r.name, amount=bs.version_amount(db, r.id, month.ref_month)))
        return out
    return _run(db, go)


@router.get("/{good_id}", response_model=s.GoodDetailOut)
def detail(good_id: int, user: CurrentUser, db: DbSession):
    def go():
        bs.ensure_setup(db, user.id)
        return _detail(db, user.id, gs.get_good(db, user.id, good_id))
    return _run(db, go)


@router.patch("/{good_id}", response_model=s.GoodDetailOut)
def patch_good(good_id: int, body: s.GoodPatch, user: CurrentUser, db: DbSession):
    def go():
        bs.ensure_setup(db, user.id)
        g = gs.get_good(db, user.id, good_id)
        if body.name is not None:
            g.name = body.name.strip()
        if body.description is not None:
            g.description = body.description
        if body.location is not None:
            g.location = body.location
        if body.condition is not None:
            g.condition = body.condition
        db.flush()
        return _detail(db, user.id, g)
    return _run(db, go)


@router.get("/{good_id}/sale-quote", response_model=s.SaleQuoteOut)
def sale_quote(good_id: int, user: CurrentUser, db: DbSession, sale_price: Decimal | None = Query(None, gt=0),
               extra_fees: Decimal = Query(Decimal("0"), ge=0)):
    def go():
        bs.ensure_setup(db, user.id)
        return gs.sale_quote(db, gs.get_good(db, user.id, good_id), sale_price, extra_fees)
    return _run(db, go)


@router.post("/{good_id}/sell", response_model=s.GoodDetailOut)
def sell(good_id: int, body: s.SaleIn, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        return _detail(db, user.id, gs.sell(db, user.id, month, good_id, sale_price=body.sale_price, extra_fees=body.extra_fees))
    return _run(db, go)


@router.post("/{good_id}/write-off", response_model=s.GoodDetailOut)
def write_off(good_id: int, body: s.WriteOffIn, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        return _detail(db, user.id, gs.write_off(db, user.id, month, good_id, body.reason))
    return _run(db, go)


@router.post("/{good_id}/occupancy", response_model=s.GoodDetailOut)
def occupancy(good_id: int, body: s.OccupancyIn, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        g = gs.set_occupancy(db, user.id, month, good_id, body.mode, monthly_rent=body.monthly_rent,
                             end_recurring_item_ids=tuple(body.end_recurring_item_ids), nightly_rate=body.nightly_rate,
                             management=body.management)
        return _detail(db, user.id, g)
    return _run(db, go)


@router.post("/{good_id}/maintenance", response_model=s.GoodDetailOut, status_code=status.HTTP_201_CREATED)
def maintenance(good_id: int, body: s.MaintenanceIn, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        gs.register_maintenance(db, user.id, month, good_id, body.amount, body.description, body.idempotency_key)
        return _detail(db, user.id, gs.get_good(db, user.id, good_id))
    return _run(db, go)


@router.post("/{good_id}/costs", response_model=s.GoodDetailOut, status_code=status.HTTP_201_CREATED)
def add_cost(good_id: int, body: s.CostIn, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        gs.add_cost(db, user.id, month, good_id, kind=body.kind, name=body.name, amount=body.amount, frequency=body.frequency)
        return _detail(db, user.id, gs.get_good(db, user.id, good_id))
    return _run(db, go)


@router.patch("/{good_id}/costs/{cost_id}", response_model=s.GoodDetailOut)
def update_cost(good_id: int, cost_id: int, body: s.CostPatch, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        gs.update_cost(db, user.id, month, good_id, cost_id, amount=body.amount, active=body.active, frequency=body.frequency)
        return _detail(db, user.id, gs.get_good(db, user.id, good_id))
    return _run(db, go)


@router.get("/taxes/summary")
def taxes(user: CurrentUser, db: DbSession):
    """Impostos já pagos sobre os seus bens, por tipo (ITBI, IPTU, IPVA, IR sobre aluguel, ISS, ganho de capital...)."""
    def go():
        from backend.models import BudgetCategory
        names = {c.id: c.name for c in db.scalars(select(BudgetCategory).where(BudgetCategory.user_id == user.id))}
        cost_kind = {c.id: c.kind for c in db.scalars(select(GoodCost).join(Good, Good.id == GoodCost.good_id).where(Good.user_id == user.id))}
        label = {"IPTU": "IPTU", "IPVA": "IPVA", "LICENSING": "Licenciamento do veículo"}
        by: dict[str, Decimal] = {}
        for e in db.scalars(select(LedgerEntry).where(LedgerEntry.user_id == user.id, LedgerEntry.kind == "EXPENSE",
                                                        LedgerEntry.company_id.is_(None), LedgerEntry.origin == "ASSET")):
            ref = e.origin_ref or ""
            if ref.endswith(":fees"):
                k = "ITBI, escritura e transferência (compra)"
            elif ref.endswith(":sale_tax"):
                k = "IR sobre ganho de capital (venda)"
            elif ref.endswith(":rent_tax"):
                k = "IR sobre aluguéis (carnê-leão)"
            elif ref.endswith(":stay_iss"):
                k = "ISS da hospedagem de temporada"
            elif ":cost:" in ref and cost_kind.get(int(ref.rsplit(":", 1)[1])) is not None and cost_kind[int(ref.rsplit(":", 1)[1])].value in label:
                k = label[cost_kind[int(ref.rsplit(":", 1)[1])].value]
            else:
                continue
            by[k] = by.get(k, Decimal("0.00")) + e.amount
        total = sum(by.values(), Decimal("0.00"))
        return {"total": total, "items": [{"tax": k, "amount": v} for k, v in sorted(by.items(), key=lambda kv: -kv[1])]}
    return _run(db, go)
