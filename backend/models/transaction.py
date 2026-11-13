from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.enums import Currency, TransactionSource, TransactionType
from backend.models.types import Money, Price, Quantity, StrEnumType


class Transaction(Base):
    """Livro-razão imutável da carteira. Nunca é apagado nem editado.

    `cash_amount_brl` é o efeito ASSINADO no caixa (+ entrada, − saída), então
    o saldo pode ser reconstruído por SUM(cash_amount_brl). `idempotency_key`
    (única) impede que workers/re-envios registrem o mesmo evento duas vezes.
    """

    __tablename__ = "transactions"
    __table_args__ = (Index("ix_transactions_portfolio_created", "portfolio_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="RESTRICT"), index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), index=True)
    type: Mapped[TransactionType] = mapped_column(StrEnumType(TransactionType, "transaction_type"), index=True)
    source: Mapped[TransactionSource] = mapped_column(
        StrEnumType(TransactionSource, "transaction_source"), default=TransactionSource.USER
    )

    quantity: Mapped[Decimal | None] = mapped_column(Quantity())
    unit_price: Mapped[Decimal | None] = mapped_column(Price())          # na moeda do ativo
    price_currency: Mapped[Currency | None] = mapped_column(StrEnumType(Currency, "currency"))
    fx_rate: Mapped[Decimal | None] = mapped_column(Price())             # moeda do ativo -> BRL
    unit_price_brl: Mapped[Decimal | None] = mapped_column(Price())

    gross_amount_brl: Mapped[Decimal] = mapped_column(Money())           # valor bruto (sempre positivo)
    tax_brl: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    fee_brl: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    cash_amount_brl: Mapped[Decimal] = mapped_column(Money())            # efeito assinado no caixa
    realized_pnl_brl: Mapped[Decimal | None] = mapped_column(Money())    # só em vendas: resultado realizado
    cash_balance_after: Mapped[Decimal] = mapped_column(Money())

    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped["Asset | None"] = relationship()  # noqa: F821
