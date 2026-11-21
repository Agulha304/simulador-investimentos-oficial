"""Empresas: criação, finanças, pessoas, estoque, expansão, instalações e empréstimos."""
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.dependencies import CurrentUser, DbSession
from backend.models import (
    Company, CompanyCost, CompanyEvent, CompanyLoan, CompanyLoanInstallment, CompanyMonth, CompanyStatus, Employee,
    EmployeeStatus, Good, GoodStatus, InventoryItem, LedgerEntry, LoanStatus, SimMonth,
)
from backend.routers.budget import _run
from backend.schemas import companies as s
from backend.services import budget_service as bs
from backend.services import partners
from backend.services import company_rules as rules
from backend.services import company_service as cs
from backend.services import company_team as team
from backend.services import goods_service, wealth_service

router = APIRouter(prefix="/companies", tags=["companies"])
ZERO = Decimal("0.00")


_UNSET = object()


def _company_out(db: Session, c: Company, last=_UNSET) -> s.CompanyOut:
    seg = rules.SEGMENTS[c.segment]
    if last is _UNSET:
        last = db.scalar(select(CompanyMonth).where(CompanyMonth.company_id == c.id).order_by(CompanyMonth.ref_month.desc()).limit(1))
    balance = cs.cash(db, c)
    loans = sum((l.balance for l in db.scalars(select(CompanyLoan).where(
        CompanyLoan.company_id == c.id, CompanyLoan.status == LoanStatus.ACTIVE))), ZERO)
    return s.CompanyOut(
        id=c.id, name=c.name, segment=c.segment, segment_label=seg.label, unit_label=seg.unit_label,
        metrics_kind=seg.metrics_kind.value, channel=c.channel, site_mode=c.site_mode, site_value=c.site_value, location=c.location,
        location_label=rules.resolve_location(seg, c.location).label, size=c.size, units=c.units, capacity_level=c.capacity_level,
        price=c.price, reputation=c.reputation, owner_share_pct=c.owner_share_pct, owner_salary=c.owner_salary,
        auto_restock=c.auto_restock, status=c.status, founded_on=c.founded_on, marketing_until=c.marketing_until,
        cash=balance, debts=quantize_money(loans + max(-balance, ZERO)), equity=wealth_service.company_equity(db, c),
        last_revenue=last.revenue if last else None, last_net_result=last.net_result if last else None)


_GENERIC_KEYS = {r.key for r in rules.GENERIC_ROLES}


def _role_out(r: rules.Role, channel: rules.CompanyChannel | None = None) -> s.RoleOut:
    return s.RoleOut(key=r.key, label=r.label, salary=r.salary, units=r.units, generic=r.key in _GENERIC_KEYS,
                     mandatory=channel is not None and r.key in rules.mandatory_roles(channel))


def _open_ref(db: Session, c: Company):
    m = db.scalar(select(SimMonth).where(SimMonth.user_id == c.user_id, SimMonth.status == "OPEN"))
    return m.ref_month if m else c.founded_on


def _employee_out(e: Employee, labels: dict, ref) -> s.EmployeeOut:
    tenure = team.tenure_months(e.hired_on, ref)
    return s.EmployeeOut(
        id=e.id, name=e.name, role=e.role, role_label=labels.get(e.role, e.role), level=e.level, regime=e.regime, schedule=e.schedule,
        education=e.education, education_label=team.EDUCATION_LABEL[e.education], experience_years=e.experience_years, salary=e.salary,
        total_cost=cs.employee_cost(e), severance_estimate=team.severance(e.regime, e.salary, tenure),
        lawsuit_risk_pct=round(team.lawsuit_probability(e.regime, e.hours_week, e.schedule, tenure) * 100, 1),
        hours_week=e.hours_week, productivity=e.productivity, status=e.status, hired_on=e.hired_on, terminated_on=e.terminated_on)


def _candidate_out(x: team.Candidate, seg: rules.Segment) -> s.CandidateOut:
    return s.CandidateOut(
        id=x.id, name=x.name, role=x.role, role_label=seg.role(x.role).label, regime=x.regime, education=x.education,
        education_label=team.EDUCATION_LABEL[x.education], experience_years=x.experience_years, level=x.level,
        level_label=team.LEVEL_LABEL[x.level], productivity=x.productivity, asking_salary=x.asking_salary, hours_week=x.hours_week,
        schedule=x.schedule, monthly_cost_at_asking=rules.payroll_cost(x.asking_salary, x.regime))


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
    inst_by_loan: dict[int, list] = {l.id: [] for l in loans}
    if loans:
        for i in db.scalars(select(CompanyLoanInstallment).where(CompanyLoanInstallment.loan_id.in_(inst_by_loan))
                            .order_by(CompanyLoanInstallment.number)):
            inst_by_loan[i.loan_id].append(i)
    role_labels = {r.key: r.label for r in seg.roles}
    employees = list(db.scalars(select(Employee).where(Employee.company_id == c.id).order_by(Employee.id)))
    open_ref = _open_ref(db, c)
    goods = list(db.scalars(select(Good).where(Good.owner_account_id == c.account_id).order_by(Good.id)))
    from backend.models import CompanyPartner, Person
    people = {x.id: x for x in db.scalars(select(Person).where(Person.user_id == c.user_id))}
    partner_rows = [{"person_id": x.person_id, "name": people[x.person_id].name, "share_pct": str(x.share_pct), "contribution": str(x.contribution),
                     "status": x.status, "joined_month": x.joined_month.isoformat(), "finance": partners.finance_label(people[x.person_id])}
                    for x in partners.partners_of(db, c.id)]
    return s.CompanyDetailOut(
        partners=partner_rows,
        company=_company_out(db, c), distributable_profit=cs.distributable_profit(db, c), runway_months=cs.runway(db, c),
        monthly_obligations=cs.monthly_obligations(db, c), loan_limit=cs.loan_limit(db, c),
        expected_demand=round(exp_dem, 1), expected_capacity=round(exp_cap, 1),
        expansion_costs={k: rules.expansion_cost(seg, k, c.size, c.units) for k in ("CAPACITY", "NEW_UNIT", "LARGER_PREMISES", "MARKETING")},
        roles=[_role_out(r, c.channel) for r in seg.roles],
        compliance=s.ComplianceOut(**cs.compliance(db, c)),
        employees=[_employee_out(e, role_labels, open_ref) for e in employees],
        inventory=[s.InventoryOut(id=i.id, name=i.name, unit=i.unit, quantity=i.quantity, unit_cost=i.unit_cost,
                                  value=quantize_money(i.quantity * i.unit_cost), supplier=i.supplier, min_quantity=i.min_quantity,
                                  monthly_consumption_est=Decimal(str(round(exp_dem * float(i.units_per_sale * (1 + i.waste_pct / 100)), 1))),
                                  low=i.quantity < i.min_quantity) for i in items] if seg.has_stock else [],
        costs=[s.CostOut(id=x.id, kind=x.kind, name=x.name, amount=x.amount, active=x.active)
               for x in db.scalars(select(CompanyCost).where(CompanyCost.company_id == c.id).order_by(CompanyCost.id))],
        lease=s.LeaseOut(kind=lease.kind, good_id=lease.good_id, name=lease.name, monthly_rent=lease.monthly_rent,
                         start_month=lease.start_month) if lease else None,
        loans=[s.LoanOut(id=l.id, principal=l.principal, annual_rate_pct=l.annual_rate_pct, term_months=l.term_months,
                         start_month=l.start_month, balance=l.balance, status=l.status, installments=[
                             s.InstallmentOut(number=i.number, due_month=i.due_month, payment=i.payment, interest=i.interest,
                                              amortization=i.amortization, balance_after=i.balance_after, status=i.status)
                             for i in inst_by_loan[l.id]]) for l in loans],
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

def _segment_out(g: rules.Segment) -> s.SegmentOut:
    channel = rules.PHYSICAL if rules.PHYSICAL in g.channels else g.channels[0]
    loc = g.default_location
    return s.SegmentOut(
        key=g.key, label=g.label, description=g.description, unit_label=g.unit_label, price=g.price, tax_pct=g.tax_pct,
        roles=[_role_out(r) for r in g.roles], stock=[x.name for x in g.stock] if g.has_stock else [],
        minimum_capital=rules.minimum_capital(g, loc, rules.CompanySize.SMALL, channel,
                                              rules.SiteMode.RENT if channel == rules.PHYSICAL else None),
        channels=list(g.channels), metrics_kind=g.metrics_kind.value, default_location=loc,
        locations=[s.LocationOut(key=x.key, label=x.label, demand=x.demand, rent_factor=x.rent, land_price=x.land_price)
                   for x in g.locations])


@router.get("/catalog", response_model=s.CatalogOut)
def catalog(user: CurrentUser):
    return s.CatalogOut(
        segments=[_segment_out(g) for g in rules.SEGMENTS.values()],
        sizes=[{"key": k.value, "label": v.label, "demand": v.demand, "setup_factor": str(v.setup)} for k, v in rules.SIZES.items()])


@router.post("/quote", response_model=s.QuoteOut)
def quote(body: s.QuoteIn, user: CurrentUser):
    seg = rules.SEGMENTS[body.segment]
    channel = body.channel or (rules.PHYSICAL if rules.PHYSICAL in seg.channels else seg.channels[0])
    try:
        location, site_mode = rules.validate_site(seg, channel, body.location, body.site_mode)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    stock = sum((q * x.unit_cost for x, q in rules.initial_stock_quantities(seg, location, body.size)), ZERO)
    mandatory = rules.mandatory_roles(channel)
    payroll = sum((rules.payroll_cost(seg.role(r).salary) for r in mandatory), ZERO)
    minimum = rules.minimum_capital(seg, location, body.size, channel, site_mode)
    owner_cost = quantize_money(minimum * body.owner_share_pct / 100)
    extra = quantize_money(body.extra_capital)
    return s.QuoteOut(
        channel=channel, site_mode=site_mode, location=location, owner_share_pct=body.owner_share_pct,
        minimum_capital=minimum, owner_cost=owner_cost, extra_capital=extra, total_owner_cost=quantize_money(owner_cost + extra),
        setup_cost=rules.setup_cost(seg, body.size, channel), initial_stock=quantize_money(stock),
        land_cost=rules.land_value(seg, channel, site_mode, location, body.size),
        monthly_fixed=rules.monthly_fixed(seg, location, body.size, channel=channel, site_mode=site_mode),
        monthly_rent=rules.monthly_rent(seg, location, body.size, channel=channel, site_mode=site_mode),
        monthly_payroll=quantize_money(payroll), mandatory_cost=rules.mandatory_setup_cost(seg, channel),
        mandatory_roles=[seg.role(r).label for r in mandatory], expected_units=round(rules.expected_units(seg, location, body.size), 1))


@router.get("/overview", response_model=s.OverviewOut)
def overview(user: CurrentUser, db: DbSession):
    def go():
        bs.ensure_setup(db, user.id)
        comps = [c for c in cs.user_companies(db, user.id) if c.status == CompanyStatus.ACTIVE]
        last = {c.id: db.scalar(select(CompanyMonth).where(CompanyMonth.company_id == c.id).order_by(CompanyMonth.ref_month.desc()).limit(1))
                for c in comps}
        outs = [_company_out(db, c, last[c.id]) for c in comps]
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
        seg = rules.SEGMENTS[body.segment]
        channel = body.channel or (rules.PHYSICAL if rules.PHYSICAL in seg.channels else seg.channels[0])
        c = cs.create_company(db, user.id, month, name=body.name, segment=body.segment, channel=channel, location=body.location,
                              site_mode=body.site_mode, size=body.size, extra_capital=body.extra_capital,
                              owner_share_pct=body.owner_share_pct, partner_invite_ids=body.partner_invite_ids)
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


@router.post("/{company_id}/candidates", response_model=s.CandidatesOut)
def candidates(company_id: int, body: s.CandidatesIn, user: CurrentUser, db: DbSession):
    """Candidatos do mês para o cargo e o regime: determinísticos (mesma consulta, mesma lista) e recalculados no servidor."""
    def go():
        month = bs.ensure_setup(db, user.id)
        c = cs.get_company(db, user.id, company_id)
        seg = rules.SEGMENTS[c.segment]
        rows = cs.list_candidates(db, user.id, month, company_id, body.role, body.regime)
        return s.CandidatesOut(role=body.role, regime=body.regime, month=month.ref_month, candidates=[_candidate_out(x, seg) for x in rows])
    return _run(db, go)


@router.post("/{company_id}/hire", response_model=s.HireOut)
def hire(company_id: int, body: s.HireIn, user: CurrentUser, db: DbSession):
    """Faz a proposta: o candidato aceita, recusa (fica indisponível no mês) ou devolve uma contraproposta."""
    def go():
        month = bs.ensure_setup(db, user.id)
        res = cs.hire(db, user.id, month, company_id, candidate_id=body.candidate_id, salary=body.salary, hours_week=body.hours_week,
                      schedule=body.schedule, regime=body.regime, confirm_risk=body.confirm_risk, idempotency_key=body.idempotency_key)
        return s.HireOut(accepted=res.accepted, status=res.status, message=res.message, counter_offer=res.counter_offer,
                         company=_detail(db, cs.get_company(db, user.id, company_id)))
    return _run(db, go)


@router.post("/{company_id}/headhunter", response_model=s.HeadhunterOut)
def headhunter(company_id: int, body: s.HeadhunterIn, user: CurrentUser, db: DbSession):
    """Headhunter: cobra o honorário (1x o salário-teto; metade se ninguém servir) e devolve até 3 candidatos do briefing."""
    def go():
        month = bs.ensure_setup(db, user.id)
        found, fee = cs.headhunter(db, user.id, month, company_id, role_key=body.role, regime=body.regime, max_salary=body.max_salary,
                                   min_level=body.min_level, idempotency_key=body.idempotency_key)
        c = cs.get_company(db, user.id, company_id)
        seg = rules.SEGMENTS[c.segment]
        msg = (f"O headhunter encontrou {len(found)} candidato(s) dentro do briefing." if found
               else "Nenhum candidato atendeu ao briefing: cobrança de metade do honorário. Revise orçamento ou nível mínimo.")
        return s.HeadhunterOut(fee=fee, found=len(found), message=msg, candidates=[_candidate_out(x, seg) for x in found],
                               company=_detail(db, c))
    return _run(db, go)


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
                               company=c)
    return _run(db, lambda: _act(db, user.id, company_id, fn))


@router.post("/partner-invites")
def partner_invite(body: s.PartnerInviteIn, user: CurrentUser, db: DbSession):
    """Convida um amigo ou parceiro para ser sócio. A resposta é decidida uma vez por pessoa e mês."""
    def go():
        month = bs.ensure_setup(db, user.id)
        inv = partners.invite(db, user.id, month, body.person_id, body.share_pct, body.capital)
        return {"id": inv.id, "person_id": inv.person_id, "accepted": inv.accepted, "message": inv.message,
                "share_pct": str(inv.share_pct), "capital": str(inv.capital), "used": inv.used}
    return _run(db, go)


@router.get("/invites/current")
def partner_invites(user: CurrentUser, db: DbSession):
    def go():
        from backend.models import PartnerInvite
        month = bs.ensure_setup(db, user.id)
        return [{"id": i.id, "person_id": i.person_id, "accepted": i.accepted, "message": i.message, "share_pct": str(i.share_pct),
                 "capital": str(i.capital), "used": i.used}
                for i in db.scalars(select(PartnerInvite).where(PartnerInvite.user_id == user.id, PartnerInvite.ref_month == month.ref_month))]
    return _run(db, go)
