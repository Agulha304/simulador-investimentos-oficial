"""Progressão e integração geral (etapa 6): partida (livre/carreira), objetivos, conquistas, relatórios e painel.

Tudo é calculado a partir dos dados reais dos outros módulos (carteira, ledger, bens, empresas, vida, economia).
`on_month_closed` é chamado no fim do fechamento mensal, na MESMA transação: se algo falhar, o mês inteiro desfaz.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import (
    Achievement, BudgetCategory, BudgetItem, Child, Company, CompanyEvent, CompanyEventType, CompanyLoan, CompanyMonth, CompanyStatus,
    Employee, EmployeeStatus, EntryOrigin, FlowKind, Good, GoodStatus, Goal, LedgerEntry, LifeLog, LifeProfile, Loan,
    LoanStatus, MonthReport, MonthStatus, Person, Portfolio, REAL_ESTATE, Relationship, SimMonth, Transaction,
    TransactionSource, TransactionType, WorldEvent,
)
from backend.services import budget_service, economy_service, finance_ledger, ledger_service, life_service, portfolio_service, wealth_service
from backend.services import progression_rules as P
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError

ZERO = Decimal("0.00")
D = Decimal


# ------------------------------------------------------------------ métricas (fonte única para metas, conquistas e painel)
def _company_loans(db: Session, user_id: int) -> Decimal:
    return db.scalar(select(func.coalesce(func.sum(CompanyLoan.balance), 0)).join(Company, Company.id == CompanyLoan.company_id).where(
        Company.user_id == user_id, CompanyLoan.status == LoanStatus.ACTIVE)) or ZERO


def _streak(values: list[bool]) -> int:
    n = 0
    for v in reversed(values):
        if not v:
            break
        n += 1
    return n


def metrics(db: Session, user_id: int, ref: date, closed: SimMonth | None = None) -> dict:
    portfolio = db.scalar(select(Portfolio).where(Portfolio.user_id == user_id))
    summary = portfolio_service.build_summary(db, portfolio)
    personal_ids = finance_ledger.personal_account(db, user_id).id
    expense_ref = (closed.total_expense if closed is not None and closed.total_expense else None)
    if expense_ref is None:
        expense_ref = db.scalar(select(func.coalesce(func.sum(SimMonth.total_expense), 0)).where(
            SimMonth.user_id == user_id, SimMonth.ref_month == budget_service.shift_month(ref, -1))) or ZERO
    if not expense_ref:        # sem histórico: usa as despesas planejadas do mês aberto (sem base, não há reserva medida)
        expense_ref = db.scalar(select(func.coalesce(func.sum(BudgetItem.planned_amount), 0)).join(
            SimMonth, SimMonth.id == BudgetItem.month_id).where(
            BudgetItem.user_id == user_id, BudgetItem.kind == FlowKind.EXPENSE, BudgetItem.capital.is_(False),
            SimMonth.status == MonthStatus.OPEN)) or ZERO
    emergency = float(portfolio.cash_balance / expense_ref) if expense_ref and expense_ref > 0 else 0.0
    passive = db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount), 0)).join(
        BudgetCategory, BudgetCategory.id == LedgerEntry.category_id).where(
        LedgerEntry.user_id == user_id, LedgerEntry.ref_month == ref, LedgerEntry.kind == FlowKind.INCOME,
        LedgerEntry.company_id.is_(None), BudgetCategory.name.in_(("Aluguéis recebidos", "Rendimentos")))) or ZERO
    companies = list(db.scalars(select(Company).where(Company.user_id == user_id, Company.status == CompanyStatus.ACTIVE)))
    cm_rows = list(db.execute(select(CompanyMonth.ref_month, func.sum(CompanyMonth.revenue), func.sum(CompanyMonth.net_result)).join(
        Company, Company.id == CompanyMonth.company_id).where(Company.user_id == user_id, CompanyMonth.ref_month <= ref)
        .group_by(CompanyMonth.ref_month).order_by(CompanyMonth.ref_month)))
    revenue = next((r[1] for r in cm_rows if r[0] == ref), ZERO) or ZERO
    # sequência de meses consecutivos lucrativos terminando em `ref`
    profit_seq, cursor = [], ref
    by_month = {r[0]: r[2] for r in cm_rows}
    while cursor in by_month:
        profit_seq.append(by_month[cursor] > 0)
        cursor = budget_service.shift_month(cursor, -1)
    profit_seq.reverse()
    closed_months = list(db.scalars(select(SimMonth).where(
        SimMonth.user_id == user_id, SimMonth.status == MonthStatus.CLOSED).order_by(SimMonth.ref_month)))
    prof = life_service.get_profile(db, user_id, create=False)
    kids = life_service.children(db, user_id) if prof else []
    partner = life_service.active_partner(db, user_id) if prof else None
    edu_months = {e for e in db.scalars(select(LedgerEntry.ref_month).where(
        LedgerEntry.user_id == user_id, LedgerEntry.origin == EntryOrigin.FAMILY, LedgerEntry.origin_ref.like("child:%:education")))}
    edu_seq, cursor = [], ref
    while cursor in edu_months:
        edu_seq.append(True)
        cursor = budget_service.shift_month(cursor, -1)
    employees = db.scalar(select(func.count(Employee.id)).join(Company, Company.id == Employee.company_id).where(
        Company.user_id == user_id, Employee.status == EmployeeStatus.ACTIVE)) or 0
    real_estate = db.scalar(select(func.count(Good.id)).where(
        Good.user_id == user_id, Good.status == GoodStatus.ACTIVE, Good.category.in_(REAL_ESTATE),
        Good.owner_account_id == personal_ids)) or 0
    invested = summary.market_value_brl + summary.fixed_income_value_brl
    return {
        "cash": portfolio.cash_balance, "net_worth": summary.total_equity_brl, "invested": quantize_money(invested),
        "debts": quantize_money(wealth_service.debts(db, user_id) + _company_loans(db, user_id)),
        "emergency_months": round(emergency, 2), "passive_income": quantize_money(passive),
        "real_estate": real_estate, "companies": len(companies), "company_revenue": quantize_money(revenue),
        "employees": employees, "units": sum(c.units for c in companies), "profit_streak": _streak(profit_seq),
        "positive_streak": _streak([m.total_income > m.total_expense for m in closed_months]),
        "quality": prof.quality if prof else 50, "wellbeing": prof.wellbeing if prof else 50,
        "family_members": 1 + (1 if partner and partner.stage in ("COHABITING", "MARRIED") else 0) + len(kids),
        "work_life": 1 if prof and prof.wellbeing >= 65 and prof.work_level != "INTENSE" else 0,
        "education_streak": _streak(edu_seq), "children": len(kids),
        "companies_positive": any(profit_seq[-1:]) if profit_seq else False,
    }


# ------------------------------------------------------------------ objetivos
def _goal_from(db: Session, user_id: int, month: SimMonth, g: P.GoalDef, origin: str) -> Goal | None:
    if db.scalar(select(Goal.id).where(Goal.user_id == user_id, Goal.key == g.key)):
        return None
    goal = Goal(user_id=user_id, key=g.key, kind=g.kind, title=g.title, description=g.description, metric=g.metric,
                comparator=g.comparator, target=D(str(g.target)), sustain_months=g.sustain, origin=origin,
                created_month=month.ref_month)
    db.add(goal)
    db.flush()
    return goal


def create_goal(db: Session, user_id: int, month: SimMonth, *, template: str, target: Decimal | None = None,
                sustain_months: int | None = None) -> Goal:
    t = P.GOAL_TEMPLATES.get(template)
    if t is None:
        raise FinanceError("modelo de objetivo desconhecido")
    kind, title, metric, comp, default_target, default_sustain = t
    tgt = D(str(target if target is not None else default_target))
    sustain = sustain_months or default_sustain
    if not 1 <= sustain <= 60 or tgt < 0:
        raise FinanceError("alvo ou prazo de sustentação inválido")
    cur = metrics(db, user_id, month.ref_month)
    if metric == "debts" and cur["debts"] <= 0:
        raise FinanceError("você não tem dívidas: esse objetivo seria concluído sem esforço")
    key = f"{template}:{tgt.normalize():f}"
    gd = P.GoalDef(key, kind, f"{title}: {tgt.normalize():f}" if tgt else title, "", metric, float(tgt), sustain, comp)
    g = _goal_from(db, user_id, month, gd, "USER")
    if g is None:
        raise ConflictError("você já tem esse objetivo")
    return g


def evaluate_goals(db: Session, user_id: int, ref: date, m: dict) -> list[Goal]:
    done = []
    for g in db.scalars(select(Goal).where(Goal.user_id == user_id, Goal.status == "ACTIVE").with_for_update()):
        if g.last_eval_month == ref:
            continue
        value = m.get(g.metric, 0)
        value = D(str(value))
        g.current = quantize_money(value)
        ok = value >= g.target if g.comparator == "GTE" else value <= g.target
        g.streak = g.streak + 1 if ok else 0
        g.last_eval_month = ref
        if g.streak >= g.sustain_months:
            g.status, g.done_month = "DONE", ref
            done.append(g)
    db.flush()
    return done


def goal_out(g: Goal) -> dict:
    return {"id": g.id, "key": g.key, "kind": g.kind, "title": g.title, "description": g.description, "metric": g.metric,
            "metric_label": P.METRIC_LABEL.get(g.metric, g.metric), "comparator": g.comparator, "target": str(g.target),
            "current": str(g.current), "streak": g.streak, "sustain_months": g.sustain_months, "status": g.status,
            "origin": g.origin, "progress": round(min(1.0, g.streak / g.sustain_months), 3),
            "done_month": g.done_month.isoformat() if g.done_month else None}


# ------------------------------------------------------------------ conquistas (verificadas sobre o HISTÓRICO)
def _exists(db: Session, q) -> bool:
    return db.scalar(q.limit(1)) is not None


def achievement_checks(db: Session, user_id: int, m: dict) -> dict[str, bool]:
    pid = db.scalar(select(Portfolio.id).where(Portfolio.user_id == user_id))
    reports = list(db.scalars(select(MonthReport).where(MonthReport.user_id == user_id)))
    return {
        "first_investment": _exists(db, select(Transaction.id).where(
            Transaction.portfolio_id == pid, Transaction.type.in_((TransactionType.BUY, TransactionType.FIXED_INCOME_APPLY)))),
        "first_property": _exists(db, select(Good.id).where(Good.user_id == user_id, Good.category.in_(REAL_ESTATE))),
        "first_company": _exists(db, select(Company.id).where(Company.user_id == user_id)),
        "first_employee": _exists(db, select(Employee.id).join(Company, Company.id == Employee.company_id).where(Company.user_id == user_id)),
        "first_positive_month": _exists(db, select(SimMonth.id).where(
            SimMonth.user_id == user_id, SimMonth.status == MonthStatus.CLOSED, SimMonth.total_income > SimMonth.total_expense)),
        "first_debt_paid": _exists(db, select(Loan.id).where(Loan.user_id == user_id, Loan.status == LoanStatus.PAID)) or
        _exists(db, select(CompanyLoan.id).join(Company, Company.id == CompanyLoan.company_id).where(
            Company.user_id == user_id, CompanyLoan.status == LoanStatus.PAID)),
        "first_million": m["net_worth"] >= P.MILLION or any(r.data.get("net_worth", 0) >= P.MILLION for r in reports),
        "company_expanded": _exists(db, select(CompanyEvent.id).join(Company, Company.id == CompanyEvent.company_id).where(
            Company.user_id == user_id, CompanyEvent.type == CompanyEventType.EXPANSION)),
        "first_distribution": _exists(db, select(LedgerEntry.id).where(LedgerEntry.user_id == user_id, LedgerEntry.line == "DISTRIBUTION")),
        "emergency_reserve": m["emergency_months"] >= 6 or any(r.data.get("metrics", {}).get("emergency_months", 0) >= 6 for r in reports),
        "first_partner": _exists(db, select(LifeLog.id).where(LifeLog.user_id == user_id, LifeLog.kind == "DATING")) or
        _exists(db, select(Relationship.id).where(Relationship.user_id == user_id, Relationship.stage.in_(("DATING", "COHABITING", "MARRIED")))),
        "married": _exists(db, select(LifeLog.id).where(LifeLog.user_id == user_id, LifeLog.kind == "MARRIED")) or
        _exists(db, select(Relationship.id).where(Relationship.user_id == user_id, Relationship.stage == "MARRIED")),
        "first_child": _exists(db, select(Child.id).where(Child.user_id == user_id)),
        "first_goal": _exists(db, select(Goal.id).where(Goal.user_id == user_id, Goal.status == "DONE")),
    }


def evaluate_achievements(db: Session, user_id: int, ref: date, m: dict) -> list[str]:
    have = set(db.scalars(select(Achievement.key).where(Achievement.user_id == user_id)))
    new = []
    for key, ok in achievement_checks(db, user_id, m).items():
        if ok and key not in have:
            db.add(Achievement(user_id=user_id, key=key, unlocked_month=ref))
            new.append(key)
    db.flush()
    return new


def achievements_out(db: Session, user_id: int) -> list[dict]:
    got = {a.key: a for a in db.scalars(select(Achievement).where(Achievement.user_id == user_id))}
    return [{"key": k, "name": n, "description": d, "unlocked": k in got,
             "unlocked_month": got[k].unlocked_month.isoformat() if k in got else None} for k, (n, d) in P.ACHIEVEMENTS.items()]


# ------------------------------------------------------------------ relatórios
def _num(x) -> float:
    return float(x)


def build_month_report(db: Session, user_id: int, closed: SimMonth, nxt: SimMonth, m: dict, new_achievements: list[str],
                       done_goals: list[Goal]) -> MonthReport:
    ref = closed.ref_month
    prev = db.scalar(select(MonthReport).where(
        MonthReport.user_id == user_id, MonthReport.ref_month == budget_service.shift_month(ref, -1)))
    game = economy_service.get_game(db, user_id)
    baseline = (prev.data["net_worth"] if prev else (game.config or {}).get("initial_net_worth"))
    entries = list(db.execute(select(LedgerEntry.kind, LedgerEntry.origin, LedgerEntry.company_id, LedgerEntry.capital,
                                     BudgetCategory.name, func.sum(LedgerEntry.amount)).outerjoin(
        BudgetCategory, BudgetCategory.id == LedgerEntry.category_id).where(
        LedgerEntry.user_id == user_id, LedgerEntry.ref_month == ref)
        .group_by(LedgerEntry.kind, LedgerEntry.origin, LedgerEntry.company_id, LedgerEntry.capital, BudgetCategory.name)))
    by_cat: dict[str, float] = {}
    family_exp = personal_exp = 0.0
    for kind, origin, company_id, capital, cat, total in entries:
        if company_id is None and kind == FlowKind.EXPENSE and not capital:
            by_cat[cat or "Outros"] = by_cat.get(cat or "Outros", 0.0) + _num(total)
            if origin == EntryOrigin.FAMILY:
                family_exp += _num(total)
            else:
                personal_exp += _num(total)
    companies = [{"company_id": c.id, "name": c.name, "revenue": _num(cm.revenue), "net_result": _num(cm.net_result)}
                 for cm, c in db.execute(select(CompanyMonth, Company).join(Company, Company.id == CompanyMonth.company_id).where(
                     Company.user_id == user_id, CompanyMonth.ref_month == ref).order_by(Company.id))]
    family_changes = [{"kind": l.kind, "text": l.text} for l in db.scalars(select(LifeLog).where(
        LifeLog.user_id == user_id, LifeLog.ref_month.in_((ref, nxt.ref_month))).order_by(LifeLog.id))]
    events = [{"name": e.name, "category": e.category, "status": e.status, "start": e.start_month.isoformat(),
               "end": e.end_month.isoformat()} for e in db.scalars(select(WorldEvent).where(
                   WorldEvent.user_id == user_id, WorldEvent.start_month.in_((ref, nxt.ref_month))).order_by(WorldEvent.id))]
    st = economy_service.get_state(db, user_id, ref)
    prof = life_service.get_profile(db, user_id, create=False)
    income, expense = _num(closed.total_income), _num(closed.total_expense)
    cpi = float(economy_service.index_value(db, user_id, ref, "geral"))                  # custo de vida (base 1 no início)
    wage_idx = float(economy_service.index_value(db, user_id, ref, "salarios"))
    real = {"cpi": round(cpi, 6), "purchasing_power": round(1 / cpi, 6) if cpi else 1.0, "income_real": round(income / cpi, 2),
            "expense_real": round(expense / cpi, 2), "net_worth_real": round(_num(m["net_worth"]) / cpi, 2),
            "wage_index": round(wage_idx, 6), "cost_of_living_12m": round(_num(st.inflation), 2) if st else None}
    data = {"real": real,
        "month": ref.isoformat(), "income": income, "expense": expense, "result": round(income - expense, 2),
        "invested": _num(closed.invested), "closing_balance": _num(closed.closing_balance),
        "net_worth": _num(m["net_worth"]), "net_worth_open": _num(baseline) if baseline is not None else None,
        "net_worth_change": round(_num(m["net_worth"]) - _num(baseline), 2) if baseline is not None else None,
        "debts": _num(m["debts"]), "expense_by_category": {k: round(v, 2) for k, v in sorted(by_cat.items())},
        "family_expense": round(family_exp, 2), "personal_expense": round(personal_exp, 2),
        "companies": companies, "company_profit": round(sum(c["net_result"] for c in companies), 2),
        "family_changes": family_changes, "events": events,
        "economy": ({"inflation": _num(st.inflation), "interest": _num(st.interest), "unemployment": _num(st.unemployment),
                     "growth": _num(st.growth), "demand": _num(st.demand), "confidence": _num(st.confidence)} if st else None),
        "attributes": ({"health": prof.health, "wellbeing": prof.wellbeing, "quality": prof.quality,
                        "satisfaction": prof.satisfaction, "social": prof.social} if prof else None),
        "achievements": [{"key": k, "name": P.ACHIEVEMENTS[k][0]} for k in new_achievements],
        "goals_done": [{"key": g.key, "title": g.title} for g in done_goals],
        "metrics": {k: (_num(v) if isinstance(v, Decimal) else v) for k, v in m.items()},
    }
    rep = MonthReport(user_id=user_id, ref_month=ref, data=data)
    db.add(rep)
    db.flush()
    return rep


def annual_report(db: Session, user_id: int, year: int) -> dict:
    reps = list(db.scalars(select(MonthReport).where(
        MonthReport.user_id == user_id, MonthReport.ref_month >= date(year, 1, 1), MonthReport.ref_month <= date(year, 12, 1))
        .order_by(MonthReport.ref_month)))
    if not reps:
        raise NotFoundError("nenhum mês fechado neste ano")
    d = [r.data for r in reps]
    first, last = d[0], d[-1]
    start_nw = first["net_worth_open"] if first.get("net_worth_open") is not None else round(first["net_worth"] - first["result"], 2)
    attrs0, attrs1 = first.get("attributes"), last.get("attributes")
    return {
        "year": year, "months": len(d), "complete": len(d) == 12,
        "net_worth_start": start_nw, "net_worth_end": last["net_worth"], "net_worth_change": round(last["net_worth"] - start_nw, 2),
        "income": round(sum(x["income"] for x in d), 2), "expense": round(sum(x["expense"] for x in d), 2),
        "invested": round(sum(x["invested"] for x in d), 2), "company_profit": round(sum(x["company_profit"] for x in d), 2),
        "debts_start": first["debts"], "debts_end": last["debts"],
        "personal_change": ({k: attrs1[k] - attrs0[k] for k in attrs1} if attrs0 and attrs1 else None),
        "attributes_end": attrs1,
        "events": [{**e, "month": x["month"]} for x in d for e in x["events"] if e["category"] == "ECONOMIC" or e["status"] != "PENDING"][:60],
        "family_changes": [{**c, "month": x["month"]} for x in d for c in x["family_changes"]
                           if c["kind"] in ("BIRTH", "MARRIED", "MOVED", "COHABITING", "DATING", "ENDED", "EMANCIPATED")],
        "achievements": [a for x in d for a in x["achievements"]], "goals_done": [g for x in d for g in x["goals_done"]],
        "monthly": [{"month": x["month"], "income": x["income"], "expense": x["expense"], "result": x["result"],
                     "net_worth": x["net_worth"]} for x in d],
        "real": ({"income_real": round(sum(x["real"]["income_real"] for x in d), 2), "expense_real": round(sum(x["real"]["expense_real"] for x in d), 2),
                  "cpi_start": d[0]["real"]["cpi"], "cpi_end": d[-1]["real"]["cpi"],
                  "cost_of_living_change_pct": round((d[-1]["real"]["cpi"] / d[0]["real"]["cpi"] - 1) * 100, 2),
                  "purchasing_power_end": d[-1]["real"]["purchasing_power"], "net_worth_real_end": d[-1]["real"]["net_worth_real"],
                  "wage_index_change_pct": round((d[-1]["real"]["wage_index"] / d[0]["real"]["wage_index"] - 1) * 100, 2)}
                 if all("real" in x for x in d) else None),
    }


def on_month_closed(db: Session, user_id: int, closed: SimMonth, nxt: SimMonth) -> None:
    """Fim do fechamento (mesma transação): metas, conquistas e retrato do mês."""
    from backend.core.clock import get_clock
    from datetime import UTC, datetime
    clock = get_clock()
    if clock is not None:                      # foto do patrimônio na data simulada (gráfico de desempenho da partida)
        portfolio = db.scalar(select(Portfolio).where(Portfolio.user_id == user_id))
        from backend.services import performance_service
        when = datetime.combine(nxt.ref_month, datetime.min.time(), tzinfo=UTC)
        if not db.scalar(select(performance_service.PortfolioSnapshot.id).where(
                performance_service.PortfolioSnapshot.portfolio_id == portfolio.id, performance_service.PortfolioSnapshot.taken_at == when)):
            performance_service.take_snapshot(db, portfolio_service.load_portfolio(db, portfolio.id), when)
    if db.scalar(select(MonthReport.id).where(MonthReport.user_id == user_id, MonthReport.ref_month == closed.ref_month)):
        return
    m = metrics(db, user_id, closed.ref_month, closed)
    done = evaluate_goals(db, user_id, closed.ref_month, m)
    new = evaluate_achievements(db, user_id, closed.ref_month, m)
    build_month_report(db, user_id, closed, nxt, m, new, done)


def refresh_open_month(db: Session, user_id: int, month: SimMonth) -> list[str]:
    """Registra conquistas já alcançadas no mês aberto (ex.: primeiro investimento) sem esperar o fechamento."""
    return evaluate_achievements(db, user_id, month.ref_month, metrics(db, user_id, month.ref_month))


# ------------------------------------------------------------------ início de partida
def _fresh(db: Session, user_id: int, month: SimMonth) -> bool:
    pid = db.scalar(select(Portfolio.id).where(Portfolio.user_id == user_id))
    others = db.scalar(select(func.count(Transaction.id)).where(
        Transaction.portfolio_id == pid, Transaction.type != TransactionType.DEPOSIT)) or 0
    closed = db.scalar(select(func.count(SimMonth.id)).where(SimMonth.user_id == user_id, SimMonth.status == MonthStatus.CLOSED)) or 0
    goods = db.scalar(select(func.count(Good.id)).where(Good.user_id == user_id)) or 0
    cos = db.scalar(select(func.count(Company.id)).where(Company.user_id == user_id)) or 0
    from backend.models import RecurringItem
    rec = db.scalar(select(func.count(RecurringItem.id)).where(RecurringItem.user_id == user_id)) or 0
    started = economy_service.get_game(db, user_id, create=False)
    return not (others or closed or goods or cos or rec) and not (started and started.started_month)


def _set_cash(db: Session, user_id: int, target: Decimal) -> None:
    portfolio = db.scalar(select(Portfolio).where(Portfolio.user_id == user_id))
    delta = quantize_money(target - portfolio.cash_balance)
    if delta > 0:
        ledger_service.deposit(db, portfolio.id, delta, source=TransactionSource.SYSTEM, idempotency_key=f"game-start:cash:{user_id}")
    elif delta < 0:
        ledger_service.record(db, portfolio.id, ledger_service.CashMovement(
            type=TransactionType.WITHDRAWAL, gross_amount_brl=-delta, cash_amount_brl=delta, source=TransactionSource.SYSTEM,
            idempotency_key=f"game-start:cash:{user_id}", note="Ajuste do caixa inicial da partida"))


def validate_free_config(cash: Decimal, salary: Decimal, expenses: list[P.Expense], rent: Decimal) -> None:
    """Combinações que quebrariam a simulação desde o primeiro mês são recusadas."""
    if cash < 0 or salary < 0 or rent < 0 or any(e.amount < 0 for e in expenses):
        raise FinanceError("valores iniciais não podem ser negativos")
    if cash > 50_000_000 or salary > 1_000_000:
        raise FinanceError("valores iniciais fora do limite do simulador")
    monthly_out = sum((D(e.amount) for e in expenses), ZERO) + rent
    if salary < monthly_out and cash < monthly_out * 6:
        raise FinanceError("com esta renda e este caixa as despesas não se sustentam nem por 6 meses: ajuste os valores iniciais")
    if salary > 0 and rent > salary * D("0.7") and cash < rent * 12:
        raise FinanceError("o aluguel consome mais de 70% da renda sem caixa para sustentá-lo: reduza o aluguel ou aumente o caixa")


def start_game(db: Session, user_id: int, *, mode: str, scenario_key: str | None = None, seed: int | None = None,
               name: str = "Você", free: dict | None = None, economy: dict | None = None, sim: dict | None = None,
               gender: str | None = None, interested_in: str | None = None, career_field: str | None = None) -> dict:
    if mode not in P.MODES:
        raise FinanceError("modo inválido (use FREE ou CAREER)")
    month = budget_service.ensure_setup(db, user_id)
    if not _fresh(db, user_id, month):
        raise ConflictError("esta conta já tem movimentação: só é possível iniciar uma partida em uma conta nova")
    free = free or {}
    if mode == "CAREER":
        sc = P.SCENARIOS.get(scenario_key or "")
        if sc is None:
            raise FinanceError("escolha um cenário válido")
        cash, salary, expenses, goals, age = D(sc.cash), D(sc.salary), list(sc.expenses), list(sc.goals), sc.age
        init_econ = {**sc.economy, **(economy or {})}
    else:
        scenario_key, sc = None, None
        cash = D(str(free.get("cash", 20000)))
        salary = D(str(free.get("monthly_income", 0)))
        base_exp = D(str(free.get("monthly_expenses", 0)))
        rent = D(str(free.get("rent", 0)))
        expenses = []
        if base_exp > 0:
            expenses = [P.Expense("Alimentação", "Alimentação", int(base_exp * D("0.35")), "alimentacao"),
                        P.Expense("Transporte", "Transporte", int(base_exp * D("0.15")), "transporte"),
                        P.Expense("Contas domésticas", "Contas domésticas", int(base_exp * D("0.2")), "energia"),
                        P.Expense("Outros", "Outras despesas", int(base_exp * D("0.3")))]
        if rent > 0:
            expenses.append(P.Expense("Moradia", "Aluguel", int(rent)))
        validate_free_config(cash, salary, [e for e in expenses if e.category != "Moradia"], rent)
        goals, age = [], int(free.get("age", 28))
        init_econ = dict(economy or {})
    from backend.services import career_rules
    career_field = career_field or career_rules.DEFAULT_FIELD
    if career_field not in career_rules.FIELDS:
        raise FinanceError("área de atuação inválida")
    if mode == "CAREER":                  # cenário: a área ajusta levemente o salário inicial (todas começam parecidas); no modo livre vale o valor digitado
        salary = (salary * D(str(career_rules.FIELDS[career_field]["start"]))).quantize(D("0.01"))
    seed = int(seed if seed is not None else user_id)
    _set_cash(db, user_id, cash)
    if salary > 0:
        budget_service.add_item(db, user_id, month, name="Salário", kind=FlowKind.INCOME,
                                category_id=_cat_id(db, user_id, FlowKind.INCOME, "Salário"),
                                planned_amount=salary, recurring=True)
    for e in expenses:
        if e.amount <= 0:
            continue
        bi = budget_service.add_item(db, user_id, month, name=e.name, kind=FlowKind.EXPENSE,
                                     category_id=_cat_id(db, user_id, FlowKind.EXPENSE, e.category),
                                     planned_amount=D(e.amount), recurring=True)
        if e.index:
            economy_service.set_indexation(db, user_id, bi.recurring_item_id, "MONTHLY", e.index)
    life_service.create_character(db, user_id, name=name, age_years=age, gender=gender, interested_in=interested_in)
    life_service.set_initial_field(db, user_id, month, career_field)
    if sc and sc.partner:
        _seed_family(db, user_id, month, sc)
    game = economy_service.get_game(db, user_id)
    game.mode, game.scenario_key, game.started_month = mode, scenario_key, month.ref_month
    economy_service.start_world(db, user_id, month, seed=seed, initial=init_econ, sim=sim)
    nw = portfolio_service.build_summary(db, db.scalar(select(Portfolio).where(Portfolio.user_id == user_id))).total_equity_brl
    game.config = {**(game.config or {}), "initial_net_worth": float(nw), "initial_cash": float(cash), "salary": float(salary),
                   "expenses": [e.amount for e in expenses]}
    for g in goals:
        _goal_from(db, user_id, month, g, "SCENARIO")
    life_service.sync_month(db, user_id, month)
    economy_service.sync_month(db, user_id, month)
    economy_service.ensure_monthly_decision(db, user_id, month)          # decisão do primeiro mês
    return {"mode": mode, "scenario": scenario_key, "seed": seed}


def _cat_id(db: Session, user_id: int, kind: FlowKind, name: str) -> int:
    from backend.services import item_sync
    return item_sync.category(db, user_id, kind, name).id


def _seed_family(db: Session, user_id: int, month: SimMonth, sc: P.Scenario) -> None:
    ref = month.ref_month
    p = sc.partner
    person = Person(user_id=user_id, name=p.get("name", "Parceiro(a)"), age=sc.age - 1, personality="tranquilo",
                    interests=["cultura", "natureza"], occupation="Analista", income=D(p["income"]), assets=D(p["assets"]),
                    debts=D(p["debts"]), sociability=55, wants_children=60, preferences={}, met_month=ref)
    db.add(person)
    db.flush()
    back = budget_service.shift_month(ref, -48)
    db.add(Relationship(user_id=user_id, person_id=person.id, stage=p["stage"], affinity=80, trust=75, since_month=back,
                        stage_since=back, finance_mode="SHARED", contribution_pct=D("40")))
    prof = life_service.get_profile(db, user_id)
    for i, age in enumerate(sc.children_ages):
        db.add(Child(user_id=user_id, name=["Alice", "Miguel", "Helena"][i % 3], birth_month=budget_service.shift_month(ref, -12 * age)))
    if sc.housing:
        prof.housing_kind, prof.housing_cost = sc.housing[0], D(sc.housing[1])
    db.flush()


# ------------------------------------------------------------------ painel geral
def dashboard(db: Session, user_id: int) -> dict:
    month = budget_service.ensure_setup(db, user_id)
    refresh_open_month(db, user_id, month)
    m = metrics(db, user_id, month.ref_month)
    summary = budget_service.summarize(db, user_id, month)
    game = economy_service.get_game(db, user_id)
    st = economy_service.get_state(db, user_id, month.ref_month)
    prof = life_service.get_profile(db, user_id, create=False)
    partner = life_service.active_partner(db, user_id) if prof else None
    companies = list(db.scalars(select(Company).where(Company.user_id == user_id, Company.status == CompanyStatus.ACTIVE)))
    goals = list(db.scalars(select(Goal).where(Goal.user_id == user_id).order_by(Goal.id)))
    pending_events = db.scalar(select(func.count(WorldEvent.id)).where(WorldEvent.user_id == user_id, WorldEvent.status == "PENDING")) or 0
    last_report = db.scalar(select(MonthReport).where(MonthReport.user_id == user_id).order_by(MonthReport.ref_month.desc()).limit(1))
    return {
        "month": month.ref_month.isoformat(), "mode": game.mode, "scenario": game.scenario_key, "dynamic_economy": game.economy_mode == "DYNAMIC",
        "cash": str(m["cash"]), "monthly_income": str(summary.planned_income), "monthly_expense": str(summary.planned_expense),
        "net_worth": str(m["net_worth"]), "debts": str(m["debts"]), "invested": str(m["invested"]),
        "passive_income": str(m["passive_income"]), "emergency_months": m["emergency_months"],
        "companies": [{"id": c.id, "name": c.name, "segment": c.segment.value} for c in companies],
        "family": {"partner": partner.stage if partner else None, "children": m["children"], "members": m["family_members"]},
        "wellbeing": ({"health": prof.health, "wellbeing": prof.wellbeing, "quality": prof.quality, "satisfaction": prof.satisfaction,
                       "social": prof.social} if prof else None),
        "economy": ({"inflation": str(st.inflation), "interest": str(st.interest), "unemployment": str(st.unemployment),
                     "growth": str(st.growth), "confidence": str(st.confidence)} if st else None),
        "goals": [goal_out(g) for g in goals], "pending_events": pending_events,
        "pending_life_decisions": len(life_service.pending_decisions(db, user_id, month)) if prof else 0,
        "last_report_month": last_report.ref_month.isoformat() if last_report else None,
        "achievements_unlocked": db.scalar(select(func.count(Achievement.id)).where(Achievement.user_id == user_id)) or 0,
    }
