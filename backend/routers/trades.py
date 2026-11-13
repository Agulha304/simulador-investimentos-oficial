from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from backend.dependencies import CurrentUser, DbSession
from backend.models import Asset
from backend.schemas.market import BuyRequest, SellRequest
from backend.schemas.portfolio import TransactionOut
from backend.services import ledger_service, portfolio_service, trading_service

router = APIRouter(prefix="/trades", tags=["trades"])
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", max_length=64)]


def _run(db, user, asset_id, fn):
    asset = db.get(Asset, asset_id)
    if not asset or not asset.is_active:
        raise HTTPException(404, "Ativo não encontrado")
    portfolio = portfolio_service.get_portfolio_for_user(db, user.id)
    try:
        tx = fn(portfolio.id, asset)
    except trading_service.TradeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    except ledger_service.InsufficientFundsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    except ledger_service.DuplicateTransactionError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Operação já processada (Idempotency-Key repetida)") from None
    db.refresh(tx)
    return tx


@router.post("/buy", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def buy(body: BuyRequest, user: CurrentUser, db: DbSession, idempotency_key: IdemKey = None):
    return _run(db, user, body.asset_id, lambda pid, a: trading_service.buy(
        db, pid, a, quantity=body.quantity, amount_brl=body.amount_brl, idempotency_key=idempotency_key))


@router.post("/sell", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def sell(body: SellRequest, user: CurrentUser, db: DbSession, idempotency_key: IdemKey = None):
    return _run(db, user, body.asset_id, lambda pid, a: trading_service.sell(
        db, pid, a, quantity=body.quantity, idempotency_key=idempotency_key))
