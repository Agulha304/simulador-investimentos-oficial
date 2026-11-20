"""Configurações da conta (fora de qualquer partida)."""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.dependencies import AccountUser, DbSession
from backend.routers.budget import _run
from backend.services import account_settings as acc

router = APIRouter(prefix="/account", tags=["account"])


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: str


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, max_length=60)
    active: bool | None = None


@router.get("/categories")
def categories(user: AccountUser, db: DbSession):
    return _run(db, lambda: [acc.out(c) for c in acc.ensure_defaults(db, user.id)])


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, user: AccountUser, db: DbSession):
    return _run(db, lambda: acc.out(acc.create(db, user.id, body.name, body.kind)))


@router.patch("/categories/{category_id}")
def update_category(category_id: int, body: CategoryPatch, user: AccountUser, db: DbSession):
    return _run(db, lambda: acc.out(acc.update(db, user.id, category_id, name=body.name, active=body.active)))
