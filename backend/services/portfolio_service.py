"""Cálculos da carteira (patrimônio, resultado). Sem efeitos colaterais.

Na Fase 1 o valor de mercado das posições é igual ao custo (ainda não há
cotação). A Fase 2 injeta preços via services/market_data.py.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.core.money import quantize_money
from backend.models import Holding, Portfolio, Transaction, TransactionType


@dataclass
class HoldingView:
    holding: Holding
    current_price_brl: Decimal | None
    market_value_brl: Decimal
    pnl_brl: Decimal
    pnl_pct: Decimal | None


@dataclass
class PortfolioSummary:
    portfolio: Portfolio
    cash_balance: Decimal
    invested_brl: Decimal          # custo das posições abertas
    market_value_brl: Decimal      # valor de mercado das posições
    total_equity_brl: Decimal      # caixa + posições
    total_deposits_brl: Decimal    # capital aportado
    pnl_brl: Decimal               # patrimônio − aportes
    pnl_pct: Decimal | None
    holdings: list[HoldingView] = field(default_factory=list)


def get_portfolio_for_user(db: Session, user_id: int) -> Portfolio:
    return db.execute(
        select(Portfolio)
        .where(Portfolio.user_id == user_id)
        .options(selectinload(Portfolio.holdings).selectinload(Holding.asset))
    ).scalar_one()


def _pct(part: Decimal, whole: Decimal) -> Decimal | None:
    if whole == 0:
        return None
    return (part / whole * 100).quantize(Decimal("0.01"))


def build_summary(db: Session, portfolio: Portfolio) -> PortfolioSummary:
    views: list[HoldingView] = []
    for h in portfolio.holdings:
        if h.quantity <= 0:
            continue
        price = None  # Fase 2: market_data.get_price_brl(h.asset)
        value = quantize_money(h.quantity * price) if price is not None else h.total_cost_brl
        pnl = quantize_money(value - h.total_cost_brl)
        views.append(HoldingView(h, price, value, pnl, _pct(pnl, h.total_cost_brl)))

    invested = sum((v.holding.total_cost_brl for v in views), Decimal("0"))
    market = sum((v.market_value_brl for v in views), Decimal("0"))
    net_deposits = sum_net_deposits(db, portfolio.id)
    equity = quantize_money(portfolio.cash_balance + market)
    pnl = quantize_money(equity - net_deposits)
    return PortfolioSummary(
        portfolio=portfolio,
        cash_balance=portfolio.cash_balance,
        invested_brl=quantize_money(invested),
        market_value_brl=quantize_money(market),
        total_equity_brl=equity,
        total_deposits_brl=net_deposits,
        pnl_brl=pnl,
        pnl_pct=_pct(pnl, net_deposits),
        holdings=views,
    )


def sum_net_deposits(db: Session, portfolio_id: int) -> Decimal:
    """Aportes − retiradas: base para medir lucro/prejuízo total."""
    total = db.scalar(
        select(func.coalesce(func.sum(Transaction.cash_amount_brl), 0)).where(
            Transaction.portfolio_id == portfolio_id,
            Transaction.type.in_([TransactionType.DEPOSIT, TransactionType.WITHDRAWAL]),
        )
    )
    return quantize_money(total)


def list_transactions(db: Session, portfolio_id: int, *, limit: int = 50, offset: int = 0) -> list[Transaction]:
    return list(db.scalars(
        select(Transaction)
        .where(Transaction.portfolio_id == portfolio_id)
        .options(selectinload(Transaction.asset))
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .limit(limit).offset(offset)
    ))
