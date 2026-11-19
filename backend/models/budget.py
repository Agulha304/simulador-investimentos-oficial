"""Orçamento mensal, recorrências, ciclo mensal e livro de movimentações financeiras.

Princípios:
  * `LedgerEntry` é imutável: correções são novas linhas (estorno) ligadas à original.
  * Valores planejados (`BudgetItem`) são "materializados" a cada mês. Por isso mudar
    uma recorrência hoje nunca reescreve meses passados.
  * O saldo da conta PESSOAL continua sendo `Portfolio.cash_balance` (fonte única);
    cada movimentação nela gera também uma `Transaction` (BUDGET_INCOME/EXPENSE).
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.enums import AccountKind, EntryOrigin, FlowKind, Frequency, MonthStatus
from backend.models.types import Money, StrEnumType


class FinanceAccount(Base):
    """Conta financeira de um usuário. A pessoal aponta para a carteira (saldo = cash_balance)."""

    __tablename__ = "finance_accounts"
    __table_args__ = (
        Index("uq_finance_accounts_user_personal", "user_id", unique=True,
              postgresql_where=text("kind = 'PERSONAL'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[AccountKind] = mapped_column(StrEnumType(AccountKind, "account_kind"))
    name: Mapped[str] = mapped_column(String(80))
    portfolio_id: Mapped[int | None] = mapped_column(ForeignKey("portfolios.id", ondelete="RESTRICT"))
    # Saldo das contas NÃO pessoais (empresas). A conta pessoal usa Portfolio.cash_balance (fonte única).
    balance: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BudgetCategory(Base):
    __tablename__ = "budget_categories"
    __table_args__ = (UniqueConstraint("user_id", "kind", "name", name="uq_budget_categories_user_kind_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[FlowKind] = mapped_column(StrEnumType(FlowKind, "flow_kind"))
    name: Mapped[str] = mapped_column(String(60))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class RecurringItem(Base):
    """Receita/despesa recorrente. O valor vive em `RecurringItemVersion` (histórico de valores)."""

    __tablename__ = "recurring_items"
    __table_args__ = (CheckConstraint("end_month IS NULL OR end_month >= start_month", name="ck_recurring_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("finance_accounts.id", ondelete="RESTRICT"))
    category_id: Mapped[int] = mapped_column(ForeignKey("budget_categories.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[FlowKind] = mapped_column(StrEnumType(FlowKind, "flow_kind"))
    frequency: Mapped[Frequency] = mapped_column(StrEnumType(Frequency, "frequency"), default=Frequency.MONTHLY)
    start_month: Mapped[date] = mapped_column(Date)               # sempre dia 1
    end_month: Mapped[date | None] = mapped_column(Date)          # último mês em que vale (dia 1)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Reajuste pela inflação (etapa 5): NONE = valor contratual fixo (padrão); MONTHLY; ANNUAL = no aniversário do item
    indexation: Mapped[str] = mapped_column(String(8), default="NONE", server_default="NONE")
    index_category: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecurringItemVersion(Base):
    """Valor da recorrência a partir de `effective_from`. Mudar o valor = nova versão."""

    __tablename__ = "recurring_item_versions"
    __table_args__ = (
        UniqueConstraint("item_id", "effective_from", name="uq_recurring_version_item_from"),
        CheckConstraint("amount > 0", name="ck_recurring_version_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("recurring_items.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money())
    effective_from: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SimMonth(Base):
    """Mês do simulador. O tempo só avança quando o usuário fecha o mês."""

    __tablename__ = "sim_months"
    __table_args__ = (
        UniqueConstraint("user_id", "ref_month", name="uq_sim_months_user_month"),
        Index("uq_sim_months_user_open", "user_id", unique=True, postgresql_where=text("status = 'OPEN'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ref_month: Mapped[date] = mapped_column(Date)                 # dia 1 do mês
    status: Mapped[MonthStatus] = mapped_column(StrEnumType(MonthStatus, "month_status"), default=MonthStatus.OPEN)
    opening_balance: Mapped[Decimal] = mapped_column(Money())
    closing_balance: Mapped[Decimal | None] = mapped_column(Money())
    planned_investment: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")
    # Resumo gravado no fechamento (os meses fechados não são recalculados).
    total_income: Mapped[Decimal | None] = mapped_column(Money())
    total_expense: Mapped[Decimal | None] = mapped_column(Money())
    invested: Mapped[Decimal | None] = mapped_column(Money())
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BudgetItem(Base):
    """Linha planejada de um mês (valor previsto). Não mexe no saldo."""

    __tablename__ = "budget_items"
    __table_args__ = (
        UniqueConstraint("month_id", "recurring_item_id", name="uq_budget_items_month_recurring"),
        CheckConstraint("planned_amount >= 0", name="ck_budget_items_planned_nonneg"),
        # Itens gerados por outros módulos (bens, financiamentos...) são identificados por `source_key`.
        Index("uq_budget_items_month_source", "month_id", "source_key", unique=True,
              postgresql_where=text("source_key IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("sim_months.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("budget_categories.id", ondelete="RESTRICT"))
    recurring_item_id: Mapped[int | None] = mapped_column(ForeignKey("recurring_items.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[FlowKind] = mapped_column(StrEnumType(FlowKind, "flow_kind"))
    planned_amount: Mapped[Decimal] = mapped_column(Money())
    source_key: Mapped[str | None] = mapped_column(String(80))      # ex.: good:12:rent, loan:3:7:interest
    # Movimentação patrimonial (compra de bem, amortização, venda): mexe no caixa, mas não é receita/despesa.
    capital: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LedgerEntry(Base):
    """Movimentação financeira imutável (efetivamente realizada).

    Nunca é editada nem apagada: um erro é corrigido por um estorno (`origin=REVERSAL`,
    `reverses_id` apontando para a original). `transaction_id` liga ao registro de caixa.
    """

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_ledger_entries_amount_positive"),
        # Uma recorrência só pode ser lançada uma vez por mês, mesmo com requisições repetidas.
        Index("uq_ledger_recurring_month", "recurring_item_id", "ref_month", unique=True,
              postgresql_where=text("origin = 'RECURRING'")),
        Index("ix_ledger_entries_user_month", "user_id", "ref_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[FlowKind] = mapped_column(StrEnumType(FlowKind, "flow_kind"))
    amount: Mapped[Decimal] = mapped_column(Money())               # sempre positivo
    category_id: Mapped[int | None] = mapped_column(ForeignKey("budget_categories.id", ondelete="RESTRICT"))
    description: Mapped[str] = mapped_column(String(200))
    entry_date: Mapped[date] = mapped_column(Date)
    ref_month: Mapped[date] = mapped_column(Date)
    source_account_id: Mapped[int | None] = mapped_column(ForeignKey("finance_accounts.id", ondelete="RESTRICT"))
    dest_account_id: Mapped[int | None] = mapped_column(ForeignKey("finance_accounts.id", ondelete="RESTRICT"))
    origin: Mapped[EntryOrigin] = mapped_column(StrEnumType(EntryOrigin, "entry_origin"), default=EntryOrigin.MANUAL)
    origin_ref: Mapped[str | None] = mapped_column(String(64))     # id da operação de origem (outro módulo)
    budget_item_id: Mapped[int | None] = mapped_column(ForeignKey("budget_items.id", ondelete="SET NULL"))
    recurring_item_id: Mapped[int | None] = mapped_column(ForeignKey("recurring_items.id", ondelete="SET NULL"))
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="RESTRICT"))
    reverses_id: Mapped[int | None] = mapped_column(ForeignKey("ledger_entries.id", ondelete="RESTRICT"), unique=True)
    capital: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Movimentação de uma EMPRESA (conta empresarial): fica fora do orçamento pessoal. `line` = natureza contábil.
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), index=True)
    line: Mapped[str | None] = mapped_column(String(24))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
