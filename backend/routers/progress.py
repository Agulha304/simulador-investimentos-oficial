"""Partida (modo livre/carreira), objetivos, conquistas, relatórios e painel geral (etapa 6)."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.dependencies import CurrentUser, DbSession
from backend.models import Goal, MonthReport
from backend.routers.budget import _run
from backend.services import budget_service as bs
from backend.services import economy_service
from backend.services import progression_rules as P
from backend.services import progression_service as ps
from backend.services.finance_ledger import NotFoundError

game_router = APIRouter(prefix="/game", tags=["game"])
router = APIRouter(prefix="/progress", tags=["progress"])


class FreeConfig(BaseModel):
    cash: Decimal = Field(default=Decimal("20000"), ge=0)
    monthly_income: Decimal = Field(default=Decimal("0"), ge=0)
    monthly_expenses: Decimal = Field(default=Decimal("0"), ge=0)
    rent: Decimal = Field(default=Decimal("0"), ge=0)
    age: int = Field(default=28, ge=18, le=80)


class StartIn(BaseModel):
    mode: str
    scenario: str | None = None
    seed: int | None = None
    name: str = "Você"
    free: FreeConfig | None = None
    economy: dict[str, float] | None = None
    sim: dict[str, float] | None = None
    gender: str | None = None
    interested_in: str | None = None
    career_field: str | None = None


class GoalIn(BaseModel):
    template: str
    target: Decimal | None = None
    sustain_months: int | None = Field(default=None, ge=1, le=60)


def _scenario_out(s: P.Scenario) -> dict:
    return {"key": s.key, "name": s.name, "description": s.description, "cash": s.cash, "salary": s.salary,
            "expenses": [{"category": e.category, "name": e.name, "amount": e.amount, "indexed": e.index} for e in s.expenses],
            "goals": [{"key": g.key, "title": g.title, "kind": g.kind} for g in s.goals], "challenges": list(s.challenges),
            "partner": s.partner is not None, "children": len(s.children_ages), "age": s.age}


@game_router.get("")
def game_info(user: CurrentUser, db: DbSession):
    def go():
        g = economy_service.get_game(db, user.id)
        return {"mode": g.mode, "scenario": g.scenario_key, "started": g.started_month is not None, "ended": g.ended_reason, "dynamic": g.economy_mode == "DYNAMIC",
                "seed": g.seed, "config": g.config, "scenarios": [_scenario_out(s) for s in P.SCENARIOS.values()],
                "goal_templates": [{"key": k, "kind": v[0], "title": v[1], "metric": v[2], "default_target": v[4]}
                                   for k, v in P.GOAL_TEMPLATES.items()]}
    return _run(db, go)


@game_router.post("/start")
def start(body: StartIn, user: CurrentUser, db: DbSession):
    return _run(db, lambda: ps.start_game(
        db, user.id, mode=body.mode, scenario_key=body.scenario, seed=body.seed, name=body.name,
        free=body.free.model_dump() if body.free else None, economy=body.economy, sim=body.sim,
        gender=body.gender, interested_in=body.interested_in, career_field=body.career_field))


@router.get("/overview")
def overview(user: CurrentUser, db: DbSession):
    return _run(db, lambda: ps.dashboard(db, user.id))


@router.get("/performance")
def career_performance(user: CurrentUser, db: DbSession):
    """Desempenho da carreira (vida financeira completa): patrimônio, poupança, dívidas, saúde e carreira ao longo dos meses."""
    return _run(db, lambda: ps.career_performance(db, user.id))


@router.get("/goals")
def goals(user: CurrentUser, db: DbSession):
    return _run(db, lambda: [ps.goal_out(g) for g in db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.id))])


@router.post("/goals", status_code=201)
def add_goal(body: GoalIn, user: CurrentUser, db: DbSession):
    def go():
        g = ps.create_goal(db, user.id, bs.ensure_setup(db, user.id), template=body.template, target=body.target,
                           sustain_months=body.sustain_months)
        return ps.goal_out(g)
    return _run(db, go)


@router.get("/achievements")
def achievements(user: CurrentUser, db: DbSession):
    def go():
        ps.refresh_open_month(db, user.id, bs.ensure_setup(db, user.id))
        return ps.achievements_out(db, user.id)
    return _run(db, go)


@router.get("/reports")
def reports(user: CurrentUser, db: DbSession):
    def go():
        rows = list(db.scalars(select(MonthReport).where(MonthReport.user_id == user.id).order_by(MonthReport.ref_month)))
        return [{"month": r.ref_month.isoformat(), "income": r.data["income"], "expense": r.data["expense"],
                 "result": r.data["result"], "net_worth": r.data["net_worth"]} for r in rows]
    return _run(db, go)


@router.get("/reports/latest")
def latest_report(user: CurrentUser, db: DbSession):
    def go():
        r = db.scalar(select(MonthReport).where(MonthReport.user_id == user.id).order_by(MonthReport.ref_month.desc()).limit(1))
        if r is None:
            raise NotFoundError("nenhum mês fechado ainda")
        return r.data
    return _run(db, go)


@router.get("/reports/annual/{year}")
def annual(year: int, user: CurrentUser, db: DbSession):
    return _run(db, lambda: ps.annual_report(db, user.id, year))


@router.get("/reports/{ym}")
def month_report(ym: str, user: CurrentUser, db: DbSession):
    def go():
        try:
            y, m = (int(x) for x in ym.split("-"))
            ref = date(y, m, 1)
        except (ValueError, TypeError):
            raise NotFoundError("mês inválido")
        r = db.scalar(select(MonthReport).where(MonthReport.user_id == user.id, MonthReport.ref_month == ref))
        if r is None:
            raise NotFoundError("relatório não encontrado")
        return r.data
    return _run(db, go)
