from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from backend.dependencies import CurrentUser, DbSession
from backend.schemas.engagement import PerformanceOut, RankingOut, RankingSettings
from backend.services import performance_service, portfolio_service, ranking_service

performance_router = APIRouter(prefix="/performance", tags=["performance"])
ranking_router = APIRouter(prefix="/ranking", tags=["ranking"])


@performance_router.get("", response_model=PerformanceOut)
def get_performance(user: CurrentUser, db: DbSession,
                    range: Annotated[str, Query(pattern="^(1d|7d|30d|90d|all)$")] = "30d"):
    portfolio = portfolio_service.get_portfolio_for_user(db, user.id)
    return performance_service.build_performance(db, user.id, portfolio.id, range)


@ranking_router.get("", response_model=RankingOut)
def get_ranking(user: CurrentUser, db: DbSession,
                board: Annotated[str, Query(pattern="^(wealth|return)$")] = "wealth",
                period: Annotated[str, Query(pattern="^(all|30d|7d)$")] = "all"):
    # a foto do próprio usuário só é regravada se tiver mais de 35 min (o worker roda a cada 30): o GET quase nunca escreve
    performance_service.ensure_recent_snapshot(db, portfolio_service.get_portfolio_for_user(db, user.id), max_age=timedelta(minutes=35))
    return ranking_service.compute(db, board, period, user.id)


@ranking_router.get("/settings", response_model=RankingSettings)
def get_settings(user: CurrentUser):
    return RankingSettings(show_in_ranking=user.show_in_ranking, nickname=user.ranking_nickname,
                           default_nickname=ranking_service.default_nickname(user.name))


@ranking_router.put("/settings", response_model=RankingSettings)
def put_settings(body: RankingSettings, user: CurrentUser, db: DbSession):
    nick = body.nickname.strip() if body.nickname else None
    if nick is not None and len(nick) < 2:
        raise HTTPException(422, "O apelido precisa ter ao menos 2 caracteres")
    user.show_in_ranking, user.ranking_nickname = body.show_in_ranking, nick or None
    db.commit()
    return RankingSettings(show_in_ranking=user.show_in_ranking, nickname=user.ranking_nickname,
                           default_nickname=ranking_service.default_nickname(user.name))


# ------------------------------------------------------------------ aulas
from fastapi import status  # noqa: E402

from backend.schemas.engagement import LearnOverview, LessonOut, QuizResult, QuizSubmit  # noqa: E402
from backend.services import learn_service  # noqa: E402

learn_router = APIRouter(prefix="/learn", tags=["learn"])


@learn_router.get("", response_model=LearnOverview)
def learn_overview(user: CurrentUser, db: DbSession):
    return learn_service.overview(db, user.id)


@learn_router.get("/lessons/{lesson_id}", response_model=LessonOut)
def learn_lesson(lesson_id: str, user: CurrentUser, db: DbSession):
    try:
        return learn_service.get_lesson(db, user.id, lesson_id)
    except learn_service.LearnError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None


@learn_router.post("/lessons/{lesson_id}/quiz", response_model=QuizResult)
def learn_quiz(lesson_id: str, body: QuizSubmit, user: CurrentUser, db: DbSession):
    try:
        return learn_service.submit_quiz(db, user.id, lesson_id, body.answers)
    except learn_service.LearnError as exc:
        code = status.HTTP_404_NOT_FOUND if "não encontrada" in str(exc) else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(code, str(exc)) from None
