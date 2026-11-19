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

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import (
    Company, CompanySegment, CompanyStatus, EconomyState, EntryOrigin, FlowKind, GameProfile, REAL_ESTATE, RecurringItem,
    RecurringItemVersion, SimMonth, TransactionSource, WorldEvent,
)
from backend.services import budget_service, finance_ledger, item_sync
from backend.services import economy_events as E
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError
from backend.services.life_rules import hash01

ONE = Decimal("1.0000")
D = Decimal
PREFIX = ("econ:",)
RANGES = {"inflation": (-2, 40), "interest": (1, 30), "unemployment": (2, 30), "growth": (-10, 10),
          "demand": (50, 150), "confidence": (0, 100)}
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


def asset_adjust(db: Session, user_id: int, ref: date, category) -> Decimal:
    """Variação extra (% no mês) do valor de um bem por economia e eventos."""
    st = get_state(db, user_id, ref)
    if st is None:
        return D("0")
    pct = 0.0
    if category in REAL_ESTATE:
        pct += (float(st.growth) - 2.0) * 0.03 - (float(st.interest) - 10.5) * 0.04
    for ev in active_events(db, user_id, ref):
        pct += ev.effects.get("assets_all_pct", 0)
        if category in REAL_ESTATE:
            pct += ev.effects.get("assets_pct", 0)
    return D(str(round(pct, 4)))


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
def _new_state(db: Session, user_id: int, ref: date, latent: dict, prev: EconomyState | None, offsets: dict,
               cat_changes: dict | None = None) -> EconomyState:
    disp = {k: _clamp(latent[k] + offsets.get(k, 0), *RANGES[k]) for k in RANGES}
    prev_idx = prev.indices if prev else {c: 1.0 for c in E.PRICE_CATEGORIES}
    changes = cat_changes or {c: 0.0 for c in E.PRICE_CATEGORIES}
    idx = {c: round(float(prev_idx.get(c, 1.0)) * (1 + changes.get(c, 0.0) / 100), 6) for c in E.PRICE_CATEGORIES}
    st = EconomyState(user_id=user_id, ref_month=ref, **{k: D(str(round(v, 4))) for k, v in disp.items()},
                      monthly_changes={**{c: round(v, 4) for c, v in changes.items()}, "_latent": latent}, indices=idx)
    db.add(st)
    db.flush()
    return st


def start_world(db: Session, user_id: int, month: SimMonth, *, seed: int, initial: dict | None = None) -> GameProfile:
    """Liga a economia dinâmica (uma vez) com semente e condições iniciais configuráveis."""
    g = get_game(db, user_id)
    if db.scalar(select(EconomyState.id).where(EconomyState.user_id == user_id).limit(1)):
        raise ConflictError("a economia desta partida já foi iniciada")
    latent = dict(E.INITIAL)
    for k, v in (initial or {}).items():
        if k not in RANGES:
            raise FinanceError(f"condição econômica desconhecida: {k}")
        lo, hi = RANGES[k]
        if not lo <= float(v) <= hi:
            raise FinanceError(f"{k} deve estar entre {lo} e {hi}")
        latent[k] = float(v)
    g.economy_mode, g.seed = "DYNAMIC", seed
    _new_state(db, user_id, month.ref_month, latent, None, {})
    return g


# ------------------------------------------------------------------ eventos
def _offsets(events: list[WorldEvent]) -> tuple[dict, dict]:
    macro = {k: 0.0 for k in RANGES}
    prices = {c: 0.0 for c in E.PRICE_CATEGORIES}
    for ev in events:
        for k in macro:
            macro[k] += ev.effects.get(k, 0)
        for c, v in ev.effects.get("prices", {}).items():
            prices[c] = prices.get(c, 0.0) + v
    return macro, prices


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


def _spawn(db: Session, user_id: int, ref: date, seed: int, macro: dict) -> list[WorldEvent]:
    ctx = _context(db, user_id, ref)
    new: list[WorldEvent] = []
    cap = {"world": 2, "user": 1}
    count = {"world": 0, "user": 0}
    for d in E.CATALOG:
        bucket = "world" if d.scope in ("WORLD", "SECTOR") else "user"
        if count[bucket] >= cap[bucket]:
            continue
        p = d.prob * d.cond(macro, ctx)
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
    if opt.cost:
        item = {"kind": "EXPENSE", "amount": opt.cost, "price_cat": "insumos" if ev.category == "BUSINESS" else "lazer",
                "label": f"{opt.label} — {ev.name}"}
        if ev.category == "BUSINESS":
            fx["company_oneoff"] = {"amount": opt.cost, "price_cat": "insumos", "label": opt.label}
        else:
            fx["oneoff"] = [item]
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


# ------------------------------------------------------------------ avanço mensal
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
    seed = g.seed
    # 2) fim de eventos e decisão automática dos pendentes
    for ev in db.scalars(select(WorldEvent).where(WorldEvent.user_id == user_id, WorldEvent.status != "ENDED")):
        if ev.status == "PENDING" and ev.start_month < ref:
            default = next(o for o in E.CATALOG_BY_KEY[ev.key].options if o.default)
            _resolve(db, ev, default.key, ref, seed)
        if ev.status == "ACTIVE" and ev.end_month < ref:
            ev.status = "ENDED"
    db.flush()
    # 1) condições (processo latente)
    lat = dict(prev.monthly_changes["_latent"]) if prev else dict(E.INITIAL)
    n = lambda name: hash01(seed, name, ref.isoformat()) * 2 - 1                  # noqa: E731
    lat["growth"] = 0.85 * lat["growth"] + 0.15 * 2.0 + 0.6 * n("g")
    lat["inflation"] = 0.88 * lat["inflation"] + 0.12 * 4.5 + 0.25 * n("i") + 0.03 * (lat["demand"] - 100)
    lat["unemployment"] = lat["unemployment"] - 0.12 * (lat["growth"] - 2) + 0.05 * (8 - lat["unemployment"]) + 0.15 * n("u")
    lat["interest"] = 0.9 * lat["interest"] + 0.1 * (10.5 + (lat["inflation"] - 4.5)) + 0.1 * n("r")
    lat["confidence"] = _clamp(0.7 * lat["confidence"] + 0.3 * (55 + 6 * (lat["growth"] - 2) - 3 * (lat["unemployment"] - 8)
                                                                  - 2 * (lat["inflation"] - 4.5)) + 2 * n("c"), 0, 100)
    lat["demand"] = 100 + 4 * (lat["growth"] - 2) - 1.5 * (lat["unemployment"] - 8) + 0.1 * (lat["confidence"] - 55)
    for k, (lo, hi) in RANGES.items():
        lat[k] = _clamp(lat[k], lo, hi)
    # 3) novos eventos (condições usam o estado já com os eventos ainda ativos)
    macro_now = {k: _clamp(lat[k] + _offsets(active_events(db, user_id, ref))[0][k], *RANGES[k]) for k in RANGES}
    _spawn(db, user_id, ref, seed, macro_now)
    # 4) índices de preços
    offs, price_pp = _offsets(active_events(db, user_id, ref))
    infl = _clamp(lat["inflation"] + offs["inflation"], *RANGES["inflation"])
    changes = {}
    for cat in E.PRICE_CATEGORIES:
        beta, vol = E.BETA[cat]
        noise = hash01(seed, "cat", cat, ref.isoformat()) * 2 - 1
        changes[cat] = infl / 12 * beta + 0.25 * vol * noise + price_pp.get(cat, 0.0)
    _new_state(db, user_id, ref, lat, prev, offs, changes)
    # 5) recorrências indexadas  6) itens gerados por eventos
    _apply_indexation(db, user_id, ref)
    sync_month(db, user_id, new_month)
