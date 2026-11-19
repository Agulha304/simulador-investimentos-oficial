"""Empresas: criação, finanças, pessoas, estoque, expansão, instalações e empréstimos."""
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.dependencies import CurrentUser, DbSession
from backend.models import (
    Company, CompanyCost, CompanyEvent, CompanyLoan, CompanyLoanInstallment, CompanyMonth, CompanyStatus, Employee,
    EmployeeStatus, Good, GoodStatus, InventoryItem, LedgerEntry, LoanStatus,
)
from backend.routers.budget import _run
from backend.schemas import companies as s
from backend.services import budget_service as bs
from backend.services import company_rules as rules
from backend.services import company_service as cs
from backend.services import goods_service, wealth_service

router = APIRouter(prefix="/companies", tags=["companies"])
ZERO = Decimal("0.00")


def _company_out(db: Session, c: Company) -> s.CompanyOut:
    seg = rules.SEGMENTS[c.segment]
    last = db.scalar(select(CompanyMonth).where(CompanyMonth.company_id == c.id).order_by(CompanyMonth.ref_month.desc()).limit(1))
    balance = cs.cash(db, c)
    loans = sum((l.balance for l in db.scalars(select(CompanyLoan).where(
        CompanyLoan.company_id == c.id, CompanyLoan.status == LoanStatus.ACTIVE))), ZERO)
    return s.CompanyOut(
        id=c.id, name=c.name, segment=c.segment, segment_label=seg.label, business_type=c.business_type, location=c.location,
        location_label=rules.LOCATIONS[c.location].label, size=c.size, units=c.units, capacity_level=c.capacity_level,
        price=c.price, reputation=c.reputation, owner_share_pct=c.owner_share_pct, owner_salary=c.owner_salary,
        auto_restock=c.auto_restock, status=c.status, founded_on=c.founded_on, marketing_until=c.marketing_until,
        cash=balance, debts=quantize_money(loans + max(-balance, ZERO)), equity=wealth_service.company_equity(db, c),
        last_revenue=last.revenue if last else None, last_net_result=last.net_result if last else None)


def _role_out(r: rules.Role) -> s.RoleOut:
    return s.RoleOut(key=r.key, label=r.label, salary=r.salary, units=r.units)


def _detail(db: Session, c: Company) -> s.CompanyDetailOut:
    seg = rules.SEGMENTS[c.segment]
    staff = cs._employees(db, c)
    exp_dem = rules.demand_units(seg, location=c.location, size=c.size, units=c.units, reputation=c.reputation, price=c.price,
                                 company_id=c.id, ref=c.founded_on, marketing=False, season=False)
    exp_cap = rules.capacity_units(seg, size=c.size, units=c.units, capacity_level=c.capacity_level,
                                   staff=[(e.role, e.productivity) for e in staff], equipment_factor=cs._equipment_factor(db, c))
    items = list(db.scalars(select(InventoryItem).where(InventoryItem.company_id == c.id).order_by(InventoryItem.id)))
    lease = cs._lease(db, c)
    loans = list(db.scalars(select(CompanyLoan).where(CompanyLoan.company_id == c.id).order_by(CompanyLoan.id)))
    role_labels = {r.key: r.label for r in seg.roles}
    employees = list(db.scalars(select(Employee).where(Employee.company_id == c.id).order_by(Employee.id)))
    goods = list(db.scalars(select(Good).where(Good.owner_account_id == c.account_id).order_by(Good.id)))
    return s.CompanyDetailOut(
        company=_company_out(db, c), distributable_profit=cs.distributable_profit(db, c), runway_months=cs.runway(db, c),
        monthly_obligations=cs.monthly_obligations(db, c), loan_limit=cs.loan_limit(db, c),
        expected_demand=round(exp_dem, 1), expected_capacity=round(exp_cap, 1),
        expansion_costs={k: rules.expansion_cost(seg, k, c.size, c.units) for k in ("CAPACITY", "NEW_UNIT", "LARGER_PREMISES", "MARKETING")},
        roles=[_role_out(r) for r in seg.roles],
        employees=[s.EmployeeOut(id=e.id, role=e.role, role_label=role_labels.get(e.role, e.role), level=e.level, salary=e.salary,
                                 total_cost=rules.payroll_cost(e.salary), hours_week=e.hours_week, productivity=e.productivity,
                                 status=e.status, hired_on=e.hired_on, terminated_on=e.terminated_on) for e in employees],
        inventory=[s.InventoryOut(id=i.id, name=i.name, unit=i.unit, quantity=i.quantity, unit_cost=i.unit_cost,
                                  value=quantize_money(i.quantity * i.unit_cost), supplier=i.supplier, min_quantity=i.min_quantity,
                                  monthly_consumption_est=Decimal(str(round(exp_dem * float(i.units_per_sale * (1 + i.waste_pct / 100)), 1))),
                                  low=i.quantity < i.min_quantity) for i in items],
        costs=[s.CostOut(id=x.id, kind=x.kind, name=x.name, amount=x.amount, active=x.active)
               for x in db.scalars(select(CompanyCost).where(CompanyCost.company_id == c.id).order_by(CompanyCost.id))],
        lease=s.LeaseOut(kind=lease.kind, good_id=lease.good_id, name=lease.name, monthly_rent=lease.monthly_rent,
                         start_month=lease.start_month) if lease else None,
        loans=[s.LoanOut(id=l.id, principal=l.principal, annual_rate_pct=l.annual_rate_pct, term_months=l.term_months,
                         start_month=l.start_month, balance=l.balance, status=l.status, installments=[
                             s.InstallmentOut(number=i.number, due_month=i.due_month, payment=i.payment, interest=i.interest,
                                              amortization=i.amortization, balance_after=i.balance_after, status=i.status)
                             for i in db.scalars(select(CompanyLoanInstallment).where(CompanyLoanInstallment.loan_id == l.id)
                                                 .order_by(CompanyLoanInstallment.number))]) for l in loans],
        goods=[s.CompanyGoodOut(id=g.id, name=g.name, category=g.category.value, current_value=g.current_value, status=g.status.value)
               for g in goods],
        months=[s.MonthOut.model_validate(m, from_attributes=True) for m in db.scalars(
            select(CompanyMonth).where(CompanyMonth.company_id == c.id).order_by(CompanyMonth.ref_month.desc()).limit(24))],
        events=[s.EventOut(ref_month=e.ref_month, type=e.type, description=e.description, amount=e.amount, created_at=e.created_at)
                for e in db.scalars(select(CompanyEvent).where(CompanyEvent.company_id == c.id).order_by(CompanyEvent.id.desc()).limit(60))],
        ledger=[s.LedgerLineOut(id=e.id, kind=e.kind, amount=e.amount, description=e.description, line=e.line, capital=e.capital,
                                ref_month=e.ref_month) for e in db.scalars(
            select(LedgerEntry).where(LedgerEntry.company_id == c.id).order_by(LedgerEntry.id.desc()).limit(80))])


# ------------------------------------------------------------------ catálogo, orçamento e visão geral

@router.get("/catalog", response_model=s.CatalogOut)
def catalog(user: CurrentUser):
    return s.CatalogOut(
        segments=[s.SegmentOut(
            key=g.key, label=g.label, description=g.description, unit_label=g.unit_label, price=g.price, tax_pct=g.tax_pct,
            roles=[_role_out(r) for r in g.roles], stock=[x.name for x in g.stock],
            required_capital=rules.required_capital(g, "bairro", rules.CompanySize.SMALL)) for g in rules.SEGMENTS.values()],
        locations=[{"key": k, "label": v.label, "demand": v.demand, "rent_factor": str(v.rent)} for k, v in rules.LOCATIONS.items()],
        sizes=[{"key": k.value, "label": v.label, "demand": v.demand, "setup_factor": str(v.setup)} for k, v in rules.SIZES.items()])


@router.post("/quote", response_model=s.QuoteOut)
def quote(body: s.QuoteIn, user: CurrentUser):
    if body.location not in rules.LOCATIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "localização inválida")
    seg = rules.SEGMENTS[body.segment]
    stock = sum((q * x.unit_cost for x, q in rules.initial_stock_quantities(seg, body.location, body.size)), ZERO)
    payroll = sum((rules.payroll_cost(rules.level_salary(seg.role(r), rules.EmployeeLevel.MID))
                   for r in rules.initial_staff(seg, body.size)), ZERO)
    return s.QuoteOut(
        required_capital=rules.required_capital(seg, body.location, body.size), setup_cost=rules.setup_cost(seg, body.size),
        monthly_fixed=rules.monthly_fixed(seg, body.location, body.size), monthly_payroll=quantize_money(payroll),
        initial_stock=quantize_money(stock), expected_units=round(rules.expected_units(seg, body.location, body.size), 1))


@router.get("/overview", response_model=s.OverviewOut)
def overview(user: CurrentUser, db: DbSession):
    def go():
        bs.ensure_setup(db, user.id)
        comps = [c for c in cs.user_companies(db, user.id) if c.status == CompanyStatus.ACTIVE]
        outs = [_company_out(db, c) for c in comps]
        last = {c.id: db.scalar(select(CompanyMonth).where(CompanyMonth.company_id == c.id).order_by(CompanyMonth.ref_month.desc()).limit(1))
                for c in comps}
        rev = sum((m.revenue for m in last.values() if m), ZERO)
        spent = sum((m.variable_costs + m.fixed_costs + m.payroll + m.taxes + m.interest for m in last.values() if m), ZERO)
        return s.OverviewOut(
            count=len(comps), equity_total=sum((o.equity for o in outs), ZERO),
            equity_user_share=wealth_service.companies_net_value(db, user.id), cash_total=sum((o.cash for o in outs), ZERO),
            debts_total=sum((o.debts for o in outs), ZERO), revenue_last_month=rev, expenses_last_month=quantize_money(spent),
            net_last_month=quantize_money(rev - spent), companies=outs)
    return _run(db, go)


@router.get("", response_model=list[s.CompanyOut])
def list_companies(user: CurrentUser, db: DbSession):
    def go():
        bs.ensure_setup(db, user.id)
        return [_company_out(db, c) for c in cs.user_companies(db, user.id)]
    return _run(db, go)


@router.post("", response_model=s.CompanyDetailOut, status_code=status.HTTP_201_CREATED)
def create(body: s.CompanyCreate, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        c = cs.create_company(db, user.id, month, name=body.name, segment=body.segment, location=body.location, size=body.size,
                              capital=body.capital, owner_share_pct=body.owner_share_pct, business_type=body.business_type)
        return _detail(db, c)
    return _run(db, go)


@router.get("/{company_id}", response_model=s.CompanyDetailOut)
def detail(company_id: int, user: CurrentUser, db: DbSession):
    def go():
        bs.ensure_setup(db, user.id)
        return _detail(db, cs.get_company(db, user.id, company_id))
    return _run(db, go)


def _act(db: Session, user_id: int, company_id: int, fn):
    month = bs.ensure_setup(db, user_id)
    fn(month)
    return _detail(db, cs.get_company(db, user_id, company_id))


@router.post("/{company_id}/contribute", response_model=s.CompanyDetailOut)
def contribute(company_id: int, body: s.MoneyIn, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: cs.contribute(db, user.id, m, company_id, body.amount, body.idempotency_key)))


@router.post("/{company_id}/distribute", response_model=s.CompanyDetailOut)
def distribute(company_id: int, body: s.MoneyIn, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: cs.distribute(db, user.id, m, company_id, body.amount, body.idempotency_key)))


@router.patch("/{company_id}/settings", response_model=s.CompanyDetailOut)
def settings(company_id: int, body: s.SettingsIn, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: cs.update_settings(
        db, user.id, m, company_id, price=body.price, owner_salary=body.owner_salary, auto_restock=body.auto_restock)))


@router.post("/{company_id}/employees", response_model=s.CompanyDetailOut, status_code=status.HTTP_201_CREATED)
def hire(company_id: int, body: s.HireIn, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: cs.hire(db, user.id, m, company_id, body.role, body.level, body.confirm_risk)))


@router.delete("/{company_id}/employees/{employee_id}", response_model=s.CompanyDetailOut)
def fire(company_id: int, employee_id: int, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: cs.fire(db, user.id, m, company_id, employee_id)))


@router.post("/{company_id}/stock", response_model=s.CompanyDetailOut, status_code=status.HTTP_201_CREATED)
def buy_stock(company_id: int, body: s.StockIn, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: cs.buy_stock(db, user.id, m, company_id, body.item_id, body.quantity, body.idempotency_key)))


@router.post("/{company_id}/expand", response_model=s.CompanyDetailOut)
def expand(company_id: int, body: s.ExpandIn, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: cs.expand(db, user.id, m, company_id, body.kind)))


@router.post("/{company_id}/lease", response_model=s.CompanyDetailOut)
def lease(company_id: int, body: s.LeaseIn, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: cs.set_lease(
        db, user.id, m, company_id, body.kind, good_id=body.good_id, monthly_rent=body.monthly_rent, name=body.name)))


@router.post("/{company_id}/loans", response_model=s.CompanyDetailOut, status_code=status.HTTP_201_CREATED)
def loan(company_id: int, body: s.LoanIn, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: cs.take_loan(db, user.id, m, company_id, body.amount, body.term_months)))


@router.post("/{company_id}/goods/purchase", response_model=s.CompanyDetailOut, status_code=status.HTTP_201_CREATED)
def buy_good(company_id: int, body: s.CompanyGoodIn, user: CurrentUser, db: DbSession):
    def fn(month):
        c = cs.get_company(db, user.id, company_id, lock=True)
        cs._active(c)
        goods_service.purchase(db, user.id, month, listing_key=body.listing_key, purchase_key=body.idempotency_key,
                               extra_costs=body.extra_costs, company=c)
    return _run(db, lambda: _act(db, user.id, company_id, fn))
