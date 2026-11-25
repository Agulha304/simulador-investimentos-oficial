"""Expansão em passos (fase 5): tipo -> nível (barato/médio/caro) -> 3 opções sorteadas -> confirmar -> resultado.

* `draw_options`: 3 opções determinísticas por (empresa, semente da partida, mês, tipo, nível) de um conjunto maior por família/segmento
  (`company_expansion_data`). O servidor RECALCULA as opções ao executar: `option_key` precisa estar entre as 3 do mês.
* `execute`: cobra, sorteia o resultado (COMPLETO / PARCIAL / FRACASSO) com `_roll` (hash01 + semente; os testes trocam `_roll`) e aplica
  os efeitos. Nível maior => mais chance e efeito maior; nunca garantido. Idempotente por `idempotency_key` (tabela `company_expansions`).
Nenhuma função aqui faz commit.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import (
    Company, CompanyChannel, CompanyCost, CompanyCostKind, CompanyEventType, CompanyExpansion, CompanyUnit, Employee, EmployeeEducation,
    EmployeeLevel, EmployeeRegime, EmployeeStatus, FlowKind, LeaseKind, SimMonth, SiteMode, WorkSchedule,
)
from backend.services import company_expansion_data as data
from backend.services import company_rules as rules
from backend.services import company_service as cs
from backend.services.budget_service import require_open, shift_month
from backend.services.finance_ledger import ConflictError, FinanceError
from backend.services.goods_rules import hash01

D = Decimal
ZERO = Decimal("0.00")
MANAGER_ROLE = "production_manager"
MANAGER_LABEL = "Gerente de produtividade"


def _roll(*parts: object) -> float:
    """Sorteio dos RESULTADOS (determinístico). Os testes substituem esta função para forçar sucesso/fracasso."""
    return hash01(*parts)


# ------------------------------------------------------------------ opções

@dataclass(frozen=True)
class OptionView:
    key: str
    title: str
    description: str
    cost: Decimal
    side_effects: list[str]
    risk_hint: str


def tier_index(tier: str) -> int:
    if tier not in rules.TIERS:
        raise FinanceError("nível inválido (use BARATO, MEDIO ou CARO)")
    return rules.TIERS.index(tier)


def check_kind(kind: str) -> None:
    if kind not in rules.EXPANSION_KINDS:
        raise FinanceError("tipo de aporte inválido")


def draw_options(seed: int, c: Company, ref: date, kind: str, tier: str) -> list[data.Opt]:
    """3 opções do mês: as de menor `hash01(semente, empresa, mês, tipo, nível, opção)` do conjunto da família/segmento."""
    check_kind(kind)
    tier_index(tier)
    seg = rules.SEGMENTS[c.segment]
    pool = data.pool(kind, family=data.family_of(seg.metrics_kind.value), segment=seg.key.value)
    ranked = sorted(pool, key=lambda p: (hash01(seed, "xpopt", c.id, f"{ref:%Y-%m}", kind, tier, p.key), p.key))
    return ranked[:3]


def base_cost(c: Company, kind: str, tier: str) -> Decimal:
    return rules.expansion_cost(rules.SEGMENTS[c.segment], kind, c.size, c.units, tier)


def option_cost(c: Company, kind: str, tier: str, opt: data.Opt) -> Decimal:
    return quantize_money(base_cost(c, kind, tier) * D(str(opt.cost)))


def odds(kind: str, tier: str, opt: data.Opt) -> tuple[float, float]:
    """(chance de efeito COMPLETO, chance de efeito PARCIAL) do aporte; o resto é fracasso."""
    full, part = rules.TIER_ODDS[kind][tier_index(tier)]
    full = min(0.95, max(0.05, full - opt.risk))
    return full, min(part, 1 - full)


def side_effect_texts(c: Company, kind: str, tier: str, opt: data.Opt) -> list[str]:
    fx, out = opt.fx, []
    if fx.get("storage"):
        out.append(f"Teto de estoque +{round(fx['storage'] * 100)}% (efeito completo)")
    if fx.get("fixed"):
        out.append(f"Custos fixos recorrentes +{round(fx['fixed'] * 100)}% (energia, manutenção e instalações)")
    if fx.get("manager"):
        out.append("Contrata um gerente: salário e encargos recorrentes")
    if fx.get("quit"):
        out.append(f"Cada funcionário produtivo tem {round(fx['quit'] * 100)}% de chance de pedir demissão")
    if fx.get("hours"):
        out.append(f"Jornada dos produtivos +{fx['hours']} h/semana e salários +{round(fx.get('salary', 0) * 100)}% "
                   "(mais risco de processo trabalhista)")
    if kind == "NEW_UNIT":
        if fx.get("rent", 1.0) != 1.0:
            out.append(f"Aluguel de {round(fx['rent'] * 100)}% do ponto de referência")
        out.append("Nova unidade soma custos fixos, folha compartilhada e aluguel; pode fechar se acumular prejuízo")
    if kind == "CAPACITY":
        out.append("Produzir mais NÃO garante vender mais: as vendas seguem limitadas pela demanda e pela relevância")
        if rules.SEGMENTS[c.segment].needs_suppliers:
            out.append("Para usar a capacidade nova é preciso comprar mais dos fornecedores (volume contratado)")
    if kind == "QUALITY":
        out.append("Insumos e custos variáveis ficam mais caros na mesma proporção da qualidade")
        out.append("Em troca: mais relevância por mês e tolerância a preço maior")
    if kind == "MARKETING":
        out.append("Pode não ter efeito algum ou viralizar; o dinheiro é gasto de qualquer jeito")
    if kind == "LARGER_PREMISES":
        out.append("Se der certo o porte sobe: aluguel e custos fixos acompanham")
    if opt.note:
        out.append(opt.note)
    return out


def risk_hint(tier: str, opt: data.Opt) -> str:
    if opt.risk <= -0.05:
        base = "Aposta segura: costuma funcionar, mas o ganho tende a ser menor."
    elif opt.risk >= 0.08:
        base = "Aposta alta: pode render muito, mas é fácil não funcionar."
    else:
        base = "Pode ou não funcionar: o resultado é incerto."
    extra = {"BARATO": " No nível barato a chance de dar errado é maior.", "MEDIO": "",
             "CARO": " O nível caro aumenta a chance de dar certo, sem garantir."}[tier]
    return base + extra


def option_views(seed: int, c: Company, ref: date, kind: str, tier: str) -> list[OptionView]:
    return [OptionView(o.key, o.title, o.desc, option_cost(c, kind, tier, o), side_effect_texts(c, kind, tier, o), risk_hint(tier, o))
            for o in draw_options(seed, c, ref, kind, tier)]


def sites(c: Company) -> list[dict]:
    """Opções de canal/local para NOVA UNIDADE (com aluguel de referência e preço do terreno no porte da empresa)."""
    seg = rules.SEGMENTS[c.segment]
    out = []
    for ch in seg.channels:
        if ch == CompanyChannel.ONLINE:
            out.append({"channel": ch, "location": rules.ONLINE_LOCATION_KEY, "label": "Operação online", "monthly_rent": ZERO, "land_cost": ZERO})
            continue
        for loc in seg.locations:
            out.append({"channel": ch, "location": loc.key, "label": loc.label,
                        "monthly_rent": rules.default_rent(seg, loc.key, c.size),
                        "land_cost": rules.land_value(seg, ch, SiteMode.BUY, loc.key, c.size)})
    return out


def tier_table(c: Company) -> dict[str, list[dict]]:
    """Por tipo: os 3 níveis com custo e as chances aproximadas (para a tela de escolha do nível)."""
    out: dict[str, list[dict]] = {}
    for kind in rules.EXPANSION_KINDS:
        rows = []
        for t in rules.TIERS:
            try:
                cost = base_cost(c, kind, t)
            except KeyError:
                continue
            if kind in rules.TIER_ODDS:
                full, part = rules.TIER_ODDS[kind][tier_index(t)]
                chance = f"{round(full * 100)}% de efeito completo, {round(part * 100)}% parcial"
            elif kind == "NEW_UNIT":
                chance = (f"{round((1 - rules.BRANCH_FAIL[tier_index(t)]) * 100)}% de abrir; relevância inicial "
                          f"{round(rules.BRANCH_REL_FRAC[tier_index(t)] * 100)}% da marca")
            else:
                i = tier_index(t)
                chance = f"{round(rules.CAMPAIGN_FAIL[i] * 100)}% de não ter efeito, {round(rules.CAMPAIGN_VIRAL[i] * 100)}% de viralizar"
            rows.append({"tier": t, "label": rules.TIER_LABEL[t], "cost": cost, "chance": chance})
        out[kind] = rows
    return out


# ------------------------------------------------------------------ execução

@dataclass
class ExecResult:
    success: bool
    outcome: str                       # FULL | PARTIAL | FAIL
    message: str
    effects: list[str]
    cost: Decimal
    replayed: bool = False


def _validate_limits(db: Session, c: Company, kind: str) -> None:
    if kind == "CAPACITY" and float(c.capacity_boost) >= rules.MAX_CAPACITY_LEVEL:
        raise ConflictError("a capacidade já está no nível máximo")
    if kind == "NEW_UNIT" and c.units >= rules.MAX_UNITS:
        raise ConflictError(f"limite de {rules.MAX_BRANCHES} filiais próprias atingido: para crescer mais, franqueie a marca")
    if kind == "LARGER_PREMISES" and c.size == rules.CompanySize.LARGE:
        raise ConflictError("a empresa já está no maior porte")
    if kind == "QUALITY" and float(c.quality) >= 100:
        raise ConflictError("a qualidade já está no máximo")


def _outcome(kind: str, tier: str, opt: data.Opt, *key) -> str:
    full, part = odds(kind, tier, opt)
    r = _roll("xp-result", *key)
    return "FULL" if r < full else ("PARTIAL" if r < full + part else "FAIL")


def _row(db: Session, c: Company, ref: date, kind: str, tier: str, opt_key: str, idem: str, outcome: str, cost: Decimal, message: str,
         effects: list[str]) -> None:
    db.add(CompanyExpansion(company_id=c.id, idempotency_key=idem, ref_month=ref, kind=kind, tier=tier, option_key=opt_key,
                            outcome=outcome, cost=cost, message=message[:400], effects=effects))
    db.flush()


def _recurring_cost(db: Session, c: Company, pct: float, name: str) -> Decimal:
    """Custo fixo recorrente = `pct` x os custos fixos atuais por unidade (energia, ferramentas, contabilidade...)."""
    base = db.scalar(select(func.coalesce(func.sum(CompanyCost.amount), 0)).where(CompanyCost.company_id == c.id, CompanyCost.active.is_(True)))
    amount = quantize_money(D(base) * D(str(pct)))
    if amount > 0:
        db.add(CompanyCost(company_id=c.id, kind=CompanyCostKind.OTHER, name=name[:80], amount=amount, scales_with_units=False))
        db.flush()
    return amount


def _productive(seg: rules.Segment, e: Employee) -> bool:
    return any(r.key == e.role and r.units > 0 for r in seg.roles)


def _apply_capacity(db, c, seg, ref, tier, opt, outcome, key, effects: list[str], idem: str) -> None:
    ti = tier_index(tier)
    f = 1.0 if outcome == "FULL" else 0.5
    gain = min(rules.CAPACITY_GAIN[ti] * opt.power * f, rules.MAX_CAPACITY_LEVEL - float(c.capacity_boost))
    c.capacity_boost = D(str(round(float(c.capacity_boost) + gain, 3)))
    c.capacity_level += 1
    effects.append(f"Capacidade de produção/atendimento +{round(gain * 25, 1)}% (de {rules.production_ceiling(seg, c.size, 1):.0f} de teto-base por unidade)")
    fx = opt.fx
    if fx.get("storage") and seg.has_stock:
        c.storage_boost = D(str(round(float(c.storage_boost) + fx["storage"] * f, 3)))
        effects.append(f"Teto de estoque +{round(fx['storage'] * f * 100)}%")
    if fx.get("fixed"):
        amt = _recurring_cost(db, c, fx["fixed"] * (1 if outcome == "FULL" else 0.6), f"{opt.title}: energia, manutenção e instalações")
        if amt > 0:
            effects.append(f"Custo fixo recorrente +{amt}/mês")
    staff = cs._employees(db, c)
    if fx.get("manager"):
        pay = [r.salary for r in seg.roles if r.units > 0 and r.key not in {g.key for g in rules.GENERIC_ROLES}]
        salary = quantize_money(max(pay, default=D(3000)) * D("1.6"))
        db.add(Employee(company_id=c.id, role=MANAGER_ROLE, level=EmployeeLevel.SENIOR, salary=salary, hours_week=44, productivity=D("1.00"),
                        hired_on=ref, name="Gerente de produtividade", regime=EmployeeRegime.CLT, schedule=WorkSchedule.ESC_5X2,
                        education=EmployeeEducation.SUPERIOR,
                        experience_years=8))
        hire_cost = quantize_money(salary * rules.HIRING_COST_MONTHS)
        cs._post(db, c, ref, kind=FlowKind.EXPENSE, amount=hire_cost, desc="Custo de contratação: gerente de produtividade", line="HIRING",
                 key=f"co:{c.id}:xp:{idem}:manager", overdraft=True)
        effects.append(f"Gerente contratado: salário {salary} (custo mensal {rules.payroll_cost(salary)})")
    if fx.get("quit"):
        prod = [e for e in staff if _productive(seg, e)]
        quitters = [e for e in prod if _roll("xp-quit", *key, e.id) < fx["quit"]]
        quitters = quitters[: max(1, (len(prod) * 4 + 9) // 10)] if quitters else []     # no máximo 40% da equipe produtiva
        for e in quitters:
            e.status = EmployeeStatus.TERMINATED
            e.terminated_on = ref
            cs._event(db, c, ref, CompanyEventType.FIRE, f"Pedido de demissão: {e.name or e.role} não aguentou a cobrança por produtividade")
        if quitters:
            effects.append("Pediram demissão: " + ", ".join(e.name or e.role for e in quitters))
        else:
            effects.append("Ninguém pediu demissão desta vez")
    if fx.get("hours"):
        for e in staff:
            if _productive(seg, e):
                e.hours_week = min(56, e.hours_week + fx["hours"])
                e.salary = quantize_money(e.salary * (1 + D(str(fx.get("salary", 0)))))
        effects.append(f"Turno extra: jornada dos produtivos +{fx['hours']} h/semana, salários +{round(fx.get('salary', 0) * 100)}%")


def _supply_warning(db: Session, c: Company, seg: rules.Segment, ref: date) -> str | None:
    if not seg.needs_suppliers:
        return None
    state = cs.supply_state(db, c, ref)
    cap = rules.capacity_units(seg, size=c.size, units=c.units, capacity_level=float(c.capacity_boost), staff=cs.staff_capacity(cs._employees(db, c)),
                               equipment_factor=cs._equipment_factor(db, c))
    if state["cap"] < cap:
        return (f"Atenção: os contratos de fornecedores sustentam só {state['cap']:.0f} {seg.unit_label}(s) por mês, abaixo da nova capacidade "
                f"({cap:.0f}). Compre mais dos fornecedores (contrate outro com mais volume) para usar a capacidade ampliada.")
    return "Para produzir mais é preciso comprar mais dos fornecedores: acompanhe o volume contratado."


def _apply_quality(db, c, ref, tier, opt, outcome, effects: list[str]) -> None:
    ti = tier_index(tier)
    f = 1.0 if outcome == "FULL" else 0.5
    gain = min(rules.QUALITY_GAIN[ti] * opt.power * f, 100 - float(c.quality))
    c.quality = D(str(round(float(c.quality) + gain, 2)))
    effects.append(f"Qualidade +{gain:.1f} (agora {float(c.quality):.1f}/100): custo de insumos x{rules.quality_cost_mult(float(c.quality)):.2f}")
    if opt.fx.get("fixed"):
        amt = _recurring_cost(db, c, opt.fx["fixed"], f"{opt.title}: taxas e auditorias")
        if amt > 0:
            effects.append(f"Custo fixo recorrente +{amt}/mês")


def _apply_marketing(db, c, ref, tier, opt, key, effects: list[str]) -> tuple[str, str]:
    ti = tier_index(tier)
    fail = min(0.6, max(0.02, rules.CAMPAIGN_FAIL[ti] + opt.risk))
    viral = min(0.5, max(0.02, rules.CAMPAIGN_VIRAL[ti] + opt.risk * 0.5))
    r = _roll("xp-result", *key)
    if r < fail:
        effects.append("Nenhum efeito sobre a demanda ou a relevância")
        return "FAIL", "A campanha passou despercebida: o público não respondeu e o dinheiro foi gasto."
    boost = rules.CAMPAIGN_BOOST[ti] * opt.power
    months = rules.CAMPAIGN_MONTHS[ti]
    rel_gain = rules.CAMPAIGN_REL[ti] * opt.power
    outcome, msg = "FULL", "A campanha funcionou como o esperado."
    if r > 1 - viral:
        boost, months, rel_gain = boost * 1.8, months + 1, rel_gain * 2
        outcome, msg = "FULL", "A campanha VIRALIZOU: o efeito passou do esperado!"
    until = shift_month(ref, months - 1)
    if c.marketing_until is None or c.marketing_until < ref or boost >= float(c.marketing_boost):
        c.marketing_boost = D(str(round(boost, 3)))
    c.marketing_until = max(until, c.marketing_until) if c.marketing_until and c.marketing_until >= ref else until
    gain = rel_gain * (1 - float(c.relevance) / 100)
    c.relevance = D(str(round(min(100.0, float(c.relevance) + gain), 2)))
    effects.append(f"Demanda +{round(boost * 100)}% até {c.marketing_until:%m/%Y}; relevância +{gain:.1f} (agora {float(c.relevance):.1f})")
    return outcome, msg


def _apply_larger(db, c, seg, ref, outcome, effects: list[str]) -> None:
    if outcome == "FULL":
        old, new = c.size, rules.SIZE_ORDER[rules.SIZE_ORDER.index(c.size) + 1]
        ratio = rules.SIZES[new].fixed / rules.SIZES[old].fixed
        for row in db.scalars(select(CompanyCost).where(CompanyCost.company_id == c.id)):
            row.amount = quantize_money(row.amount * ratio)
        lease = cs._lease(db, c)
        if lease and lease.kind == LeaseKind.EXTERNAL:
            lease.monthly_rent = rules.default_rent(seg, c.location, new)
        c.size = new
        effects.append(f"Porte {rules.SIZES[new].label}: tetos de equipe, estoque e produção maiores; aluguel e custos fixos acompanham")
    else:
        c.capacity_boost = D(str(round(min(float(rules.MAX_CAPACITY_LEVEL), float(c.capacity_boost) + 0.4), 3)))
        c.storage_boost = D(str(round(float(c.storage_boost) + 0.2, 3)))
        effects.append("A obra não chegou ao porte seguinte, mas rendeu +10% de capacidade e +20% de estoque")


def _open_unit(db, c, seg, ref, tier, opt, kind_cost, channel, mode, loc, key, idem) -> tuple[str, str, list[str]]:
    ti = tier_index(tier)
    fail_p = min(0.4, max(0.01, rules.BRANCH_FAIL[ti] + opt.risk * 0.5))
    if _roll("xp-open", *key) < fail_p:
        return "FAIL", "A abertura não vingou (licença ou ponto não saíram): metade do investimento foi perdida e nenhuma unidade foi aberta.", \
            ["Nenhuma unidade aberta"]
    u = _roll("xp-viab", *key)
    viab = min(rules.VIAB_MAX, max(rules.VIAB_MIN, rules.VIAB_MIN + 1.1 * u ** rules.BRANCH_VIAB_SHAPE[ti] + opt.fx.get("viab", 0.0)))
    frac = rules.BRANCH_REL_FRAC[ti] + opt.fx.get("relfrac", 0.0)
    land = rules.land_value(seg, channel, mode, loc, c.size)
    rent = quantize_money(rules.monthly_rent(seg, loc, c.size, 1, channel=channel, site_mode=mode) * D(str(opt.fx.get("rent", 1.0))))
    n = (db.scalar(select(func.count()).select_from(CompanyUnit).where(CompanyUnit.company_id == c.id)) or 0) + 1
    unit = CompanyUnit(company_id=c.id, kind="BRANCH", name=f"Filial {n}", location=loc, channel=channel, site_mode=mode, site_value=land,
                       monthly_rent=rent, relevance=D(str(round(float(c.relevance) * frac, 2))), viability=D(str(round(viab, 3))),
                       status="OPEN", opened_month=ref, investment=kind_cost,
                       opens_month=shift_month(ref, rules.unit_build_months(channel, mode)))
    db.add(unit)
    c.units += 1
    db.flush()
    label = "online" if channel == CompanyChannel.ONLINE else rules.resolve_location(seg, loc).label
    build = rules.unit_build_months(channel, mode)
    effects = [f"Filial em {'obra' if mode == SiteMode.BUY else 'instalação'}: começa a vender em {unit.opens_month:%m/%Y} ({build} {'mês' if build == 1 else 'meses'})",
               f"Filial aberta ({label}; {'terreno comprado' if mode == SiteMode.BUY else 'alugada' if mode == SiteMode.RENT else 'online'})",
               f"Relevância inicial {float(unit.relevance):.1f} ({round(frac * 100)}% da marca, que é {float(c.relevance):.1f})",
               "O desempenho real só aparece nos próximos meses: pode vender menos ou mais que a matriz e fechar se acumular prejuízo"]
    if rent > 0:
        effects.append(f"Aluguel da filial: {rent}/mês")
    return ("FULL" if viab >= 0.95 else "PARTIAL"), f"{unit.name} aberta! Agora a marca tem {c.units} unidade(s).", effects


def execute(db: Session, user_id: int, month: SimMonth, company_id: int, *, kind: str, tier: str, option_key: str, idempotency_key: str,
            channel: CompanyChannel | None = None, site_mode: SiteMode | None = None, location: str | None = None) -> ExecResult:
    require_open(month)
    c = cs.get_company(db, user_id, company_id, lock=True)
    cs._active(c)
    check_kind(kind)
    ti = tier_index(tier)
    seg = rules.SEGMENTS[c.segment]
    ref = month.ref_month
    done = db.scalar(select(CompanyExpansion).where(CompanyExpansion.company_id == c.id, CompanyExpansion.idempotency_key == idempotency_key))
    if done is not None:                                              # repetição da mesma solicitação: nada muda e nada é cobrado
        return ExecResult(done.outcome != "FAIL", done.outcome, done.message, list(done.effects or []), done.cost, replayed=True)
    seed = cs._seed(db, user_id)
    opts = {o.key: o for o in draw_options(seed, c, ref, kind, tier)}
    opt = opts.get(option_key)
    if opt is None:                                                   # nunca confiar no cliente: só as 3 opções sorteadas do mês
        raise FinanceError("opção inválida: ela não está entre as 3 opções deste mês para este nível")
    _validate_limits(db, c, kind)
    cost = option_cost(c, kind, tier, opt)
    land = ZERO
    loc = mode = None
    ch = c.channel
    if kind == "NEW_UNIT":
        ch = channel or c.channel
        try:
            loc, mode = rules.validate_site(seg, ch, location, site_mode)
        except ValueError as e:
            raise FinanceError(str(e)) from None
        cost = quantize_money(cost * rules.online_scale(seg, ch))
        land = rules.land_value(seg, ch, mode, loc, c.size)
    if opt.fx.get("manager") and len(cs._employees(db, c)) >= rules.max_staff(c.size, c.units):
        raise ConflictError("Teto de funcionários atingido: não há vaga para o gerente. Amplie as instalações antes.")
    balance = cs.cash(db, c)
    if balance < cost + land:
        raise FinanceError(f"a empresa não tem caixa para este aporte ({quantize_money(cost + land)}); caixa atual: {balance}")
    n = (db.scalar(select(func.count()).select_from(CompanyExpansion).where(CompanyExpansion.company_id == c.id, CompanyExpansion.kind == kind)) or 0)
    key = (seed, c.id, f"{ref:%Y-%m}", kind, tier, option_key, n)
    line = "MARKETING" if kind == "MARKETING" else "EXPANSION"
    effects: list[str] = []
    xk = f"co:{c.id}:xp:{idempotency_key}"
    if kind == "NEW_UNIT":
        outcome, msg, effects = _open_unit(db, c, seg, ref, tier, opt, cost, ch, mode, loc, key, idempotency_key)
        paid = cost if outcome != "FAIL" else quantize_money(cost * D("0.5"))
        cs._post(db, c, ref, kind=FlowKind.EXPENSE, amount=paid, desc=f"Nova unidade: {opt.title} (nível {rules.TIER_LABEL[tier].lower()})",
                 line=line, key=f"{xk}:cost")
        if outcome != "FAIL" and land > 0:
            cs._post(db, c, ref, kind=FlowKind.EXPENSE, amount=land, desc=f"Compra do terreno da filial — {rules.resolve_location(seg, loc).label}",
                     line="LAND", key=f"{xk}:land")
        cost = paid + (land if outcome != "FAIL" else ZERO)
    else:
        cs._post(db, c, ref, kind=FlowKind.EXPENSE, amount=cost, desc=f"{'Campanha' if kind == 'MARKETING' else 'Aporte'}: {opt.title} "
                 f"(nível {rules.TIER_LABEL[tier].lower()})", line=line, key=f"{xk}:cost")
        if kind == "MARKETING":
            outcome, msg = _apply_marketing(db, c, ref, tier, opt, key, effects)
        else:
            outcome = _outcome(kind, tier, opt, *key)
            msgs = {"CAPACITY": ("A capacidade foi ampliada.", "A ampliação rendeu só parte do esperado.", "A ampliação não deu o resultado esperado: a capacidade não mudou."),
                    "QUALITY": ("A qualidade subiu como planejado.", "A qualidade subiu menos do que o esperado.", "O investimento não melhorou a qualidade."),
                    "LARGER_PREMISES": ("As instalações maiores ficaram prontas.", "A obra não chegou ao porte seguinte, mas deixou melhorias.", "A obra não saiu como previsto e nada mudou.")}[kind]
            msg = msgs[("FULL", "PARTIAL", "FAIL").index(outcome)]
            if outcome != "FAIL":
                if kind == "CAPACITY":
                    _apply_capacity(db, c, seg, ref, tier, opt, outcome, key, effects, idempotency_key)
                elif kind == "QUALITY":
                    _apply_quality(db, c, ref, tier, opt, outcome, effects)
                else:
                    _apply_larger(db, c, seg, ref, outcome, effects)
            else:
                effects.append("Nenhum efeito: o dinheiro foi gasto")
        if kind == "CAPACITY":
            warn = _supply_warning(db, c, seg, ref)
            if warn:
                effects.append(warn)
            effects.append("Produzir mais não significa vender mais: a demanda e a relevância continuam limitando as vendas")
    db.flush()
    cs._event(db, c, ref, CompanyEventType.EXPANSION, f"{opt.title} ({kind}, nível {rules.TIER_LABEL[tier].lower()}): {msg}", cost)
    _row(db, c, ref, kind, tier, option_key, idempotency_key, outcome, cost, msg, effects)
    return ExecResult(outcome != "FAIL", outcome, msg, effects, cost)
