from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.enums import Currency
from backend.models.types import Money, StrEnumType


class Portfolio(Base):
    """Carteira virtual. `cash_balance` é sempre alterado junto com uma
    Transaction (ver services/ledger_service.py), nunca diretamente."""

    __tablename__ = "portfolios"
    __table_args__ = (CheckConstraint("cash_balance >= 0", name="ck_portfolio_cash_non_negative"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(80), default="Carteira principal")
    base_currency: Mapped[Currency] = mapped_column(StrEnumType(Currency, "currency"), default=Currency.BRL)
    cash_balance: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="portfolio")  # noqa: F821
    holdings: Mapped[list["Holding"]] = relationship(back_populates="portfolio")  # noqa: F821
