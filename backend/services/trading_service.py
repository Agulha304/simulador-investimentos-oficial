"""Compra e venda simuladas. Toda a operação (caixa + holding + transação) é atômica.

Regras:
  * preço = última cotação convertida para BRL (câmbio no momento da operação);
  * ativos fracionáveis (cripto) podem ser comprados por VALOR em reais;
  * demais ativos exigem quantidade inteira;
  * preço médio = custo total / quantidade, recalculado a cada compra;
  * venda reduz o custo proporcionalmente e registra o resultado realizado.
"""
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money, quantize_price, quantize_quantity, to_decimal
from backend.models import Asset, Holding, Transaction, TransactionSource, TransactionType
from backend.services import ledger_service, market_data
from backend.services.ledger_service import CashMovement

log = logging.getLogger(__name__)


class TradeError(Exception):
    """Operação inválida (mensagem apresentável ao usuário)."""


def _get_holding(db: Session, portfolio_id: int, asset_id: int) -> Holding | None:
    return db.execute(
        select(Holding).where(Holding.portfolio_id == portfolio_id, Holding.asset_id == asset_id).with_for_update()
    ).scalar_one_or_none()


def _key(portfolio_id: int, raw: str | None) -> str | None:
    return f"user-trade:{portfolio_id}:{raw}" if raw else None


def buy(db: Session, portfolio_id: int, asset: Asset, *, quantity: Decimal | None = None,
        amount_brl: Decimal | None = None, source: TransactionSource = TransactionSource.USER,
        idempotency_key: str | None = None) -> Transaction:
    if (quantity is None) == (amount_brl is None):
        raise TradeError("informe a quantidade OU o valor a investir")
    try:
        priced = market_data.get_priced_quote(asset)
    except market_data.MarketDataUnavailable as exc:
        raise TradeError("cotação indisponível no momento; tente novamente") from exc
    price_brl = priced.price_brl
    if price_brl <= 0:
        raise TradeError("cotação inválida")

    if amount_brl is not None:
        if not asset.allows_fractional:
            raise TradeError(f"{asset.symbol} não permite compra por valor; informe a quantidade")
        cost = quantize_money(to_decimal(amount_brl))
        if cost <= 0:
            raise TradeError("o valor a investir deve ser positivo")
        qty = quantize_quantity(cost / price_brl)
    else:
        qty = to_decimal(quantity)
        if qty <= 0:
            raise TradeError("a quantidade deve ser positiva")
        if not asset.allows_fractional and qty != qty.to_integral_value():
            raise TradeError(f"{asset.symbol} só pode ser negociado em quantidades inteiras")
        qty = quantize_quantity(qty)
        cost = quantize_money(qty * price_brl)
    if qty <= 0 or cost <= 0:
        raise TradeError("valor muito pequeno para comprar este ativo")

    try:
        ledger_service.lock_portfolio(db, portfolio_id)
        tx = ledger_service.record(db, portfolio_id, CashMovement(
            type=TransactionType.BUY, source=source, asset_id=asset.id,
            gross_amount_brl=cost, cash_amount_brl=-cost, quantity=qty,
            unit_price=priced.quote.price, price_currency=priced.quote.currency,
            fx_rate=priced.fx_rate, unit_price_brl=price_brl,
            idempotency_key=_key(portfolio_id, idempotency_key),
        ))
        holding = _get_holding(db, portfolio_id, asset.id)
        if holding is None:
            holding = Holding(portfolio_id=portfolio_id, asset_id=asset.id, quantity=Decimal("0"),
                              avg_price_brl=Decimal("0"), total_cost_brl=Decimal("0"))
            db.add(holding)
        holding.quantity = holding.quantity + qty
        holding.total_cost_brl = quantize_money(holding.total_cost_brl + cost)
        holding.avg_price_brl = quantize_price(holding.total_cost_brl / holding.quantity)
        db.commit()
    except Exception:
        db.rollback()
        raise
    log.info("COMPRA %s x %s a R$ %s (total R$ %s)", qty, asset.symbol, price_brl, cost)
    return tx


def sell(db: Session, portfolio_id: int, asset: Asset, *, quantity: Decimal | None = None,
         amount_brl: Decimal | None = None, source: TransactionSource = TransactionSource.USER,
         idempotency_key: str | None = None, note: str | None = None) -> Transaction:
    """Vende por quantidade ou, em ativos fracionáveis (cripto), por valor em reais."""
    if (quantity is None) == (amount_brl is None):
        raise TradeError("informe a quantidade OU o valor a vender")
    if amount_brl is not None and not asset.allows_fractional:
        raise TradeError(f"{asset.symbol} não permite venda por valor; informe a quantidade")
    try:
        priced = market_data.get_priced_quote(asset)
    except market_data.MarketDataUnavailable as exc:
        raise TradeError("cotação indisponível no momento; tente novamente") from exc

    if amount_brl is not None:
        value = quantize_money(to_decimal(amount_brl))
        if value <= 0:
            raise TradeError("o valor deve ser positivo")
        qty = quantize_quantity(value / priced.price_brl)
    else:
        qty = quantize_quantity(to_decimal(quantity))
        if qty <= 0:
            raise TradeError("a quantidade deve ser positiva")
        if not asset.allows_fractional and qty != qty.to_integral_value():
            raise TradeError(f"{asset.symbol} só pode ser negociado em quantidades inteiras")
    if qty <= 0:
        raise TradeError("valor muito pequeno para vender este ativo")

    try:
        ledger_service.lock_portfolio(db, portfolio_id)
        holding = _get_holding(db, portfolio_id, asset.id)
        if holding is None or holding.quantity < qty:
            have = holding.quantity if holding else Decimal("0")
            raise TradeError(f"quantidade insuficiente: você possui {have} de {asset.symbol}")

        proceeds = quantize_money(qty * priced.price_brl)
        cost_removed = holding.total_cost_brl if qty == holding.quantity else \
            quantize_money(holding.total_cost_brl * qty / holding.quantity)
        tx = ledger_service.record(db, portfolio_id, CashMovement(
            type=TransactionType.SELL, source=source, asset_id=asset.id,
            gross_amount_brl=proceeds, cash_amount_brl=proceeds, quantity=qty,
            unit_price=priced.quote.price, price_currency=priced.quote.currency,
            fx_rate=priced.fx_rate, unit_price_brl=priced.price_brl,
            idempotency_key=_key(portfolio_id, idempotency_key) if source == TransactionSource.USER else idempotency_key,
            note=note,
        ))
        tx.realized_pnl_brl = quantize_money(proceeds - cost_removed)
        holding.quantity = holding.quantity - qty
        holding.total_cost_brl = quantize_money(holding.total_cost_brl - cost_removed)
        if holding.quantity == 0:
            holding.total_cost_brl = Decimal("0.00")
            holding.avg_price_brl = Decimal("0")
            holding.stop_loss = holding.take_profit = None   # posição encerrada: níveis não valem mais
        db.commit()
    except Exception:
        db.rollback()
        raise
    log.info("VENDA %s x %s a R$ %s (total R$ %s, resultado R$ %s)", qty, asset.symbol,
             priced.price_brl, proceeds, tx.realized_pnl_brl)
    return tx
