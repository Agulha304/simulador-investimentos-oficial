from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.enums import Currency, DistributionKind, EligibilityStatus
from backend.models.types import Money, Price, Quantity, StrEnumType


class Dividend(Base):
    """Evento de distribuição de um ativo (fonte de dados). Histórico permanente: nunca é apagado."""

    __tablename__ = "dividends"
    __table_args__ = (
        UniqueConstraint("asset_id", "ex_date", "amount_per_unit", name="uq_dividend_asset_ex_amount"),
        CheckConstraint("amount_per_unit > 0", name="ck_dividend_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    kind: Mapped[DistributionKind] = mapped_column(StrEnumType(DistributionKind, "distribution_kind"))
    ex_date: Mapped[date] = mapped_column(Date)                        # data EX: quem tinha o ativo ANTES dela tem direito
    pay_date: Mapped[date] = mapped_column(Date)
    pay_date_estimated: Mapped[bool] = mapped_column(Boolean, default=True)
    amount_per_unit: Mapped[Decimal] = mapped_column(Price())          # na moeda do ativo
    currency: Mapped[Currency] = mapped_column(StrEnumType(Currency, "currency"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))   # elegibilidades já geradas
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped["Asset"] = relationship()  # noqa: F821


class DividendEligibility(Base):
    """Direito de uma carteira a um evento, com a quantidade reconstruída pelas transações."""

    __tablename__ = "dividend_eligibilities"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "dividend_id", name="uq_eligibility_portfolio_dividend"),
        CheckConstraint("quantity > 0", name="ck_eligibility_quantity_positive"),
        Index("ix_eligibility_status_pay_date", "status", "pay_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="RESTRICT"), index=True)
    dividend_id: Mapped[int] = mapped_column(ForeignKey("dividends.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Quantity())              # quantidade elegível na data EX
    pay_date: Mapped[date] = mapped_column(Date)                       # data prevista de pagamento
    status: Mapped[EligibilityStatus] = mapped_column(
        StrEnumType(EligibilityStatus, "eligibility_status"), default=EligibilityStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dividend: Mapped["Dividend"] = relationship()
    payment: Mapped["DividendPayment | None"] = relationship(back_populates="eligibility", uselist=False)


class DividendPayment(Base):
    """Pagamento efetivado (no máximo um por elegibilidade)."""

    __tablename__ = "dividend_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    eligibility_id: Mapped[int] = mapped_column(ForeignKey("dividend_eligibilities.id"), unique=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), unique=True)
    gross_brl: Mapped[Decimal] = mapped_column(Money())
    tax_brl: Mapped[Decimal] = mapped_column(Money())
    net_brl: Mapped[Decimal] = mapped_column(Money())
    fx_rate: Mapped[Decimal] = mapped_column(Price())
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    eligibility: Mapped["DividendEligibility"] = relationship(back_populates="payment")
