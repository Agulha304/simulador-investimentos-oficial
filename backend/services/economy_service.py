"""Economia simulada e eventos (etapa 5).

Uma única economia por usuário/partida, consultada por TODOS os módulos (orçamento, família, empresas, bens,
financiamentos) — nunca há valores econômicos independentes por módulo.

Ordem na abertura de cada mês (`advance_to_month`, chamada pelo fechamento mensal):
  1. condições econômicas (processo latente determinístico)  2. fim/decisão automática de eventos
  3. novos eventos (probabilidades condicionadas ao estado)  4. índices de preços por categoria
  5. reajuste das recorrências indexadas  6. itens do orçamento gerados pelos eventos.
Os módulos dependentes (itens recorrentes, bens, família) rodam DEPOIS no fechamento, já com os novos índices.

Idempotência: `EconomyState` é único por (usuário, mês) e `WorldEvent` por (usuário, chave, início): reprocessar o
mês não repete nada. Reprodutibilidade: toda aleatoriedade usa `hash01(seed, ...)`.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import (
    Company, CompanySegment, CompanyStatus, EconomicCrisis, EconomyState, Relationship, EntryOrigin, FlowKind, GameProfile, REAL_ESTATE, RecurringItem,
    RecurringItemVersion, SimMonth, TransactionSource, WorldEvent,
)
from backend.services import budget_service, finance_ledger, item_sync
from backend.services import economy_events as E
from backend.services.engine import crises as engine_crises
from backend.services.engine import world as engine_world
from backend.services.engine.params import SimParams
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError
from backend.services.life_rules import hash01

ONE = Decimal("1.0000")
D = Decimal
PREFIX = ("econ:",)
RANGES = {"inflation": (-2, 40), "interest": (1, 30), "unemployment": (2, 30), "growth": (-10, 10),
          "demand": (50, 150), "confidence": (0, 100)}
# nomes públicos (colunas) -> nomes do motor
ENGINE_KEY = {"interest": "policy", "confidence": "consumer_conf"}
EXTRA_START = {"fx": (2.0, 30.0), "credit": (5, 95), "liquidity": (5, 100), "household_debt": (20, 130), "firm_debt": (20, 160),
               "business_conf": (0, 100), "commodity": (30, 400), "risk_appetite": (0, 100)}
CAT_NAME = {"saude": "Saúde", "alimentacao": "Alimentação", "moradia": "Moradia", "transporte": "Transporte",
            "educacao": "Educação", "lazer": "Lazer", "vestuario": "Vestuário"}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ------------------------------------------------------------------ perfil da partida
def get_game(db: Session, user_id: int, *, create: bool = True) -> GameProfile | None:
    g = db.scalar(select(GameProfile).where(GameProfile.user_id == user_id))
    if g is None and create:
        g = GameProfile(user_id=user_id, mode="FREE", economy_mode="STATIC", seed=user_id)
        db.add(g)
        db.flush()
    return g


def is_dynamic(db: Session, user_id: int) -> bool:
    g = get_game(db, user_id, create=False)
    return g is not None and g.economy_mode == "DYNAMIC"


def get_state(db: Session, user_id: int, ref: date) -> EconomyState | None:
    """Estado vigente no mês (o mais recente até `ref`)."""
    return db.scalar(select(EconomyState).where(
        EconomyState.user_id == user_id, EconomyState.ref_month <= ref).order_by(EconomyState.ref_month.desc()).limit(1))


def history(db: Session, user_id: int, limit: int = 36) -> list[EconomyState]:
    rows = list(db.scalars(select(EconomyState).where(EconomyState.user_id == user_id)
                           .order_by(EconomyState.ref_month.desc()).limit(limit)))
    return rows[::-1]


# ------------------------------------------------------------------ consultas usadas pelos outros módulos
def index_value(db: Session, user_id: int, ref_month: date, category: str) -> Decimal:
    st = get_state(db, user_id, ref_month)
    if st is None:
        return ONE
    return D(str(st.indices.get(category, 1)))


def financing_rate_add(db: Session, user_id: int, ref_month: date) -> Decimal:
    """Pontos percentuais somados às taxas de financiamento/empréstimo (juros acima/abaixo do nível inicial)."""
    st = get_state(db, user_id, ref_month)
    if st is None:
        return D("0")
    return (st.interest - D(str(E.INITIAL["interest"]))).quantize(D("0.0001"))


def active_events(db: Session, user_id: int, ref: date) -> list[WorldEvent]:
    return list(db.scalars(select(WorldEvent).where(
        WorldEvent.user_id == user_id, WorldEvent.status == "ACTIVE", WorldEvent.start_month <= ref,
        WorldEvent.end_month >= ref).order_by(WorldEvent.id)))


def engine_of(st: EconomyState | None) -> dict:
    return (st.engine or {}) if st is not None else {}


def asset_adjust(db: Session, user_id: int, ref: date, category) -> Decimal:
    """Variação extra (% no mês) do valor de um bem: imóveis seguem o índice imobiliário do motor (juros, crescimento,
    crédito e crises); eventos de valorização/desvalorização entram direto."""
    st = get_state(db, user_id, ref)
    if st is None:
        return D("0")
    pct = 0.0
    eng = engine_of(st)
    if category in REAL_ESTATE:
        if "house_ret" in eng.get("info", {}):
            pct += eng["info"]["house_ret"]
        else:                                                    # estado antigo (sem motor): regra simples
            pct += (float(st.growth) - 2.0) * 0.03 - (float(st.interest) - 10.5) * 0.04
    for ev in active_events(db, user_id, ref):
        pct += ev.effects.get("assets_all_pct", 0)
        if category in REAL_ESTATE:
            pct += ev.effects.get("assets_pct", 0)
    return D(str(round(pct, 4)))


def vacancy_boost(db: Session, user_id: int, ref: date) -> float:
    """Pressão de vacância (crise imobiliária): 0 = normal."""
    return float(engine_of(get_state(db, user_id, ref)).get("info", {}).get("crisis_effects", {}).get("vacancy", 0.0))


def _company_events(db: Session, c: Company, ref: date) -> list[WorldEvent]:
    out = []
    for ev in active_events(db, c.user_id, ref):
        if ev.scope == "WORLD" or (ev.scope == "SECTOR" and ev.sector == c.segment.value) or \
                (ev.scope == "COMPANY" and ev.company_id == c.id):
            out.append(ev)
    return out


def company_demand_mult(db: Session, c: Company, ref: date) -> float:
    st = get_state(db, c.user_id, ref)
    if st is None:
        return 1.0
    mult = float(st.demand) / 100.0
    sector = engine_of(st).get("info", {}).get("sector", {}).get(c.segment.value, 0.0)       # efeito das crises no setor
    mult *= max(0.2, 1 + sector / 100.0)
    for ev in _company_events(db, c, ref):
        mult *= 1 + ev.effects.get("company_demand_pct", 0) / 100.0
    return mult


def supplier_category(c: Company) -> str:
    if c.segment.value in E.FOOD_SEGMENTS:
        return "alimentacao"
    return "materiais_construcao" if c.segment.value == "CONSTRUCTION" else "insumos"


def supplier_mult(db: Session, c: Company, ref: date) -> Decimal:
    st = get_state(db, c.user_id, ref)
    if st is None:
        return D(1)
    m = D(str(st.indices.get(supplier_category(c), 1)))
    for ev in _company_events(db, c, ref):
        m *= 1 + D(str(ev.effects.get("supplier_pct", 0))) / 100
    return m


# ------------------------------------------------------------------ início do mundo
def sim_params(db: Session, user_id: int) -> SimParams:
    g = get_game(db, user_id, create=False)
    return SimParams.from_dict((g.config or {}).get("sim") if g else None)


def _persist_state(db: Session, user_id: int, ref: date, ws, info) -> EconomyState:
    m = ws.macro
    eng = ws.to_dict()
    eng["info"] = {"factors": info.factors if info else {}, "class_ret": info.crisis_effects.get("class_ret", {}) if info else {},
                   "sector": info.crisis_effects.get("sector", {}) if info else {}, "house_ret": info.house_ret if info else 0.0,
                   "crisis_effects": {k: v for k, v in (info.crisis_effects if info else {}).items() if k not in ("class_ret", "sector")}}
    st = EconomyState(user_id=user_id, ref_month=ref, inflation=D(str(round(m["inflation"], 4))), interest=D(str(round(m["policy"], 4))),
                      unemployment=D(str(round(m["unemployment"], 4))), growth=D(str(round(m["growth"], 4))),
                      demand=D(str(round(m["demand"], 4))), confidence=D(str(round(m["consumer_conf"], 4))),
                      monthly_changes={k: round(v, 4) for k, v in ws.changes.items()}, indices=ws.indices, engine=eng)
    eng["regime"] = ws.regime
    db.add(st)
    db.flush()
    return st


def _persist_crises(db: Session, user_id: int, ws, ref: date) -> None:
    for d in ws.crises:
        c = engine_crises.Crisis.from_dict(d)
        start = date.fromisoformat(c.start + "-01")
        row = db.scalar(select(EconomicCrisis).where(EconomicCrisis.user_id == user_id, EconomicCrisis.type == c.type,
                                                     EconomicCrisis.start_month == start))
        label, _, _, _, sectors, classes = engine_crises.TYPES[c.type]
        if row is None:
            row = EconomicCrisis(user_id=user_id, type=c.type, label=label, start_month=start, sectors=sectors, assets=classes,
                                 triggers=c.triggers)
            db.add(row)
        row.phase, row.intensity, row.peak, row.path = c.phase, D(str(round(c.intensity, 3))), D(str(round(c.peak, 3))), c.path
        if c.ended:
            row.status, row.end_month = "ENDED", date.fromisoformat(c.ended + "-01")
    db.flush()


def start_world(db: Session, user_id: int, month: SimMonth, *, seed: int, initial: dict | None = None,
                sim: dict | None = None) -> GameProfile:
    """Liga a economia dinâmica (uma vez) com semente, condições iniciais e parâmetros de simulação configuráveis."""
    g = get_game(db, user_id)
    if db.scalar(select(EconomyState.id).where(EconomyState.user_id == user_id).limit(1)):
        raise ConflictError("a economia desta partida já foi iniciada")
    over: dict = {}
    for k, v in (initial or {}).items():
        if k in RANGES:
            lo, hi = RANGES[k]
        elif k in EXTRA_START:
            lo, hi = EXTRA_START[k]
        else:
            raise FinanceError(f"condição econômica desconhecida: {k}")
        if not lo <= float(v) <= hi:
            raise FinanceError(f"{k} deve estar entre {lo} e {hi}")
        over[ENGINE_KEY.get(k, k)] = float(v)
    if "growth" in over:                                         # crescimento inicial vira hiato do produto equivalente
        over["gap"] = (over.pop("growth") - 2.0) / 0.8
    g.economy_mode, g.seed = "DYNAMIC", seed
    g.config = {**(g.config or {}), "sim": SimParams.from_dict(sim).__dict__}
    ws = engine_world.initial_world(over)
    ws.macro["growth"] = float(initial["growth"]) if initial and "growth" in initial else ws.macro["growth"]
    _persist_state(db, user_id, month.ref_month, ws, None)
    return g


def ws_of(st: EconomyState) -> engine_world.WorldState:
    """Estado do motor guardado no mês (ou conversão de um estado antigo, anterior ao motor)."""
    if st.engine and "macro" in st.engine:
        return engine_world.WorldState.from_dict({k: v for k, v in st.engine.items() if k not in ("info",)})
    over = {"inflation": float(st.inflation), "policy": float(st.interest), "unemployment": float(st.unemployment),
            "consumer_conf": float(st.confidence), "demand": float(st.demand), "gap": (float(st.growth) - 2.0) / 0.8}
    ws = engine_world.initial_world(over)
    for c, v in (st.indices or {}).items():
        ws.indices[c] = v
    return ws


# ------------------------------------------------------------------ eventos
def _context(db: Session, user_id: int, ref: date) -> dict:
    from backend.services import life_service
    g = get_game(db, user_id)
    prof = life_service.get_profile(db, user_id, create=False)
    partner = life_service.active_partner(db, user_id) if prof else None
    return {
        "companies": list(db.scalars(select(Company).where(Company.user_id == user_id, Company.status == CompanyStatus.ACTIVE)
                                     .order_by(Company.id))),
        "health": prof.health if prof else 70, "work_level": prof.work_level if prof else "NORMAL",
        "housing_kind": prof.housing_kind if prof else "EXISTING", "partner": partner is not None,
        "children": bool(prof and life_service.children(db, user_id)),
        "relationships": bool(prof and db.scalar(select(func.count(Relationship.id)).where(
            Relationship.user_id == user_id, Relationship.stage != "ENDED"))),
        "salary": item_sync.salary_total(db, user_id, ref),
        "months": budget_service.months_between(g.started_month, ref) if g.started_month else 12,
    }


def _make_event(db: Session, user_id: int, d: E.EventDef, ref: date, seed: int, ctx: dict) -> WorldEvent | None:
    sector = company = None
    name = d.name
    if d.scope == "SECTOR":
        pool = d.sectors or tuple(s.value for s in CompanySegment)
        sector = pool[int(hash01(seed, "sector", d.key, ref.isoformat()) * len(pool)) % len(pool)]
        name = f"{d.name} ({sector.lower()})"
    elif d.scope == "COMPANY":
        cs = ctx["companies"]
        if not cs:
            return None
        co = cs[int(hash01(seed, "co", d.key, ref.isoformat(), user_id) * len(cs)) % len(cs)]
        company, sector, name = co.id, co.segment.value, f"{d.name} — {co.name}"
    lo, hi = d.duration
    who = user_id if d.scope in ("USER", "COMPANY") else 0           # eventos de mundo: iguais para quem divide a semente
    dur = lo + int(hash01(seed, "dur", d.key, ref.isoformat(), who) * (hi - lo + 1))
    ev = WorldEvent(user_id=user_id, key=d.key, name=name[:80], description=d.description, category=d.category,
                    scope=d.scope, sector=sector, company_id=company, positive=d.positive, intensity=d.intensity,
                    start_month=ref, end_month=budget_service.shift_month(ref, dur - 1), effects=dict(d.effects))
    if d.options:
        ev.status = "PENDING"
        ev.options = [{"key": o.key, "label": o.label, "hint": o.hint, "cost": o.cost} for o in d.options]
    db.add(ev)
    db.flush()
    return ev


def _activate(db: Session, ev: WorldEvent, ref: date) -> None:
    """Efeitos de ativação (uma única vez, protegidos pelo status): vida pessoal e despesas únicas."""
    from backend.services import life_service
    fx = dict(ev.effects)
    life_fx = fx.get("life")
    if life_fx:
        prof = life_service.get_profile(db, ev.user_id, create=False)
        if prof is not None:
            for attr, delta in life_fx.items():
                setattr(prof, attr, life_service._clamp(getattr(prof, attr) + delta))
            life_service.log(db, ev.user_id, ref, "EVENT", f"{ev.name}: {ev.description}", event_id=ev.id)
    aff = fx.get("relationship_affinity")
    if aff:
        for r in db.scalars(select(Relationship).where(Relationship.user_id == ev.user_id, Relationship.stage != "ENDED")):
            r.affinity = life_service._clamp(r.affinity + aff)
            r.last_interaction_month = ref if aff > 0 else r.last_interaction_month
    oneoff = []
    for i, o in enumerate(fx.get("oneoff", [])):
        amt = quantize_money(D(str(o["amount"])) * index_value(db, ev.user_id, ref, o.get("price_cat", "insumos")))
        oneoff.append({**o, "amount": str(amt), "month": ref.isoformat(), "i": i})
    if oneoff:
        fx["oneoff"] = oneoff
    co = fx.pop("company_oneoff", None)
    if co and ev.company_id:
        c = db.get(Company, ev.company_id)
        from backend.services import company_service
        amt = quantize_money(D(str(co["amount"])) * index_value(db, ev.user_id, ref, co.get("price_cat", "insumos")))
        company_service._post(db, c, ref, kind=FlowKind.EXPENSE, amount=amt, desc=f"{co['label']} (evento)", line="FIXED",
                              key=f"econ:ev:{ev.id}:company", overdraft=True)
    ev.effects = fx


def _spawn(db: Session, user_id: int, ref: date, seed: int, macro: dict, freq: float = 1.0) -> list[WorldEvent]:
    ctx = _context(db, user_id, ref)
    new: list[WorldEvent] = []
    cap = {"world": 2, "user": 1}
    count = {"world": 0, "user": 0}
    for d in E.CATALOG:
        bucket = "world" if d.scope in ("WORLD", "SECTOR") else "user"
        if count[bucket] >= cap[bucket]:
            continue
        p = d.prob * d.cond(macro, ctx) * freq
        if p <= 0:
            continue
        busy = db.scalar(select(WorldEvent.id).where(
            WorldEvent.user_id == user_id, WorldEvent.key == d.key,
            WorldEvent.end_month >= budget_service.shift_month(ref, -6)).limit(1))     # sem repetição imediata
        if busy:
            continue
        who = user_id if bucket == "user" else 0
        if hash01(seed, "ev", d.key, ref.isoformat(), who) >= min(0.6, p):
            continue
        ev = _make_event(db, user_id, d, ref, seed, ctx)
        if ev is None:
            continue
        count[bucket] += 1
        if ev.status == "ACTIVE":
            _activate(db, ev, ref)
        new.append(ev)
    return new


def _resolve(db: Session, ev: WorldEvent, option_key: str, month_ref: date, seed: int) -> WorldEvent:
    d = E.CATALOG_BY_KEY[ev.key]
    opt = next((o for o in d.options if o.key == option_key), None)
    if opt is None:
        raise FinanceError("opção inválida para este evento")
    r, acc, chosen = hash01(seed, "dec", ev.key, ev.start_month.isoformat(), opt.key, ev.user_id), 0.0, opt.outcomes[-1]
    for oc in opt.outcomes:
        acc += oc.prob
        if r < acc:
            chosen = oc
            break
    fx = dict(chosen.effects)
    oneoff = list(fx.get("oneoff", []))
    if opt.cost:
        if ev.category == "BUSINESS":
            fx["company_oneoff"] = {"amount": opt.cost, "price_cat": "insumos", "label": opt.label}
        else:
            oneoff.append({"kind": "EXPENSE", "amount": opt.cost, "price_cat": "lazer", "label": f"{opt.label} — {ev.name}"})
    if oneoff:
        fx["oneoff"] = oneoff
    ev.effects, ev.choice, ev.outcome = fx, opt.key, chosen.text
    ev.start_month = min(ev.start_month, month_ref)
    ev.end_month = budget_service.shift_month(month_ref, max(chosen.duration, 1) - 1)
    ev.status = "ACTIVE"
    _activate(db, ev, month_ref)
    db.flush()
    return ev


def decide(db: Session, user_id: int, month: SimMonth, event_id: int, option_key: str) -> WorldEvent:
    budget_service.require_open(month)
    ev = db.scalar(select(WorldEvent).where(WorldEvent.id == event_id, WorldEvent.user_id == user_id).with_for_update())
    if ev is None:
        raise NotFoundError("evento não encontrado")
    if ev.status != "PENDING":
        raise ConflictError("este evento não aguarda decisão")
    _resolve(db, ev, option_key, month.ref_month, get_game(db, user_id).seed)
    sync_month(db, user_id, month)
    return ev


# ------------------------------------------------------------------ itens do orçamento gerados pelos eventos
def sync_month(db: Session, user_id: int, month: SimMonth) -> None:
    if month.status.value != "OPEN" or not is_dynamic(db, user_id):
        return
    ref = month.ref_month
    desired: dict[str, dict] = {}
    salary = item_sync.salary_total(db, user_id, ref)
    for ev in db.scalars(select(WorldEvent).where(WorldEvent.user_id == user_id, WorldEvent.status.in_(("ACTIVE", "ENDED")))):
        for o in ev.effects.get("oneoff", []):
            if o.get("month") == ref.isoformat():
                amt = D(o["amount"])
                if amt > 0:
                    kind = FlowKind(o["kind"])
                    desired[f"econ:{ev.id}:oneoff:{o['i']}"] = {
                        "name": o["label"], "kind": kind, "amount": amt,
                        "cat": CAT_NAME.get(o.get("price_cat"), "Outros") if kind == FlowKind.EXPENSE else "Renda extra"}
        pct = ev.effects.get("income_pct")
        if pct and ev.status == "ACTIVE" and ev.start_month <= ref <= ev.end_month and salary > 0:
            amt = quantize_money(salary * D(str(abs(pct))) / 100)
            up = pct > 0
            desired[f"econ:{ev.id}:income"] = {
                "name": f"{ev.name}: {'ganho' if up else 'perda'} de renda", "kind": FlowKind.INCOME if up else FlowKind.EXPENSE,
                "amount": amt, "cat": "Renda extra" if up else "Outros"}
    item_sync.reconcile(db, user_id, month, desired, PREFIX)


# ------------------------------------------------------------------ indexação das recorrências
def set_indexation(db: Session, user_id: int, item_id: int, mode: str, category: str | None) -> RecurringItem:
    r = db.get(RecurringItem, item_id)
    if r is None or r.user_id != user_id:
        raise NotFoundError("item recorrente não encontrado")
    if mode not in ("NONE", "MONTHLY", "ANNUAL"):
        raise FinanceError("modo de reajuste inválido")
    if mode != "NONE" and category not in E.PRICE_CATEGORIES:
        raise FinanceError("informe uma categoria de preços válida")
    r.indexation, r.index_category = mode, (category if mode != "NONE" else None)
    db.flush()
    return r


def _apply_indexation(db: Session, user_id: int, ref: date) -> None:
    prev_ref = budget_service.shift_month(ref, -1)
    for r in db.scalars(select(RecurringItem).where(
            RecurringItem.user_id == user_id, RecurringItem.active.is_(True), RecurringItem.indexation != "NONE")):
        if r.start_month >= ref or (r.end_month and r.end_month < ref):
            continue
        cat = r.index_category
        now = index_value(db, user_id, ref, cat)
        if r.indexation == "MONTHLY":
            base = index_value(db, user_id, prev_ref, cat)
        else:
            if budget_service.months_between(r.start_month, ref) % 12 != 0:
                continue
            base = index_value(db, user_id, budget_service.shift_month(ref, -12), cat)
        if base <= 0 or now == base:
            continue
        if db.scalar(select(RecurringItemVersion.id).where(
                RecurringItemVersion.item_id == r.id, RecurringItemVersion.effective_from == ref)):
            continue
        cur = budget_service.version_amount(db, r.id, ref)
        if cur is None:
            continue
        new = quantize_money(cur * now / base)
        if new > 0 and new != cur:
            db.add(RecurringItemVersion(item_id=r.id, amount=new, effective_from=ref))
    db.flush()


def ensure_monthly_decision(db: Session, user_id: int, month: SimMonth) -> WorldEvent | None:
    """Garante UMA decisão (financeira ou pessoal) para o mês. Alterna o tipo mês a mês e não repete nos últimos 6 meses. Idempotente."""
    g = get_game(db, user_id, create=False)
    if g is None or g.economy_mode != "DYNAMIC" or month.status.value != "OPEN":
        return None
    ref = month.ref_month
    existing = db.scalar(select(WorldEvent).where(WorldEvent.user_id == user_id, WorldEvent.start_month == ref,
                                                  WorldEvent.key.in_(list(E.MONTHLY_BY_KEY))))
    if existing is not None:
        return existing
    recent = set(db.scalars(select(WorldEvent.key).where(WorldEvent.user_id == user_id,
                                                         WorldEvent.start_month >= budget_service.shift_month(ref, -6))))
    st = get_state(db, user_id, ref)
    macro = _macro_view(ws_of(st)) if st else {"inflation": 4.5, "interest": 10.5, "unemployment": 8, "growth": 2, "demand": 100, "confidence": 55}
    ctx = _context(db, user_id, ref)
    want = "FINANCIAL" if (ref.year * 12 + ref.month) % 2 == 0 else "PERSONAL"
    for cat in (want, "PERSONAL" if want == "FINANCIAL" else "FINANCIAL"):
        pool = [(d, d.cond(macro, ctx)) for d in E.MONTHLY if d.category == cat and d.key not in recent]
        pool = [(d, w) for d, w in pool if w > 0]
        if not pool:
            continue
        total = sum(w for _, w in pool)
        r, acc = hash01(g.seed, "monthly", ref.isoformat(), user_id) * total, 0.0
        for d, w in pool:
            acc += w
            if r <= acc:
                return _make_event(db, user_id, d, ref, g.seed, ctx)
        return _make_event(db, user_id, pool[-1][0], ref, g.seed, ctx)
    return None


# ------------------------------------------------------------------ avanço mensal
def _event_shocks(events: list[WorldEvent]) -> dict:
    """Efeitos dos eventos de MUNDO viram choques nas equações do motor (não deslocamentos da tela): persistem pela dinâmica."""
    sh: dict = {"price_pp": {}}
    for ev in events:
        if ev.scope != "WORLD":
            continue
        fx = ev.effects
        sh["demand"] = sh.get("demand", 0.0) + 0.25 * fx.get("growth", 0) + 0.05 * fx.get("demand", 0)
        sh["conf"] = sh.get("conf", 0.0) + 0.4 * fx.get("confidence", 0)
        sh["unemp"] = sh.get("unemp", 0.0) + 0.08 * fx.get("unemployment", 0)
        sh["policy"] = sh.get("policy", 0.0) + 0.25 * fx.get("interest", 0)
        sh["supply"] = sh.get("supply", 0.0) + 0.5 * fx.get("inflation", 0)
        sh["assets_all"] = sh.get("assets_all", 0.0) + fx.get("assets_all_pct", 0)
        for c, v in fx.get("prices", {}).items():
            sh["price_pp"][c] = sh["price_pp"].get(c, 0.0) + v
    return sh


def _macro_view(ws) -> dict:
    m = ws.macro
    return {"inflation": m["inflation"], "interest": m["policy"], "unemployment": m["unemployment"], "growth": m["growth"],
            "demand": m["demand"], "confidence": m["consumer_conf"]}


def advance_to_month(db: Session, user_id: int, new_month: SimMonth) -> None:
    g = get_game(db, user_id, create=False)
    if g is None or g.economy_mode != "DYNAMIC":
        return
    ref = new_month.ref_month
    if db.scalar(select(EconomyState.id).where(EconomyState.user_id == user_id, EconomyState.ref_month == ref)):
        sync_month(db, user_id, new_month)               # reprocessamento: nada de novo, só garante os itens
        return
    prev = db.scalar(select(EconomyState).where(
        EconomyState.user_id == user_id, EconomyState.ref_month < ref).order_by(EconomyState.ref_month.desc()).limit(1))
    seed, params = g.seed, sim_params(db, user_id)
    # 1) fim de eventos e decisão automática dos pendentes
    for ev in db.scalars(select(WorldEvent).where(WorldEvent.user_id == user_id, WorldEvent.status != "ENDED")):
        if ev.status == "PENDING" and ev.start_month < ref:
            default = next(o for o in E.CATALOG_BY_KEY[ev.key].options if o.default)
            _resolve(db, ev, default.key, ref, seed)
        if ev.status == "ACTIVE" and ev.end_month < ref:
            ev.status = "ENDED"
    db.flush()
    ws = ws_of(prev) if prev else engine_world.initial_world()
    # 2) novos eventos aleatórios (probabilidade condicionada ao estado econômico atual)
    _spawn(db, user_id, ref, seed, _macro_view(ws), params.event_frequency)
    ensure_monthly_decision(db, user_id, new_month)                      # a decisão do mês (aparece antes do resumo do fechamento)
    shocks = _event_shocks(active_events(db, user_id, ref))
    # 3) motor: crises, regimes, macro, inflação por categoria, câmbio, crédito e fatores de mercado
    ws2, info = engine_world.step(ws, seed, f"{ref.year:04d}-{ref.month:02d}", params, shocks)
    st = _persist_state(db, user_id, ref, ws2, info)
    _persist_crises(db, user_id, ws2, ref)
    # 4) preços dos ativos já em uso e relógio da requisição
    from backend.core.clock import get_clock
    from backend.services import sim_market
    sim_market.roll_forward(db, user_id, st, seed)
    clock = get_clock()
    if clock is not None and clock.kind == "SIMULATED" and getattr(clock, "world", None) is not None:
        clock.world.advance(ref, D(str(round(ws2.macro["fx"], 4))))
    # 5) recorrências indexadas e itens do orçamento gerados por eventos
    _apply_indexation(db, user_id, ref)
    sync_month(db, user_id, new_month)
