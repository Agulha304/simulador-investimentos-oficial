"""Contratador (headhunter) opcional: contratar/dispensar/trocar de nível, briefing e as operações (cargos obrigatórios, equipe e
fornecedores). A lógica de escolha é PURA e fica em `company_recruiter`; aqui há o banco, o caixa, os tetos e a idempotência.

Cada operação devolve um RELATÓRIO (dict JSON) com o que foi contratado e o que NÃO foi (com o motivo); o relatório fica guardado em
`company_recruiter_runs` e a repetição da mesma `idempotency_key` devolve o mesmo relatório sem cobrar nada de novo.
Nenhuma função aqui faz commit.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import (
    Company, CompanyEventType, CompanyRecruiter, CompanyRecruiterRun, EmployeeRegime, FlowKind, SimMonth,
)
from backend.services import company_recruiter as rec
from backend.services import company_rules as rules
from backend.services import company_service as cs
from backend.services import company_supply as supply
from backend.services.budget_service import require_open
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError

D = Decimal
ZERO = Decimal("0.00")
MIN_RUNWAY_MONTHS = D(2)           # não contrata se o caixa pós-contratação cobrir menos de 2 meses de obrigações (equipe; não vale p/ obrigatórios)
MAX_TEAM_REQUEST = 60


# ------------------------------------------------------------------ contratar / trocar / dispensar / briefing

def _row(db: Session, c: Company) -> CompanyRecruiter | None:
    return db.scalar(select(CompanyRecruiter).where(CompanyRecruiter.company_id == c.id))


def _categories(c: Company) -> set[str]:
    return {x.key for x in rules.SEGMENTS[c.segment].supply_categories}


def settings_of(c: Company, row: CompanyRecruiter | None) -> rec.Settings:
    return rec.settings_from_json(row.settings if row else None, _categories(c))


def hire_recruiter(db: Session, user_id: int, month: SimMonth, company_id: int, tier: str, idempotency_key: str) -> CompanyRecruiter:
    """Contrata o contratador no nível pedido (ou TROCA o nível, se já houver um ativo). Sem custo imediato: a taxa mensal é cobrada no
    fechamento de cada mês em que ele estiver ativo. Repetir a mesma chave não muda nada."""
    require_open(month)
    c = cs.get_company(db, user_id, company_id, lock=True)
    cs._active(c)
    try:
        t = rec.tier_of(tier)
    except ValueError as e:
        raise FinanceError(str(e)) from None
    row = _row(db, c)
    ref = month.ref_month
    fee = rec.monthly_fee(t.key, c.size)
    if row is not None and row.last_key == idempotency_key:
        return row
    if row is None:
        row = CompanyRecruiter(company_id=c.id, tier=t.key, status="ACTIVE", hired_month=ref, settings=rec.settings_to_json(rec.Settings()),
                               last_key=idempotency_key)
        db.add(row)
        text = f"Contratador {t.label} contratado: taxa mensal de {fee} e comissão de {int(t.commission * 100)}% do salário por contratação"
    elif row.status == "ACTIVE":
        if row.tier == t.key:
            row.last_key = idempotency_key
            return row
        text = f"Contratador trocado de {rec.tier_of(row.tier).label} para {t.label}: taxa mensal de {fee} a partir deste fechamento"
        row.tier = t.key
    else:
        row.status, row.tier, row.hired_month, row.ended_month = "ACTIVE", t.key, ref, None
        text = f"Contratador {t.label} contratado novamente: taxa mensal de {fee}"
    row.last_key = idempotency_key
    db.flush()
    cs._event(db, c, ref, CompanyEventType.HIRE, text, fee)
    return row


def dismiss_recruiter(db: Session, user_id: int, month: SimMonth, company_id: int) -> CompanyRecruiter:
    """Dispensa o contratador a qualquer momento, sem multa (deixa de ser cobrado a partir do próximo fechamento)."""
    require_open(month)
    c = cs.get_company(db, user_id, company_id, lock=True)
    cs._active(c)
    row = _row(db, c)
    if row is None or row.status != "ACTIVE":
        raise ConflictError("a empresa não tem um contratador ativo")
    row.status, row.ended_month = "ENDED", month.ref_month
    db.flush()
    cs._event(db, c, month.ref_month, CompanyEventType.HIRE, "Contratador dispensado (sem multa)")
    return row


def update_briefing(db: Session, user_id: int, month: SimMonth, company_id: int, raw: dict) -> CompanyRecruiter:
    require_open(month)
    c = cs.get_company(db, user_id, company_id, lock=True)
    cs._active(c)
    row = _require_active(db, c)
    try:
        st = rec.build_settings(raw, _categories(c))
    except ValueError as e:
        raise FinanceError(str(e)) from None
    row.settings = rec.settings_to_json(st)
    db.flush()
    cs._event(db, c, month.ref_month, CompanyEventType.SETTINGS,
              f"Briefing do contratador atualizado: {rec.POLICY_LABEL[st.regime_policy]}, escala {st.schedule.value}, {st.hours_week} h/semana"
              + (f", salário máximo {st.max_salary}" if st.max_salary else "")
              + ("" if st.supplier_max_total_spend or st.general != rec.Limits() or st.overrides else "; fornecedores sem restrições (opcional)"))
    return row


def _require_active(db: Session, c: Company) -> CompanyRecruiter:
    row = _row(db, c)
    if row is None or row.status != "ACTIVE":
        raise ConflictError("Contrate um contratador (headhunter) antes de usar este recurso: ele é um serviço opcional da empresa.")
    return row


# ------------------------------------------------------------------ relatórios idempotentes

def _replayed(db: Session, c: Company, key: str, kind: str) -> dict | None:
    run = db.scalar(select(CompanyRecruiterRun).where(CompanyRecruiterRun.company_id == c.id, CompanyRecruiterRun.idempotency_key == key))
    if run is None:
        return None
    if run.kind != kind:
        raise ConflictError("esta chave de idempotência já foi usada em outra operação do contratador")
    return {**run.report, "replayed": True}


def _save(db: Session, c: Company, key: str, kind: str, ref: date, report: dict) -> dict:
    db.add(CompanyRecruiterRun(company_id=c.id, idempotency_key=key, kind=kind, ref_month=ref, report=report))
    db.flush()
    return {**report, "replayed": False}


# ------------------------------------------------------------------ pessoas

class _Run:
    """Estado de UMA operação de contratação: o que já foi contratado e o que já se somou à folha."""

    def __init__(self, db: Session, c: Company, row: CompanyRecruiter, cfg: rec.Settings, ref: date, key: str, seed: int, check_runway: bool):
        self.db, self.c, self.row, self.cfg, self.ref, self.key, self.seed, self.check_runway = db, c, row, cfg, ref, key, seed, check_runway
        self.seg = rules.SEGMENTS[c.segment]
        self.hired: list[dict] = []
        self.skipped: list[dict] = []
        self.cost = ZERO
        self.commission = ZERO
        self.used: set[str] = set()
        self.n = 0

    def payroll_room(self) -> Decimal | None:
        return None if self.cfg.max_monthly_payroll is None else max(self.cfg.max_monthly_payroll - self.cost, ZERO)

    def staff_full(self) -> str | None:
        cap = rules.max_staff(self.c.size, self.c.units)
        n = len(cs._employees(self.db, self.c))
        return (f"teto de funcionários atingido: o porte {rules.SIZES[self.c.size].label} comporta {cap} pessoa(s) ({n} contratadas)"
                if n >= cap else None)

    def try_plan(self, plan: rec.Plan, role: rules.Role) -> str | None:
        """Tenta contratar o plano. None = contratou; texto = motivo de não ter contratado."""
        db, c = self.db, self.c
        commission = rec.commission(self.row.tier, plan.salary)
        balance = cs.cash(db, c)
        if balance < commission:
            return f"caixa insuficiente para a comissão do contratador ({commission}); caixa atual: {balance}"
        if self.check_runway:
            obligations = cs.monthly_obligations(db, c) + plan.monthly_cost
            months = (balance - commission) / obligations if obligations > 0 else D(99)
            if months < MIN_RUNWAY_MONTHS:
                return (f"risco de caixa: após contratar {plan.person.name}, o caixa cobriria só {months:.1f} mês(es) de obrigações "
                        f"(custo mensal total {quantize_money(obligations)}); o mínimo é {MIN_RUNWAY_MONTHS} meses")
        self.n += 1
        cs._post(db, c, self.ref, kind=FlowKind.EXPENSE, amount=commission,
                 desc=f"Comissão do contratador: {role.label} ({plan.person.name})", line="HIRING", key=f"co:{c.id}:rec:{self.key}:{self.n}")
        cs._create_employee(db, c, plan.person, role, plan.salary, plan.hours_week, plan.schedule, plan.person.regime, self.ref, via=" pelo contratador")
        cs._block(db, c, cs._TokenBlock(plan.key), self.ref, "HIRED")
        self.used.add(plan.key)
        self.cost += plan.monthly_cost
        self.commission += commission
        self.hired.append({
            "name": plan.person.name, "role": role.key, "role_label": role.label, "regime": plan.person.regime.value,
            "level": plan.person.level.value, "salary": str(plan.salary), "hours_week": plan.hours_week, "schedule": plan.schedule.value,
            "monthly_cost": str(plan.monthly_cost), "commission": str(commission), "lawsuit_history": plan.person.lawsuit_history,
            "why_regime": plan.why, "cost_benefit": round(plan.score * 1000, 3)})
        return None

    def fill(self, role: rules.Role, count: int, *, by_cost: bool, hours_options: list[int]) -> None:
        """Preenche até `count` vagas do cargo; o que não couber vira um item em `skipped` com o motivo."""
        done, reason = 0, ""
        blocked = cs._blocked(self.db, self.c)
        while done < count:
            full = self.staff_full()
            if full:
                reason = full
                break
            plans, diag = rec.ranked_plans(self.seed, self.c.id, self.ref, role, self.row.tier, self.cfg, exclude=blocked | self.used,
                                           hours_options=hours_options, cost_limit=self.payroll_room(), by_cost=by_cost)
            if not plans:
                reason = (diag or "nenhum candidato cabe no orçamento")
                if self.cfg.max_monthly_payroll is not None and self.payroll_room() == 0:
                    reason = f"teto de folha extra do briefing atingido (R$ {self.cfg.max_monthly_payroll}/mês)"
                break
            why = ""
            for p in plans:
                why = self.try_plan(p, role) or ""
                if not why:
                    done += 1
                    break
            else:
                reason = why                                    # nenhum dos planos viáveis coube no caixa
                break
        if done < count:
            self.skipped.append({"role": role.key, "role_label": role.label, "requested": count, "hired": done, "missing": count - done,
                                 "reason": reason or "sem candidato"})

    def report(self, kind: str, message: str) -> dict:
        return {"kind": kind, "message": message, "hired": self.hired, "skipped": self.skipped, "contracted": [],
                "total_monthly_cost": str(quantize_money(self.cost)), "total_commission": str(quantize_money(self.commission)),
                "total_expected_spend": "0.00"}


def _prepare(db: Session, user_id: int, month: SimMonth, company_id: int, key: str, kind: str):
    require_open(month)
    c = cs.get_company(db, user_id, company_id, lock=True)
    cs._active(c)
    row = _require_active(db, c)
    return c, row, _replayed(db, c, key, kind)


def hire_mandatory(db: Session, user_id: int, month: SimMonth, company_id: int, idempotency_key: str) -> dict:
    """Contrata TODOS os cargos obrigatórios que faltam, cada um pelo menor custo mensal que cabe no salário máximo do briefing, na escala
    do briefing e com a menor proposta que o candidato aceita. Aceita jornada de 20 h (conta como preenchido) se sair mais barato."""
    c, row, done = _prepare(db, user_id, month, company_id, idempotency_key, "MANDATORY")
    if done is not None:
        return done
    cfg = settings_of(c, row)
    if cfg.max_salary is None:
        raise FinanceError("Informe o salário máximo no briefing do contratador antes de contratar.")
    ref = month.ref_month
    run = _Run(db, c, row, cfg, ref, idempotency_key, cs._seed(db, user_id), check_runway=False)
    active = {e.role for e in cs._employees(db, c) if rules.counts_as_filled(e.hours_week)}
    missing = rules.missing_mandatory(c.channel, active)
    hours = sorted({rules.MANDATORY_MIN_HOURS, cfg.hours_week})
    for key in missing:
        run.fill(run.seg.role_for(key, c.size), 1, by_cost=True, hours_options=hours)
    if not missing:
        msg = "Todos os cargos obrigatórios já estão preenchidos."
    else:
        msg = f"O contratador contratou {len(run.hired)} de {len(missing)} cargo(s) obrigatório(s)."
    return _save(db, c, idempotency_key, "MANDATORY", ref, run.report("MANDATORY", msg))


def hire_team(db: Session, user_id: int, month: SimMonth, company_id: int, roles: list[dict], idempotency_key: str) -> dict:
    """Contrata as quantidades pedidas por cargo/área: ranqueia por custo-benefício (produtividade / custo mensal real) e contrata os
    melhores que cabem no teto de salário, no teto de funcionários, no teto de folha extra do briefing e no caixa (runway >= 2 meses)."""
    c, row, done = _prepare(db, user_id, month, company_id, idempotency_key, "TEAM")
    if done is not None:
        return done
    cfg = settings_of(c, row)
    if cfg.max_salary is None:
        raise FinanceError("Informe o salário máximo no briefing do contratador antes de contratar.")
    seg = rules.SEGMENTS[c.segment]
    wanted: dict[str, int] = {}
    for r in roles:
        try:
            seg.role(r["role"])
        except KeyError:
            raise FinanceError(f"cargo inexistente neste segmento: {r['role']}") from None
        if int(r["count"]) < 1:
            raise FinanceError("a quantidade de cada cargo deve ser pelo menos 1")
        wanted[r["role"]] = wanted.get(r["role"], 0) + int(r["count"])
    if not wanted or sum(wanted.values()) > MAX_TEAM_REQUEST:
        raise FinanceError(f"peça de 1 a {MAX_TEAM_REQUEST} funcionários no total")
    ref = month.ref_month
    run = _Run(db, c, row, cfg, ref, idempotency_key, cs._seed(db, user_id), check_runway=True)
    for key, n in wanted.items():
        run.fill(seg.role_for(key, c.size), n, by_cost=False, hours_options=[cfg.hours_week])
    asked = sum(wanted.values())
    msg = f"O contratador contratou {len(run.hired)} de {asked} funcionário(s) pedido(s)."
    return _save(db, c, idempotency_key, "TEAM", ref, run.report("TEAM", msg))


# ------------------------------------------------------------------ fornecedores

def contract_suppliers(db: Session, user_id: int, month: SimMonth, company_id: int, categories: list[str] | None, idempotency_key: str) -> dict:
    """Contrata fornecedores por mim: para cada categoria (padrão: as sem contrato ativo) avalia as ofertas do universo do nível, filtra por
    confiabilidade mínima, prazo máximo, volume máximo e gasto máximo (categoria e total), escolhe o de melhor custo-benefício (menor preço
    efetivo = preço x (1 + 2 x falha)) e NEGOCIA o menor preço que ele aceita (com o desconto do nível). Os limites ficam guardados no contrato."""
    c, row, done = _prepare(db, user_id, month, company_id, idempotency_key, "SUPPLIERS")
    if done is not None:
        return done
    seg = rules.SEGMENTS[c.segment]
    if not seg.needs_suppliers:
        raise FinanceError(f"{seg.label} não usa fornecedores")
    valid = {x.key: x for x in seg.supply_categories}
    for k in categories or []:
        if k not in valid:
            raise FinanceError(f"categoria de fornecimento inexistente neste segmento: {k}")
    cfg = settings_of(c, row)
    ref = month.ref_month
    seed = cs._seed(db, user_id)
    tier = rec.tier_of(row.tier)
    contracts = cs._contracts(db, c)
    wanted = list(dict.fromkeys(categories)) if categories else [k for k in valid if k not in contracts]
    staff = cs._employees(db, c)
    exp_demand = D(str(cs.expected_totals(db, c, seg, staff)[0]))

    def expected_volume(cat: rules.SupplyCategory) -> Decimal:
        return exp_demand * cat.per_sale * (1 + cat.waste_pct / 100)

    running = quantize_money(sum((min(expected_volume(valid[k]), cs.effective_volume(s)) * s.unit_price
                                  for k, s in contracts.items() if k not in wanted), ZERO))
    contracted, skipped = [], []
    blocked = cs._blocked(db, c)
    mult = cs._price_mult(db, c, ref)
    for k in wanted:
        cat = valid[k]
        if k in contracts:
            skipped.append({"category": k, "label": cat.label, "reason": f"já existe contrato ativo com {contracts[k].name}: encerre-o antes"})
            continue
        lim = cfg.limits_for(k)
        offers = [o for o in supply.universe(seed, c.id, ref, seg, k, tier.offers, size=c.size, units=c.units,
                                             capacity_level=cs.eff_capacity_level(c), price_mult=mult) if o.id not in blocked]
        offers = rec.visible_offers(seed, c.id, ref, row.tier, offers)
        if not offers:
            skipped.append({"category": k, "label": cat.label, "reason": "nenhum fornecedor disponível neste mês"})
            continue
        plans, reasons = [], []
        for o in offers:
            p = rec.plan_supplier(o, seed=seed, company_id=c.id, ref=ref, tier=row.tier, relevance=float(c.relevance),
                                  expected_volume=expected_volume(cat), limits=lim)
            (reasons if isinstance(p, str) else plans).append(p)
        plans.sort(key=lambda x: (x.score, x.offer.id))
        pick, why_total = None, ""
        for p in plans:
            if cfg.supplier_max_total_spend is not None and running + p.expected_spend > cfg.supplier_max_total_spend:
                why_total = (f"gasto total previsto com fornecedores passaria de R$ {cfg.supplier_max_total_spend}/mês "
                             f"(já previsto R$ {running}; esta categoria: R$ {p.expected_spend})")
                continue
            pick = p
            break
        if pick is None:
            skipped.append({"category": k, "label": cat.label, "reason": why_total or "; ".join(dict.fromkeys(reasons[:3])) or "nenhuma oferta serviu"})
            continue
        sup = cs._sign_contract(db, c, pick.offer, cat, pick.price, pick.volume, ref, f"rec:{idempotency_key[:60]}:{k}", limits=pick.limits, via=" pelo contratador")
        blocked = blocked | {pick.offer.id}
        running = quantize_money(running + pick.expected_spend)
        contracted.append({"category": k, "label": cat.label, "supplier": sup.name, "unit": cat.unit, "unit_price": str(pick.price),
                           "reference_price": str(cat.ref_price), "volume": str(pick.volume), "expected_spend": str(pick.expected_spend),
                           "reliability": float(sup.reliability), "lead_days": sup.lead_days, "contract_id": sup.id})
    spend = quantize_money(sum((D(x["expected_spend"]) for x in contracted), ZERO))
    report = {"kind": "SUPPLIERS", "message": f"O contratador fechou {len(contracted)} de {len(wanted)} contrato(s) de fornecedor.",
              "hired": [], "skipped": skipped, "contracted": contracted, "total_monthly_cost": "0.00", "total_commission": "0.00",
              "total_expected_spend": str(spend)}
    return _save(db, c, idempotency_key, "SUPPLIERS", ref, report)


# ------------------------------------------------------------------ visão (detalhe da empresa)

def view(db: Session, c: Company) -> dict | None:
    row = _row(db, c)
    if row is None:
        return None
    t = rec.tier_of(row.tier)
    return {"tier": t.key, "tier_label": t.label, "status": row.status, "hired_month": row.hired_month, "ended_month": row.ended_month,
            "monthly_fee": rec.monthly_fee(t.key, c.size) if row.status == "ACTIVE" else ZERO, "commission_pct": float(t.commission) * 100,
            "settings": rec.settings_to_json(settings_of(c, row)), **_quality(t)}


def _quality(t: rec.Tier) -> dict:
    return {"pool": t.pool, "offers": t.offers, "find_chance_pct": round(t.find_chance * 100), "discount_pct": round(t.discount * 100, 1),
            "success_pct": round(t.success * 100)}


def tier_options(c: Company) -> list[dict]:
    return [{"tier": t.key, "label": t.label, "monthly_fee": rec.monthly_fee(t.key, c.size), "commission_pct": float(t.commission) * 100,
             **_quality(t)} for t in rec.TIERS.values()]
