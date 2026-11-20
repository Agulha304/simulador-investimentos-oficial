"""Empréstimos e saldo negativo (cheque especial)."""
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.dependencies import CurrentUser, DbSession
from backend.routers.budget import _run
from backend.services import budget_service as bs
from backend.services import debt_service as ds

router = APIRouter(prefix="/debt", tags=["debt"])


class LoanIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=2)
    term_months: int = Field(ge=3, le=60)


@router.get("")
def overview(user: CurrentUser, db: DbSession):
    return _run(db, lambda: ds.overview(db, user.id, bs.ensure_setup(db, user.id)))


@router.post("/loans", status_code=201)
def take(body: LoanIn, user: CurrentUser, db: DbSession):
    def go():
        m = bs.ensure_setup(db, user.id)
        ds.take_loan(db, user.id, m, body.amount, body.term_months)
        return ds.overview(db, user.id, m)
    return _run(db, go)


@router.post("/loans/{loan_id}/prepay")
def prepay(loan_id: int, user: CurrentUser, db: DbSession):
    def go():
        m = bs.ensure_setup(db, user.id)
        ds.prepay(db, user.id, m, loan_id)
        return ds.overview(db, user.id, m)
    return _run(db, go)
