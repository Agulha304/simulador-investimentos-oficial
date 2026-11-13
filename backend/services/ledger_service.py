"""Livro-razão: ÚNICO ponto do sistema que altera o saldo em caixa.

Toda alteração de saldo:
  1. trava a linha da carteira (SELECT ... FOR UPDATE) — evita corrida entre
     requests e workers;
  2. valida que o saldo não fica negativo;
  3. grava uma Transaction com o saldo resultante.
O commit fica a cargo de quem chama, para que a operação inteira (ex.: compra
= caixa + holding + transação) seja atômica.
"""
import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import Currency, Portfolio, Transaction, TransactionSource, TransactionType

log = logging.getLogger(__name__)


class InsufficientFundsError(Exception):
    pass


class DuplicateTransactionError(Exception):
    """Já existe transação com essa idempotency_key — o evento já foi processado."""


@dataclass(frozen=True)
class CashMovement:
    type: TransactionType
    gross_amount_brl: Decimal          # sempre positivo
    cash_amount_brl: Decimal           # efeito assinado no caixa
    source: TransactionSource = TransactionSource.USER
    asset_id: int | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    price_currency: Currency | None = None
    fx_rate: Decimal | None = None
    unit_price_brl: Decimal | None = None
    tax_brl: Decimal = Decimal("0")
    fee_brl: Decimal = Decimal("0")
    idempotency_key: str | None = None
    note: str | None = None


def lock_portfolio(db: Session, portfolio_id: int) -> Portfolio:
    return db.execute(select(Portfolio).where(Portfolio.id == portfolio_id).with_for_update()).scalar_one()


def record(db: Session, portfolio_id: int, mv: CashMovement) -> Transaction:
    if mv.idempotency_key and db.scalar(
        select(Transaction.id).where(Transaction.idempotency_key == mv.idempotency_key)
    ):
        raise DuplicateTransactionError(mv.idempotency_key)

    portfolio = lock_portfolio(db, portfolio_id)
    cash_delta = quantize_money(mv.cash_amount_brl)
    new_balance = quantize_money(portfolio.cash_balance + cash_delta)
    if new_balance < 0:
        raise InsufficientFundsError(
            f"saldo insuficiente: disponível {portfolio.cash_balance}, necessário {-cash_delta}"
        )

    portfolio.cash_balance = new_balance
    tx = Transaction(
        portfolio_id=portfolio.id,
        asset_id=mv.asset_id,
        type=mv.type,
        source=mv.source,
        quantity=mv.quantity,
        unit_price=mv.unit_price,
        price_currency=mv.price_currency,
        fx_rate=mv.fx_rate,
        unit_price_brl=mv.unit_price_brl,
        gross_amount_brl=quantize_money(mv.gross_amount_brl),
        tax_brl=quantize_money(mv.tax_brl),
        fee_brl=quantize_money(mv.fee_brl),
        cash_amount_brl=cash_delta,
        cash_balance_after=new_balance,
        idempotency_key=mv.idempotency_key,
        note=mv.note,
    )
    db.add(tx)
    db.flush()
    log.info("tx %s portfolio=%s type=%s cash=%s saldo=%s", tx.id, portfolio.id, mv.type, cash_delta, new_balance)
    return tx


def deposit(db: Session, portfolio_id: int, amount: Decimal, *, source=TransactionSource.USER,
            idempotency_key: str | None = None, note: str | None = None) -> Transaction:
    amount = quantize_money(amount)
    if amount <= 0:
        raise ValueError("o valor do depósito deve ser positivo")
    return record(db, portfolio_id, CashMovement(
        type=TransactionType.DEPOSIT, gross_amount_brl=amount, cash_amount_brl=amount,
        source=source, idempotency_key=idempotency_key, note=note,
    ))
