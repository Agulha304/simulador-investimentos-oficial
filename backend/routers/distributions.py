from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from backend.core.money import quantize_price
from backend.dependencies import CurrentUser, DbSession
from backend.models import Dividend, DividendEligibility, Transaction, TransactionType
from backend.schemas.portfolio import AssetBrief, DividendItemOut, DividendSyncOut
from backend.services import distribution_service, portfolio_service

router = APIRouter(prefix="/portfolio/dividends", tags=["dividends"])


@router.get("", response_model=list[DividendItemOut])
def list_dividends(user: CurrentUser, db: DbSession, limit: int = Query(200, ge=1, le=500)):
    """Proventos reconhecidos (pendentes e pagos) da carteira, do mais recente para o mais antigo."""
    portfolio = portfolio_service.get_portfolio_for_user(db, user.id)
    rows = db.scalars(
        select(DividendEligibility).where(DividendEligibility.portfolio_id == portfolio.id)
        .join(Dividend, Dividend.id == DividendEligibility.dividend_id)
        .options(joinedload(DividendEligibility.dividend).joinedload(Dividend.asset),
                 joinedload(DividendEligibility.payment))
        .order_by(Dividend.ex_date.desc(), DividendEligibility.id.desc()).limit(limit)
    ).all()
    return [
        DividendItemOut(
            id=e.id, asset=AssetBrief.model_validate(e.dividend.asset), kind=e.dividend.kind,
            ex_date=e.dividend.ex_date, pay_date=e.pay_date, pay_date_estimated=e.dividend.pay_date_estimated,
            status=e.status, quantity=e.quantity, amount_per_unit=e.dividend.amount_per_unit,
            currency=e.dividend.currency, expected_gross_native=quantize_price(e.quantity * e.dividend.amount_per_unit),
            gross_brl=e.payment.gross_brl if e.payment else None, tax_brl=e.payment.tax_brl if e.payment else None,
            net_brl=e.payment.net_brl if e.payment else None, paid_at=e.payment.paid_at if e.payment else None,
        ) for e in rows
    ]


@router.post("/sync", response_model=DividendSyncOut)
def sync_dividends(user: CurrentUser, db: DbSession):
    """Consulta eventos dos ativos da carteira e paga o que já venceu (o worker faz o mesmo periodicamente)."""
    portfolio = portfolio_service.get_portfolio_for_user(db, user.id)
    asset_ids = list(db.scalars(select(Transaction.asset_id).where(
        Transaction.portfolio_id == portfolio.id, Transaction.type == TransactionType.BUY).distinct()))
    new = distribution_service.discover(db, asset_ids=asset_ids) if asset_ids else 0
    paid = distribution_service.pay_due(db, portfolio_id=portfolio.id)
    return DividendSyncOut(new_rights=new, paid=paid)
