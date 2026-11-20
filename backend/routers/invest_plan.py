"""Orçamento da carteira de investimentos e perfil de investidor."""
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.dependencies import CurrentUser, DbSession
from backend.routers.budget import _run
from backend.services import budget_service as bs
from backend.services import invest_plan_service as ips

router = APIRouter(prefix="/invest-plan", tags=["invest-plan"])


class SettingsIn(BaseModel):
    profile: str | None = None
    wanted: list[str] | None = None
    alloc: dict[str, float] | None = None
    goal_total: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=2)


class QuizIn(BaseModel):
    answers: list[int]


@router.get("")
def get_plan(user: CurrentUser, db: DbSession):
    return _run(db, lambda: ips.plan(db, user.id, bs.ensure_setup(db, user.id)))


@router.put("")
def put_settings(body: SettingsIn, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        ips.update_settings(db, user.id, profile=body.profile, wanted=body.wanted, alloc=body.alloc, goal_total=body.goal_total)
        return ips.plan(db, user.id, month)
    return _run(db, go)


@router.get("/quiz")
def quiz(user: CurrentUser, db: DbSession):
    return {"questions": [{"text": q, "options": o} for q, o in ips.QUIZ]}


@router.post("/quiz")
def submit_quiz(body: QuizIn, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        ips.submit_quiz(db, user.id, body.answers)
        return ips.plan(db, user.id, month)
    return _run(db, go)


@router.post("/apply")
def apply(user: CurrentUser, db: DbSession):
    """Define o investimento planejado do mês como o valor recomendado."""
    return _run(db, lambda: ips.apply_recommendation(db, user.id, bs.ensure_setup(db, user.id)))
