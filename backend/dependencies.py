from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core.security import decode_access_token
from backend.database import get_db
from backend.models import Game, User

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_account(
    db: DbSession,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """A CONTA real (sem trocar de partida): menu inicial, aulas, ranking e gestão das partidas."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não autenticado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized
    sub = decode_access_token(creds.credentials)
    if not sub or not sub.isdigit():
        raise unauthorized
    user = db.get(User, int(sub))
    if user is None:
        raise unauthorized
    return user


def get_current_user(
    db: DbSession,
    account: Annotated[User, Depends(get_account)],
    x_game_id: Annotated[int | None, Header()] = None,
) -> User:
    """Com `X-Game-Id`, todas as rotas de jogo passam a operar no MUNDO da partida (usuário-sombra); sem ele, na conta."""
    if x_game_id is None:
        return account
    game = db.get(Game, x_game_id)
    if game is None or game.account_id != account.id or game.status != "ACTIVE":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "partida não encontrada")
    return db.get(User, game.world_user_id)


def _resolve_clock(token: str, game_id: int):
    from backend.database import SessionLocal
    from backend.services import game_service
    sub = decode_access_token(token)
    if not sub or not sub.isdigit():
        return None
    with SessionLocal() as db:
        game = db.get(Game, game_id)
        if game is None or game.account_id != int(sub) or game.status != "ACTIVE":
            return None
        return game_service.clock_of(game, db)


async def game_clock(request: Request):
    """Define o relógio de mercado da partida (treino/simulação) para toda a requisição."""
    from backend.core import clock
    gid, auth = request.headers.get("x-game-id"), request.headers.get("authorization", "")
    token = None
    if gid and gid.isdigit() and auth.lower().startswith("bearer "):
        c = await run_in_threadpool(_resolve_clock, auth[7:], int(gid))
        if c is not None:
            token = clock.set_clock(c)
    try:
        yield
    finally:
        if token is not None:
            clock.reset_clock(token)


CurrentUser = Annotated[User, Depends(get_current_user)]
AccountUser = Annotated[User, Depends(get_account)]
