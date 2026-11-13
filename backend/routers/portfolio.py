from fastapi import APIRouter, Query, status

from backend.dependencies import CurrentUser, DbSession
from backend.schemas.market import DepositRequest
from backend.schemas.portfolio import AssetBrief, HoldingOut, PortfolioSummaryOut, TransactionOut
from backend.services import ledger_service, portfolio_service

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioSummaryOut)
def get_portfolio(user: CurrentUser, db: DbSession):
    portfolio = portfolio_service.get_portfolio_for_user(db, user.id)
    s = portfolio_service.build_summary(db, portfolio)
    return PortfolioSummaryOut(
        id=portfolio.id,
        name=portfolio.name,
        base_currency=portfolio.base_currency,
        cash_balance=s.cash_balance,
        invested_brl=s.invested_brl,
        market_value_brl=s.market_value_brl,
        total_equity_brl=s.total_equity_brl,
        total_deposits_brl=s.total_deposits_brl,
        pnl_brl=s.pnl_brl,
        pnl_pct=s.pnl_pct,
        holdings=[
            HoldingOut(
                asset=AssetBrief.model_validate(v.holding.asset),
                quantity=v.holding.quantity,
                avg_price_brl=v.holding.avg_price_brl,
                total_cost_brl=v.holding.total_cost_brl,
                current_price_brl=v.current_price_brl,
                market_value_brl=v.market_value_brl,
                pnl_brl=v.pnl_brl,
                pnl_pct=v.pnl_pct,
            )
            for v in s.holdings
        ],
    )


@router.get("/transactions", response_model=list[TransactionOut])
def get_transactions(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    portfolio = portfolio_service.get_portfolio_for_user(db, user.id)
    return portfolio_service.list_transactions(db, portfolio.id, limit=limit, offset=offset)


@router.post("/deposit", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def deposit(body: DepositRequest, user: CurrentUser, db: DbSession):
    """Adiciona saldo virtual (aporte fictício)."""
    portfolio = portfolio_service.get_portfolio_for_user(db, user.id)
    tx = ledger_service.deposit(db, portfolio.id, body.amount, note="Depósito virtual")
    db.commit()
    db.refresh(tx)
    return tx
