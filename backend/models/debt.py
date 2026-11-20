"""Dívidas pessoais: empréstimos (parcelas com juros) e cheque especial (saldo negativo até o limite)."""
from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
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


class InvestorProfile(Base):
    """Perfil de investidor e carteira-alvo (orçamento de investimentos) da partida."""
    __tablename__ = "investor_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    profile: Mapped[str] = mapped_column(String(14), default="MODERATE")        # CONSERVATIVE | MODERATE | AGGRESSIVE
    wanted: Mapped[list] = mapped_column(JSON, default=list)                    # classes em que o jogador quer investir
    target_alloc: Mapped[dict] = mapped_column(JSON, default=dict)              # classe -> % da carteira-alvo (soma 100)
    goal_total: Mapped[Decimal | None] = mapped_column(Money())                 # objetivo de dinheiro investido (R$)
    quiz_score: Mapped[int | None] = mapped_column(Integer)
    customized: Mapped[bool] = mapped_column(default=False)                     # o jogador editou a carteira à mão
