"""Partidas salvas e modo treino (conta real, sem X-Game-Id)."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.core.dates import today_br
from backend.dependencies import AccountUser, DbSession
from backend.models import Achievement, Game, GameProfile, LessonProgress, PortfolioSnapshot, Portfolio, SimMonth
from backend.routers.budget import _run
from backend.services.finance_ledger import ConflictError, FinanceError
from backend.services import game_service as gs
from backend.services import progression_rules as P
from backend.content.course import TOTAL_LESSONS

router = APIRouter(prefix="/games", tags=["games"])


class CreateIn(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=60)
    start_date: date | None = None


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class AdvanceIn(BaseModel):
    months: int = Field(default=1, ge=1, le=24)


class DateIn(BaseModel):
    date: date


class MoneyIn(BaseModel):
    amount: Decimal = Field(gt=0)


def _out(db, g: Game) -> dict:
    snap = db.scalar(select(PortfolioSnapshot).join(Portfolio, Portfolio.id == PortfolioSnapshot.portfolio_id).where(
        Portfolio.user_id == g.world_user_id).order_by(PortfolioSnapshot.taken_at.desc()).limit(1))
    out = {"id": g.id, "kind": g.kind, "name": g.name, "status": g.status, "created_at": g.created_at.isoformat(),
           "last_played_at": g.last_played_at.isoformat(), "equity_brl": str(snap.equity_brl) if snap else None}
    if g.kind == "TRAINING":
        md = date.fromisoformat(g.config["market_date"])
        out.update({"market_date": md.isoformat(), "start_date": g.config["start_date"],
                    "at_present": md >= gs.first_of_month(today_br())})
    else:
        prof = db.scalar(select(GameProfile).where(GameProfile.user_id == g.world_user_id))
        month = db.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == g.world_user_id, SimMonth.status == "OPEN"))
        from backend.models import LifeProfile
        lp = db.scalar(select(LifeProfile).where(LifeProfile.user_id == g.world_user_id))
        out.update({"age": lp.age_years if lp else None, "ended": prof.ended_reason if prof else None, "ended_month": prof.ended_month.isoformat() if prof and prof.ended_month else None,
                    "mode": prof.mode if prof else None, "scenario": prof.scenario_key if prof else None,
                    "started": bool(prof and prof.started_month), "month": month.isoformat() if month else None})
    return out


@router.get("")
def list_games(user: AccountUser, db: DbSession):
    def go():
        games = list(db.scalars(select(Game).where(Game.account_id == user.id, Game.status == "ACTIVE")
                                .order_by(Game.last_played_at.desc())))
        worlds = [g.world_user_id for g in db.scalars(select(Game).where(Game.account_id == user.id))]
        unlocked = {a.key: a.unlocked_month for a in db.scalars(select(Achievement).where(Achievement.user_id.in_(worlds)).order_by(
            Achievement.unlocked_month.desc()))} if worlds else {}
        done = db.scalar(select(func.count(LessonProgress.id)).where(LessonProgress.user_id == user.id, LessonProgress.completed_at.is_not(None))) or 0
        return {"account": {"name": user.name, "email": user.email},
                "games": [_out(db, g) for g in games],
                "achievements": [{"key": k, "name": n, "description": d, "unlocked": k in unlocked,
                                  "unlocked_month": unlocked[k].isoformat() if k in unlocked else None}
                                 for k, (n, d) in P.ACHIEVEMENTS.items()],
                "lessons": {"done": done, "total": TOTAL_LESSONS}}
    return _run(db, go)


@router.post("", status_code=201)
def create(body: CreateIn, user: AccountUser, db: DbSession):
    return _run(db, lambda: _out(db, gs.create_game(db, user, kind=body.kind, name=body.name, start_date=body.start_date)))


@router.get("/{game_id}")
def detail(game_id: int, user: AccountUser, db: DbSession):
    def go():
        g = gs.get_game(db, user.id, game_id)
        gs.touch(g)
        return _out(db, g)
    return _run(db, go)


@router.patch("/{game_id}")
def rename(game_id: int, body: RenameIn, user: AccountUser, db: DbSession):
    return _run(db, lambda: _out(db, gs.rename(db, gs.get_game(db, user.id, game_id), body.name)))


@router.post("/{game_id}/archive")
def archive(game_id: int, user: AccountUser, db: DbSession):
    return _run(db, lambda: _out(db, gs.archive(gs.get_game(db, user.id, game_id))))


@router.post("/{game_id}/training/advance")
def advance(game_id: int, body: AdvanceIn, user: AccountUser, db: DbSession):
    return _run(db, lambda: _out(db, gs.advance_months(db, gs.get_game(db, user.id, game_id), body.months)))


@router.post("/{game_id}/training/date")
def set_date(game_id: int, body: DateIn, user: AccountUser, db: DbSession):
    return _run(db, lambda: _out(db, gs.set_market_date(db, gs.get_game(db, user.id, game_id), body.date)))


@router.post("/{game_id}/training/money")
def add_money(game_id: int, body: MoneyIn, user: AccountUser, db: DbSession):
    def go():
        g = gs.get_game(db, user.id, game_id)
        gs.add_fake_money(db, g, body.amount)
        return _out(db, g)
    return _run(db, go)


class SimParamsIn(BaseModel):
    volatility: float | None = None
    event_frequency: float | None = None
    crisis_frequency: float | None = None
    crisis_severity: float | None = None
    shock_scale: float | None = None


@router.get("/{game_id}/sim-params")
def get_sim_params(game_id: int, user: AccountUser, db: DbSession):
    """Ajustes da simulação de uma partida (Configurações da conta)."""
    def go():
        from backend.services import economy_service
        g = gs.get_game(db, user.id, game_id)
        if g.kind != "LIFE":
            raise ConflictError("só partidas de vida completa têm economia simulada")
        return {"game": g.name, "params": economy_service.sim_params(db, g.world_user_id).__dict__}
    return _run(db, go)


@router.put("/{game_id}/sim-params")
def put_sim_params(game_id: int, body: SimParamsIn, user: AccountUser, db: DbSession):
    def go():
        from backend.services import economy_service
        from backend.services.engine.params import SimParams
        g = gs.get_game(db, user.id, game_id)
        if g.kind != "LIFE":
            raise ConflictError("só partidas de vida completa têm economia simulada")
        prof = economy_service.get_game(db, g.world_user_id)
        cur = {**economy_service.sim_params(db, g.world_user_id).__dict__, **{k: v for k, v in body.model_dump().items() if v is not None}}
        try:
            prof.config = {**(prof.config or {}), "sim": SimParams.from_dict(cur).__dict__}
        except ValueError as e:
            raise FinanceError(str(e))
        return {"game": g.name, "params": prof.config["sim"]}
    return _run(db, go)
