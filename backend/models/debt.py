"""Dívidas pessoais: empréstimos (parcelas com juros) e cheque especial (saldo negativo até o limite)."""
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.types import Money


class PersonalLoan(Base):
    __tablename__ = "personal_loans"
    __table_args__ = (Index("ix_personal_loans_user", "user_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))                      # LOAN | OVERDRAFT
    principal: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    balance: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    annual_rate_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    term_months: Mapped[int] = mapped_column(Integer, default=0)
    start_month: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")  # ACTIVE | PAID


class PersonalLoanInstallment(Base):
    __tablename__ = "personal_loan_installments"
    __table_args__ = (UniqueConstraint("loan_id", "number", name="uq_personal_installment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("personal_loans.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    due_month: Mapped[date] = mapped_column(Date)
    payment: Mapped[Decimal] = mapped_column(Money())
    interest: Mapped[Decimal] = mapped_column(Money())
    amortization: Mapped[Decimal] = mapped_column(Money())
    balance_after: Mapped[Decimal] = mapped_column(Money())
    status: Mapped[str] = mapped_column(String(10), default="PENDING")  # PENDING | PAID | CANCELLED
