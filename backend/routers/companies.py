"""Empresas: criação, finanças, pessoas, estoque, expansão, instalações e empréstimos."""
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.dependencies import CurrentUser, DbSession
from backend.models import (
    Company, CompanyCost, CompanyEvent, CompanyLoan, CompanySupplier, CompanyUnit, CompanyLoanInstallment, CompanyMonth, CompanyStatus, Employee,
    EmployeeStatus, Good, GoodStatus, InventoryItem, LedgerEntry, LoanStatus, SimMonth,
)
from backend.routers.budget import _run
from backend.schemas import companies as s
from backend.services import budget_service as bs
from backend.services import partners
from backend.services import company_expansion as xp
from backend.services import company_acquisition as acq
from backend.services import company_aides_service as aidesvc
from backend.services import company_world as cw
from backend.services import country_rules as crules
from backend.services import world_service as wsvc
from backend.services import company_franchise as franchise_svc
from backend.services import company_ipo as ipo_svc
from backend.services import company_recruiter_service as recsvc
from backend.services import company_rules as rules
from backend.services import company_service as cs
from backend.services import company_taxes as ctax
from backend.services import company_supply as supply
from backend.services import company_team as team
from backend.services import economy_service, goods_service, wealth_service

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
        quality=float(c.quality), capacity_boost=float(c.capacity_boost), storage_boost=float(c.storage_boost),
        marketing_boost=float(c.marketing_boost), suspended_until=c.suspended_until,
        price=c.price, reputation=c.reputation, relevance=float(c.relevance), owner_share_pct=c.owner_share_pct, owner_salary=c.owner_salary,
        auto_restock=c.auto_restock, status=c.status, founded_on=c.founded_on, marketing_until=c.marketing_until,
        cash=balance, debts=quantize_money(loans + max(-balance, ZERO)), equity=wealth_service.company_equity(db, c),
        last_revenue=last.revenue if last else None, last_net_result=last.net_result if last else None,
        country=c.country, country_name=crules.get(c.country).name, currency=crules.get(c.country).currency, opens_month=c.opens_month,
        country_factor=cw.company_factor(db, c, c.last_processed_month or c.founded_on),
        supplier_budget=cs.supplier_budget(db, c)["total_planned"], supply_ready=all(x["present"] for x in cs.supply_checklist(db, c)))


_GENERIC_KEYS = {r.key for r in rules.GENERIC_ROLES}


def _role_out(r: rules.Role, channel: rules.CompanyChannel | None = None) -> s.RoleOut:
    return s.RoleOut(key=r.key, label=r.label, salary=r.salary, units=r.units, generic=r.key in _GENERIC_KEYS, hours=r.hours,
                     mandatory=channel is not None and r.key in rules.mandatory_roles(channel))


def _open_ref(db: Session, c: Company):
    m = db.scalar(select(SimMonth).where(SimMonth.user_id == c.user_id, SimMonth.status == "OPEN"))
    return m.ref_month if m else c.founded_on


def _employee_out(e: Employee, labels: dict, ref) -> s.EmployeeOut:
    tenure = team.tenure_months(e.hired_on, ref)
    return s.EmployeeOut(
        id=e.id, name=e.name, role=e.role, role_label=labels.get(e.role, e.role), level=e.level, regime=e.regime, schedule=e.schedule,
        education=e.education, education_label=team.EDUCATION_LABEL[e.education], experience_years=e.experience_years, salary=e.salary,
        total_cost=cs.employee_cost(e), work_mode=e.work_mode, country=e.country, country_name=crules.get(e.country).name,
        can_remote=cw.can_be_remote(e.role), severance_estimate=team.severance(e.regime, e.salary, tenure),
        lawsuit_risk_pct=round(team.lawsuit_probability(e.regime, e.hours_week, e.schedule, tenure, e.lawsuit_history) * 100, 1),
        lawsuit_history=e.lawsuit_history,
        hours_week=e.hours_week, productivity=e.productivity, status=e.status, hired_on=e.hired_on, terminated_on=e.terminated_on)


def _candidate_out(x: team.Candidate, seg: rules.Segment) -> s.CandidateOut:
    return s.CandidateOut(
        id=x.id, name=x.name, role=x.role, role_label=seg.role(x.role).label, regime=x.regime, education=x.education,
        education_label=team.EDUCATION_LABEL[x.education], experience_years=x.experience_years, level=x.level,
        level_label=team.LEVEL_LABEL[x.level], productivity=x.productivity, asking_salary=x.asking_salary, hours_week=x.hours_week,
        schedule=x.schedule, monthly_cost_at_asking=rules.payroll_cost(x.asking_salary, x.regime),
        lawsuit_history=x.lawsuit_history, can_remote=cw.can_be_remote(x.role),
        remote_effect_pct=round((cw.REMOTE_FACTOR.get(x.role, 1.0) - 1) * 100, 1))


def _contract_out(c: Company, seg: rules.Segment, x: CompanySupplier, ref) -> s.SupplierContractOut:
    cat = seg.supply(x.category)
    fine = ZERO if (x.is_default or x.status != "ACTIVE" or cs.months_between(x.started_month, ref) >= supply.MIN_TENURE_MONTHS) \
        else quantize_money(x.min_monthly_order * x.unit_price * supply.EARLY_END_FINE_ORDERS)
    return s.SupplierContractOut(
        id=x.id, category=x.category, category_label=cat.label, unit=cat.unit, name=x.name, unit_price=x.unit_price,
        reference_price=x.reference_price, price_vs_reference_pct=round(float(x.unit_price / x.reference_price - 1) * 100, 1),
        min_monthly_order=x.min_monthly_order, max_units_month=x.max_units_month, reliability=float(x.reliability),
        failure_probability_pct=round((1 - float(x.reliability)) * 100, 1), lead_days=x.lead_days, status=x.status,
        started_month=x.started_month, ended_month=x.ended_month, term_months=x.term_months, is_default=x.is_default,
        volume_used=(x.volume_used if x.volume_month == ref else ZERO), early_end_fine=fine,
        max_monthly_spend=x.max_monthly_spend, volume_cap=x.volume_cap,
        min_reliability=float(x.min_reliability) if x.min_reliability is not None else None, max_lead_days=x.max_lead_days,
        spend_used=(x.spend_used if x.volume_month == ref else ZERO), effective_volume=cs.effective_volume(x))


def _supply_out(db: Session, c: Company, seg: rules.Segment, open_ref) -> s.SupplyOut:
    if not seg.needs_suppliers:
        return s.SupplyOut(required=False, ready=True, checklist=[], contracts=[], budget=s.SupplierBudgetOut(
            rows=[], total_planned=ZERO, total_last_actual=ZERO))
    checklist = cs.supply_checklist(db, c)
    ready = all(x["present"] for x in checklist)
    rows = list(db.scalars(select(CompanySupplier).where(CompanySupplier.company_id == c.id).order_by(CompanySupplier.id)))
    state = cs.supply_state(db, c, open_ref)
    missing = [x["label"] for x in checklist if not x["present"]]
    warning = None
    if missing:
        warning = ("Contrate fornecedores antes de operar: faltam " + ", ".join(missing) + ". "
                   + ("Sem eles a operação fica bloqueada (vendas zeradas)." if seg.metrics_kind == rules.MetricsKind.SERVICE
                      else "Sem eles o estoque dessas categorias não é reposto e as vendas travam na ruptura."))
    return s.SupplyOut(
        required=True, ready=ready, checklist=[s.SupplyChecklistOut(**x) for x in checklist],
        contracts=[_contract_out(c, seg, x, open_ref) for x in rows if x.status == "ACTIVE"],
        ended=[_contract_out(c, seg, x, open_ref) for x in rows if x.status != "ACTIVE"][-10:],
        effective_capacity=None if state["cap"] == float("inf") else round(state["cap"], 1),
        budget=s.SupplierBudgetOut(**cs.supplier_budget(db, c)), warning=warning)


def _units_list(db: Session, c: Company, seg: rules.Segment) -> list[s.UnitOut]:
    """Matriz (a própria empresa) + todas as filiais (abertas e fechadas)."""
    def label(loc: str) -> str:
        return rules.resolve_location(seg, loc).label
    out = [s.UnitOut(id=None, kind="HQ", name="Matriz", location=c.location, location_label=label(c.location), channel=c.channel,
                     site_mode=c.site_mode, site_value=c.site_value, monthly_rent=(cs._lease(db, c).monthly_rent if cs._lease(db, c) else ZERO),
                     relevance=float(c.relevance), status="OPEN", opened_month=c.founded_on)]
    for u in db.scalars(select(CompanyUnit).where(CompanyUnit.company_id == c.id).order_by(CompanyUnit.id)):
        out.append(s.UnitOut(id=u.id, kind=u.kind, name=u.name, location=u.location, location_label=label(u.location), channel=u.channel,
                             site_mode=u.site_mode, site_value=u.site_value, monthly_rent=u.monthly_rent, relevance=float(u.relevance),
                             viability=float(u.viability), status=u.status, opened_month=u.opened_month, closed_month=u.closed_month,
                             closed_reason=u.closed_reason, cumulative_result=u.cumulative_result, investment=u.investment))
    return out


def _detail(db: Session, c: Company) -> s.CompanyDetailOut:
    seg = rules.SEGMENTS[c.segment]
    staff = cs._employees(db, c)
    open_ref = _open_ref(db, c)
    q = float(c.quality)
    exp_dem, exp_cap = cs.expected_totals(db, c, seg, staff)
    mature = rules.demand_units(seg, location=c.location, size=c.size, units=c.units, reputation=c.reputation, price=c.price,
                                company_id=c.id, ref=c.founded_on, marketing=False, season=False, quality=q)
    ratio = rules.price_ratio(seg, c.price, q)
    market = s.MarketOut(
        relevance=float(c.relevance), demand_factor=round(rules.relevance_factor(float(c.relevance)), 3),
        zero_month_prob=round(rules.zero_month_prob(float(c.relevance), ratio), 3), price_ratio=round(ratio, 3),
        price_factor=round(rules.price_factor(seg, c.price, q), 3), mature_demand=round(mature, 1),
        production_cap=round(rules.production_ceiling(seg, c.size, c.units, float(c.capacity_boost)), 1),
        storage_cap_units=round(rules.storage_cap_units(seg, c.size, c.units, float(c.storage_boost)), 1) if seg.has_stock else 0,
        max_staff=rules.max_staff(c.size, c.units), staff_count=len(staff), relocated_this_month=c.relocated_on == open_ref,
        crisis=economy_service.company_crisis_info(db, c, open_ref))
    items = list(db.scalars(select(InventoryItem).where(InventoryItem.company_id == c.id).order_by(InventoryItem.id)))
    lease = cs._lease(db, c)
    loans = list(db.scalars(select(CompanyLoan).where(CompanyLoan.company_id == c.id).order_by(CompanyLoan.id)))
    inst_by_loan: dict[int, list] = {l.id: [] for l in loans}
    if loans:
        for i in db.scalars(select(CompanyLoanInstallment).where(CompanyLoanInstallment.loan_id.in_(inst_by_loan))
                            .order_by(CompanyLoanInstallment.number)):
            inst_by_loan[i.loan_id].append(i)
    role_labels = {r.key: r.label for r in seg.roles}
    role_labels[xp.MANAGER_ROLE] = xp.MANAGER_LABEL
    employees = list(db.scalars(select(Employee).where(Employee.company_id == c.id).order_by(Employee.id)))
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
        expected_demand=round(exp_dem, 1), expected_capacity=round(exp_cap, 1), market=market,
        expansion_costs={k: {t: xp.base_cost(c, k, t) for t in rules.TIERS} for k in rules.EXPANSION_KINDS},
        expansion_tiers=xp.tier_table(c), units_list=_units_list(db, c, seg),
        roles=[_role_out(seg.role_for(r.key, c.size), c.channel) for r in seg.roles],
        compliance=s.ComplianceOut(**cs.compliance(db, c)),
        supply=_supply_out(db, c, seg, open_ref),
        recruiter=s.RecruiterOut(**rv) if (rv := recsvc.view(db, c)) else None, recruiter_tiers=recsvc.tier_options(c),
        aides=aidesvc.view(db, c), aide_options=aidesvc.options(c), opens_month=c.opens_month,
        franchise=franchise_svc.view(db, c, open_ref), ipo=ipo_svc.view(db, c, open_ref),
        employees=[_employee_out(e, role_labels, open_ref) for e in employees],
        inventory=[s.InventoryOut(id=i.id, name=i.name, unit=i.unit, quantity=i.quantity, unit_cost=i.unit_cost,
                                  value=quantize_money(i.quantity * i.unit_cost), supplier=i.supplier, min_quantity=i.min_quantity,
                                  monthly_consumption_est=Decimal(str(round(exp_dem * float(i.units_per_sale * (1 + i.waste_pct / 100)), 1))),
                                  low=i.quantity < i.min_quantity, max_quantity=rules.storage_cap_qty(seg, c.size, c.units, i, float(c.storage_boost)),
                                  category=i.category, contracted=(i.category or "") in cs._contracts(db, c)) for i in items] if seg.has_stock else [],
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

def _tax_info(segment: str) -> s.SegmentTaxInfoOut:
    return s.SegmentTaxInfoOut(**ctax.segment_tax_info(segment), simplifications=ctax.SIMPLIFICACOES)


def _cat_out(x: rules.SupplyCategory) -> s.SupplyCategoryOut:
    return s.SupplyCategoryOut(key=x.key, label=x.label, unit=x.unit, weight=x.weight, per_sale=x.per_sale, reference_price=x.ref_price)


def _segment_out(g: rules.Segment) -> s.SegmentOut:
    channel = rules.PHYSICAL if rules.PHYSICAL in g.channels else g.channels[0]
    loc = g.default_location
    return s.SegmentOut(
        key=g.key, label=g.label, description=g.description, unit_label=g.unit_label, price=g.price, tax=_tax_info(g.key.value),
        roles=[_role_out(r) for r in g.roles], stock=[x.name for x in g.stock] if g.has_stock else [],
        minimum_capital=rules.minimum_capital(g, loc, rules.CompanySize.SMALL, channel,
                                              rules.SiteMode.RENT if channel == rules.PHYSICAL else None),
        channels=list(g.channels), metrics_kind=g.metrics_kind.value, default_location=loc,
        supply_categories=[_cat_out(x) for x in g.supply_categories],
        locations=[s.LocationOut(key=x.key, label=x.label, demand=x.demand, rent_factor=x.rent, land_price=x.land_price)
                   for x in g.locations])


@router.get("/catalog", response_model=s.CatalogOut)
def catalog(user: CurrentUser):
    return s.CatalogOut(
        segments=[_segment_out(g) for g in rules.SEGMENTS.values()],
        sizes=[{"key": k.value, "label": v.label, "demand": v.demand, "setup_factor": str(v.setup)} for k, v in rules.SIZES.items()])


@router.post("/quote", response_model=s.QuoteOut)
def quote(body: s.QuoteIn, user: CurrentUser, db: DbSession):
    seg = rules.SEGMENTS[body.segment]
    try:
        cc = crules.get(body.country)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    month = bs.ensure_setup(db, user.id)
    rate = wsvc.fx(db, user.id, cc.code, month.ref_month)
    fz = Decimal(str(round(cc.cost_index * float(rate * wsvc.price_level(db, user.id, cc.code, month.ref_month)) / cc.fx0, 6))) if cc.code != "BR" else Decimal(1)
    channel = body.channel or (rules.PHYSICAL if rules.PHYSICAL in seg.channels else seg.channels[0])
    try:
        location, site_mode = rules.validate_site(seg, channel, body.location, body.site_mode)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    stock = rules.first_purchase_reserve(seg, location, body.size)
    mandatory = rules.mandatory_roles(channel)
    payroll = rules.mandatory_monthly_payroll(seg, channel, body.size)
    minimum = quantize_money(rules.minimum_capital(seg, location, body.size, channel, site_mode) * fz)
    owner_cost = quantize_money(minimum * body.owner_share_pct / 100)
    extra = quantize_money(body.extra_capital)
    return s.QuoteOut(
        channel=channel, site_mode=site_mode, location=location, owner_share_pct=body.owner_share_pct,
        minimum_capital=minimum, owner_cost=owner_cost, extra_capital=extra, total_owner_cost=quantize_money(owner_cost + extra),
        setup_cost=quantize_money(rules.setup_cost(seg, body.size, channel) * fz), initial_stock=quantize_money(stock * fz),
        first_purchase_reserve=quantize_money(stock * fz), supply_categories=[_cat_out(x) for x in seg.supply_categories],
        land_cost=quantize_money(rules.land_value(seg, channel, site_mode, location, body.size) * fz),
        monthly_fixed=quantize_money(rules.monthly_fixed(seg, location, body.size, channel=channel, site_mode=site_mode) * fz),
        monthly_rent=quantize_money(rules.monthly_rent(seg, location, body.size, channel=channel, site_mode=site_mode) * fz),
        country=cc.code, country_name=cc.name, currency=cc.currency, rate=rate, country_factor=fz, income_tax=cc.income_tax, vat=cc.vat,
        corp_tax=cc.corp_tax, open_months=rules.opening_months(body.size, site_mode) + (cw.FOREIGN_OPEN_EXTRA_MONTHS if cc.code != "BR" else 0),
        tax=_tax_info(body.segment.value),
        monthly_payroll=quantize_money(payroll), mandatory_cost=rules.mandatory_setup_cost(seg, channel, body.size),
        mandatory_roles=[seg.role(r).label for r in mandatory], expected_units=round(rules.expected_units(seg, location, body.size), 1),
        first_month_units=round(rules.expected_units(seg, location, body.size) * rules.relevance_factor(0), 1),
        operating_reserve=rules.operating_reserve(seg, location, body.size, channel, site_mode), reserve_months=int(rules.RESERVE_MONTHS),
        max_staff=rules.SIZES[body.size].max_staff)


@router.get("/acquisitions")
def acquisitions(user: CurrentUser, db: DbSession):
    """Empresas à venda no mês (todos os portes e países) e as suas negociações."""
    def go():
        m = bs.ensure_setup(db, user.id)
        return acq.view(db, user.id, m.ref_month)
    return _run(db, go)


@router.post("/acquisitions/negotiate")
def acquisition_negotiate(body: s.AcquisitionOfferIn, user: CurrentUser, db: DbSession):
    """Faz uma oferta pela empresa: o dono aceita, contrapropõe, recusa ou desiste. MERGE incorpora; KEEP cria empresa separada."""
    def go():
        m = bs.ensure_setup(db, user.id)
        res = acq.negotiate(db, user.id, m, body.target_key, body.offer, body.mode, body.buyer_company_id, body.name)
        return {**res, **acq.view(db, user.id, m.ref_month)}
    return _run(db, go)


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
                              owner_share_pct=body.owner_share_pct, partner_invite_ids=body.partner_invite_ids, country=body.country)
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
        rows = cs.list_candidates(db, user.id, month, company_id, body.role, body.regime, body.country)
        return s.CandidatesOut(role=body.role, regime=body.regime, month=month.ref_month, candidates=[_candidate_out(x, seg) for x in rows])
    return _run(db, go)


@router.post("/{company_id}/hire", response_model=s.HireOut)
def hire(company_id: int, body: s.HireIn, user: CurrentUser, db: DbSession):
    """Faz a proposta: o candidato aceita, recusa (fica indisponível no mês) ou devolve uma contraproposta."""
    def go():
        month = bs.ensure_setup(db, user.id)
        res = cs.hire(db, user.id, month, company_id, candidate_id=body.candidate_id, salary=body.salary, hours_week=body.hours_week,
                      schedule=body.schedule, regime=body.regime, confirm_risk=body.confirm_risk, idempotency_key=body.idempotency_key,
                      work_mode=body.work_mode, country=body.country)
        return s.HireOut(accepted=res.accepted, status=res.status, message=res.message, counter_offer=res.counter_offer,
                         company=_detail(db, cs.get_company(db, user.id, company_id)))
    return _run(db, go)


def _report(db: Session, user_id: int, company_id: int, rep: dict) -> s.RecruiterReportOut:
    return s.RecruiterReportOut(**rep, company=_detail(db, cs.get_company(db, user_id, company_id)))


@router.post("/{company_id}/aides/{kind}", response_model=s.CompanyDetailOut)
def aide_hire(company_id: int, kind: str, body: s.AideHireIn, user: CurrentUser, db: DbSession):
    """Contrata (ou troca o nível d)o marketeiro (MARKETER) ou gerente (MANAGER): baixo, médio ou alto nível. Taxa mensal no fechamento."""
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: aidesvc.hire(db, user.id, m, company_id, kind, body.level)))


@router.delete("/{company_id}/aides/{kind}", response_model=s.CompanyDetailOut)
def aide_dismiss(company_id: int, kind: str, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: aidesvc.dismiss(db, user.id, m, company_id, kind)))


@router.put("/{company_id}/aides/{kind}/briefing", response_model=s.CompanyDetailOut)
def aide_briefing(company_id: int, kind: str, body: s.AideBriefingIn, user: CurrentUser, db: DbSession):
    """Briefing: marketeiro = orçamento mensal; gerente = rigidez (0 a 100; alta rende mais, mas funcionários podem se demitir)."""
    raw = {k: v for k, v in (("monthly_budget", str(body.monthly_budget) if body.monthly_budget is not None else None), ("rigor", body.rigor)) if v is not None}
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: aidesvc.update_briefing(db, user.id, m, company_id, kind, raw)))


@router.post("/{company_id}/franchise/advertise", response_model=s.CompanyDetailOut)
def franchise_advertise(company_id: int, body: s.FranchiseAdIn, user: CurrentUser, db: DbSession):
    """Publicidade da franquia: atrai franqueados (difícil: exige marca relevante; o efeito decai todo mês)."""
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: franchise_svc.advertise(db, user.id, m, company_id, body.tier, body.idempotency_key)))


@router.post("/{company_id}/ipo", response_model=s.CompanyDetailOut)
def ipo_apply(company_id: int, body: s.IpoApplyIn, user: CurrentUser, db: DbSession):
    """Pede a abertura de capital (IPO): exige empresa madura e lucrativa; leva 3 meses."""
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: ipo_svc.apply(db, user.id, m, company_id, body.float_pct, body.idempotency_key)))


@router.post("/{company_id}/ipo/sell", response_model=s.CompanyDetailOut)
def ipo_sell(company_id: int, body: s.StakeIn, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: ipo_svc.sell_stake(db, user.id, m, company_id, body.pct, body.idempotency_key)))


@router.post("/{company_id}/ipo/buyback", response_model=s.CompanyDetailOut)
def ipo_buyback(company_id: int, body: s.StakeIn, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: ipo_svc.buy_back(db, user.id, m, company_id, body.pct, body.idempotency_key)))


@router.post("/{company_id}/recruiter", response_model=s.CompanyDetailOut)
def recruiter_hire(company_id: int, body: s.RecruiterHireIn, user: CurrentUser, db: DbSession):
    """Contrata o contratador (headhunter) no nível pedido ou troca o nível. Opcional; taxa mensal no fechamento."""
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: recsvc.hire_recruiter(db, user.id, m, company_id, body.tier, body.idempotency_key)))


@router.delete("/{company_id}/recruiter", response_model=s.CompanyDetailOut)
def recruiter_dismiss(company_id: int, user: CurrentUser, db: DbSession):
    """Dispensa o contratador (sem multa)."""
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: recsvc.dismiss_recruiter(db, user.id, m, company_id)))


@router.put("/{company_id}/recruiter/settings", response_model=s.CompanyDetailOut)
def recruiter_settings(company_id: int, body: s.RecruiterSettingsIn, user: CurrentUser, db: DbSession):
    """Briefing do contratador: salário máximo, escala, regime, teto de folha extra e critérios de fornecedores (geral e por categoria)."""
    raw = body.model_dump(mode="json")
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: recsvc.update_briefing(db, user.id, m, company_id, raw)))


@router.post("/{company_id}/recruiter/hire-mandatory", response_model=s.RecruiterReportOut)
def recruiter_hire_mandatory(company_id: int, body: s.RecruiterKeyIn, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        return _report(db, user.id, company_id, recsvc.hire_mandatory(db, user.id, month, company_id, body.idempotency_key))
    return _run(db, go)


@router.post("/{company_id}/recruiter/hire-team", response_model=s.RecruiterReportOut)
def recruiter_hire_team(company_id: int, body: s.RecruiterTeamIn, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        return _report(db, user.id, company_id, recsvc.hire_team(
            db, user.id, month, company_id, [r.model_dump() for r in body.roles], body.idempotency_key))
    return _run(db, go)


@router.post("/{company_id}/recruiter/contract-suppliers", response_model=s.RecruiterReportOut)
def recruiter_contract_suppliers(company_id: int, body: s.RecruiterSuppliersIn, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        return _report(db, user.id, company_id, recsvc.contract_suppliers(
            db, user.id, month, company_id, body.categories, body.idempotency_key))
    return _run(db, go)


@router.delete("/{company_id}/employees/{employee_id}", response_model=s.CompanyDetailOut)
def fire(company_id: int, employee_id: int, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: cs.fire(db, user.id, m, company_id, employee_id)))


@router.post("/{company_id}/stock", response_model=s.CompanyDetailOut, status_code=status.HTTP_201_CREATED)
def buy_stock(company_id: int, body: s.StockIn, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: cs.buy_stock(db, user.id, m, company_id, body.item_id, body.quantity, body.idempotency_key)))


def _offer_out(o: supply.SupplierOffer, seg: rules.Segment) -> s.SupplierOfferOut:
    cat = seg.supply(o.category)
    return s.SupplierOfferOut(
        id=o.id, category=o.category, category_label=cat.label, unit=cat.unit, name=o.name, unit_price=o.unit_price,
        reference_price=o.reference_price, price_vs_reference_pct=round(float(o.unit_price / o.reference_price - 1) * 100, 1),
        min_monthly_order=o.min_monthly_order, max_units_month=o.max_units_month, reliability=o.reliability, lead_days=o.lead_days)


@router.post("/{company_id}/suppliers/search", response_model=s.SupplierSearchOut)
def suppliers_search(company_id: int, body: s.SupplierSearchIn, user: CurrentUser, db: DbSession):
    """Fornecedores do mês para a categoria (3 a 5, determinísticos: mesma consulta, mesma lista). O id é um token recalculado no servidor."""
    def go():
        month = bs.ensure_setup(db, user.id)
        offers = cs.search_suppliers(db, user.id, month, company_id, body.category)
        seg = rules.SEGMENTS[cs.get_company(db, user.id, company_id).segment]
        return s.SupplierSearchOut(category=body.category, month=month.ref_month, offers=[_offer_out(o, seg) for o in offers])
    return _run(db, go)


@router.post("/{company_id}/suppliers/negotiate", response_model=s.SupplierNegotiateOut)
def suppliers_negotiate(company_id: int, body: s.SupplierNegotiateIn, user: CurrentUser, db: DbSession):
    """Propõe um preço: o fornecedor aceita (cria o contrato), recusa (indisponível no mês) ou contrapõe."""
    def go():
        month = bs.ensure_setup(db, user.id)
        res = cs.negotiate_supplier(db, user.id, month, company_id, supplier_id=body.supplier_id, unit_price=body.unit_price,
                                    monthly_volume=body.monthly_volume, idempotency_key=body.idempotency_key)
        return s.SupplierNegotiateOut(accepted=res.accepted, status=res.status, message=res.message, counter_offer=res.counter_offer,
                                      company=_detail(db, cs.get_company(db, user.id, company_id)))
    return _run(db, go)


@router.delete("/{company_id}/suppliers/{supplier_id}", response_model=s.CompanyDetailOut)
def suppliers_end(company_id: int, supplier_id: int, user: CurrentUser, db: DbSession):
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: cs.end_supplier(db, user.id, m, company_id, supplier_id)))


@router.put("/{company_id}/suppliers/{supplier_id}/limits", response_model=s.CompanyDetailOut)
def suppliers_limits(company_id: int, supplier_id: int, body: s.SupplierLimitsIn, user: CurrentUser, db: DbSession):
    """Limites do contrato: gasto e volume mensais (valem nas compras) e confiabilidade/prazo (critérios do contratador)."""
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: cs.set_supplier_limits(
        db, user.id, m, company_id, supplier_id, max_monthly_spend=body.max_monthly_spend, min_reliability=body.min_reliability,
        max_lead_days=body.max_lead_days, volume_cap=body.volume_cap)))


@router.post("/{company_id}/relocate/quote", response_model=s.RelocateQuoteOut)
def relocate_quote(company_id: int, body: s.RelocateQuoteIn, user: CurrentUser, db: DbSession):
    """Quanto custaria mudar de endereço (não altera nada)."""
    def go():
        bs.ensure_setup(db, user.id)
        c = cs.get_company(db, user.id, company_id)
        q = cs.relocation_quote(db, c, location=body.location, site_mode=body.site_mode, size=body.size)
        seg = rules.SEGMENTS[c.segment]
        return s.RelocateQuoteOut(location_label=rules.resolve_location(seg, q["location"]).label, **q)
    return _run(db, go)


@router.post("/{company_id}/relocate", response_model=s.CompanyDetailOut)
def relocate(company_id: int, body: s.RelocateIn, user: CurrentUser, db: DbSession):
    """Mudança de endereço (só empresas físicas): cobra a mudança, troca terreno/aluguel, mantém a equipe e perde parte da relevância."""
    return _run(db, lambda: _act(db, user.id, company_id, lambda m: cs.relocate(
        db, user.id, m, company_id, location=body.location, site_mode=body.site_mode, size=body.size, idempotency_key=body.idempotency_key)))


@router.post("/{company_id}/expansion/options", response_model=s.ExpansionOptionsOut)
def expansion_options(company_id: int, body: s.ExpansionOptionsIn, user: CurrentUser, db: DbSession):
    """3 opções SORTEADAS (determinísticas por empresa, semente, mês, tipo e nível) para o aporte escolhido. Não altera nada."""
    def go():
        month = bs.ensure_setup(db, user.id)
        c = cs.get_company(db, user.id, company_id)
        cs._active(c)
        views = xp.option_views(cs._seed(db, user.id), c, month.ref_month, body.kind, body.tier)
        return s.ExpansionOptionsOut(
            kind=body.kind, tier=body.tier, tier_label=rules.TIER_LABEL[body.tier], tier_cost=xp.base_cost(c, body.kind, body.tier),
            ref_month=month.ref_month, options=[s.ExpansionOptionOut(**v.__dict__) for v in views],
            sites=[s.ExpansionSiteOut(**x) for x in xp.sites(c)] if body.kind == "NEW_UNIT" else [])
    return _run(db, go)


@router.post("/{company_id}/expansion/execute", response_model=s.ExpansionResultOut)
def expansion_execute(company_id: int, body: s.ExpansionExecuteIn, user: CurrentUser, db: DbSession):
    """Cobra e resolve o aporte (resultado probabilístico determinístico). O servidor recalcula as 3 opções do mês: `option_key`
    fora delas é recusada. Nova unidade exige canal/terreno/local. Idempotente por `idempotency_key`."""
    def go():
        month = bs.ensure_setup(db, user.id)
        r = xp.execute(db, user.id, month, company_id, kind=body.kind, tier=body.tier, option_key=body.option_key,
                       idempotency_key=body.idempotency_key, channel=body.channel, site_mode=body.site_mode, location=body.location)
        return s.ExpansionResultOut(success=r.success, outcome=r.outcome, message=r.message, effects=r.effects, cost=r.cost,
                                    replayed=r.replayed, company=_detail(db, cs.get_company(db, user.id, company_id)))
    return _run(db, go)


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


@router.post("/{company_id}/goods/build", response_model=s.CompanyDetailOut, status_code=status.HTTP_201_CREATED)
def build_good(company_id: int, body: s.CompanyBuildIn, user: CurrentUser, db: DbSession):
    """A empresa CONSTRÓI um imóvel próprio (3 a 6 meses de obra; pago à vista do caixa da empresa)."""
    def fn(month):
        c = cs.get_company(db, user.id, company_id, lock=True)
        cs._active(c)
        goods_service.build(db, user.id, month, plan_key=body.plan_key, city_key=body.city_key, purchase_key=body.idempotency_key, company=c)
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
