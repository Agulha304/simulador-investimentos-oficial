"""Economia simulada e eventos (etapa 5)."""
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.dependencies import CurrentUser, DbSession
from backend.models import EconomicCrisis, EconomyState, WorldEvent
from backend.routers.budget import _run
from backend.services import budget_service as bs
from backend.services import economy_events as E
from backend.services import economy_service as es

router = APIRouter(prefix="/economy", tags=["economy"])


class DecisionIn(BaseModel):
    option: str


class IndexationIn(BaseModel):
    mode: str
    category: str | None = None


class ParamsIn(BaseModel):
    volatility: float | None = None
    event_frequency: float | None = None
    crisis_frequency: float | None = None
    crisis_severity: float | None = None
    shock_scale: float | None = None


def state_out(st: EconomyState) -> dict:
    eng = st.engine or {}
    m = eng.get("macro", {})
    return {"month": st.ref_month.isoformat(), "inflation": str(st.inflation), "interest": str(st.interest),
            "unemployment": str(st.unemployment), "growth": str(st.growth), "demand": str(st.demand),
            "confidence": str(st.confidence),
            "monthly_changes": {k: v for k, v in (st.monthly_changes or {}).items() if not k.startswith("_")},
            "indices": st.indices,
            "fx": m.get("fx"), "credit": m.get("credit"), "liquidity": m.get("liquidity"), "business_conf": m.get("business_conf"),
            "household_debt": m.get("household_debt"), "firm_debt": m.get("firm_debt"), "default_rate": m.get("default_rate"),
            "wage_growth": m.get("wage_growth"), "regime": eng.get("regime"), "class_index": eng.get("class_index"),
            "general_inflation_month": (st.monthly_changes or {}).get("geral")}


def crisis_out(c: EconomicCrisis) -> dict:
    return {"id": c.id, "type": c.type, "label": c.label, "start_month": c.start_month.isoformat(),
            "end_month": c.end_month.isoformat() if c.end_month else None, "status": c.status, "phase": c.phase,
            "intensity": float(c.intensity), "peak": float(c.peak), "sectors": c.sectors, "assets": c.assets,
            "triggers": c.triggers, "path": c.path}


def event_out(ev: WorldEvent) -> dict:
    """Eventos pendentes mostram só as alternativas e dicas: os resultados ficam ocultos até a decisão."""
    out = {"id": ev.id, "key": ev.key, "name": ev.name, "description": ev.description, "category": ev.category,
           "scope": ev.scope, "sector": ev.sector, "company_id": ev.company_id, "positive": ev.positive,
           "intensity": ev.intensity, "start_month": ev.start_month.isoformat(), "end_month": ev.end_month.isoformat(),
           "status": ev.status, "choice": ev.choice, "outcome": ev.outcome}
    if ev.status == "PENDING":
        out["options"] = ev.options
    else:
        out["effects"] = {k: v for k, v in ev.effects.items() if k not in ("oneoff", "company_oneoff")}
    return out


def overview(db: Session, user_id: int) -> dict:
    month = bs.ensure_setup(db, user_id)
    g = es.get_game(db, user_id)
    st = es.get_state(db, user_id, month.ref_month)
    events = list(db.scalars(select(WorldEvent).where(WorldEvent.user_id == user_id).order_by(WorldEvent.id.desc()).limit(60)))
    return {
        "month": month.ref_month.isoformat(), "dynamic": g.economy_mode == "DYNAMIC", "seed": g.seed,
        "state": state_out(st) if st else None,
        "history": [state_out(x) for x in es.history(db, user_id)],
        "categories": [{"key": k, "label": E.CATEGORY_LABEL[k]} for k in E.PRICE_CATEGORIES],
        "params": es.sim_params(db, user_id).__dict__,
        "crises": [crisis_out(c) for c in db.scalars(select(EconomicCrisis).where(EconomicCrisis.user_id == user_id)
                                                     .order_by(EconomicCrisis.start_month.desc()))],
        "pending": [event_out(e) for e in events if e.status == "PENDING"],
        "active": [event_out(e) for e in events if e.status == "ACTIVE"],
        "past": [event_out(e) for e in events if e.status == "ENDED"],
    }


@router.get("")
def get_economy(user: CurrentUser, db: DbSession):
    return _run(db, lambda: overview(db, user.id))


@router.post("/events/{event_id}/decide")
def decide(event_id: int, body: DecisionIn, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        ev = es.decide(db, user.id, month, event_id, body.option)
        return {"event": event_out(ev)}
    return _run(db, go)


@router.put("/recurring/{item_id}/indexation")
def indexation(item_id: int, body: IndexationIn, user: CurrentUser, db: DbSession):
    def go():
        r = es.set_indexation(db, user.id, item_id, body.mode, body.category)
        return {"id": r.id, "indexation": r.indexation, "index_category": r.index_category}
    return _run(db, go)


@router.put("/params")
def set_params(body: ParamsIn, user: CurrentUser, db: DbSession):
    """Parâmetros da simulação (volatilidade, frequência de eventos, frequência e severidade das crises): valem dos próximos meses em diante."""
    def go():
        from backend.services.engine.params import SimParams
        g = es.get_game(db, user.id)
        cur = {**es.sim_params(db, user.id).__dict__, **{k: v for k, v in body.model_dump().items() if v is not None}}
        try:
            g.config = {**(g.config or {}), "sim": SimParams.from_dict(cur).__dict__}
        except ValueError as e:
            from backend.services.finance_ledger import FinanceError
            raise FinanceError(str(e))
        return g.config["sim"]
    return _run(db, go)
