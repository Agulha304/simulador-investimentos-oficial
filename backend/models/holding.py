from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.types import Money, Price, Quantity


class Holding(Base):
    """Posição atual (derivada das transações) de um ativo numa carteira.
    Custos sempre em BRL, já convertidos no momento da compra."""

    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "asset_id", name="uq_holding_portfolio_asset"),
        CheckConstraint("quantity >= 0", name="ck_holding_quantity_non_negative"),
        CheckConstraint("stop_loss IS NULL OR stop_loss > 0", name="ck_holding_stop_positive"),
        CheckConstraint("take_profit IS NULL OR take_profit > 0", name="ck_holding_take_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Quantity(), default=Decimal("0"))
    avg_price_brl: Mapped[Decimal] = mapped_column(Price(), default=Decimal("0"))
    total_cost_brl: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    # Stop Loss / Take Profit: preços NA MOEDA DO ATIVO (ex.: US$ para AAPL). Nulos = desativado.
    stop_loss: Mapped[Decimal | None] = mapped_column(Price())
    take_profit: Mapped[Decimal | None] = mapped_column(Price())
    risk_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # muda a cada ajuste de níveis
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    portfolio: Mapped["Portfolio"] = relationship(back_populates="holdings")  # noqa: F821
    asset: Mapped["Asset"] = relationship()  # noqa: F821
