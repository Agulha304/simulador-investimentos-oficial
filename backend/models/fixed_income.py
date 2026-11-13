from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.enums import (
    EventKind, EventStatus, FixedIncomeType, IndexName, Indexer, InvestmentStatus, Liquidity, PaymentFrequency,
    ProductSource, RateMode, RiskLevel, TaxRegime,
)
from backend.models.types import Money, Price, Quantity, StrEnumType

Rate = lambda: Numeric(12, 6, asdecimal=True)  # noqa: E731  (percentuais: 14.650000)


class FixedIncomeProduct(Base):
    """Oferta de renda fixa (título público, CDB, LCI, ...). As regras de liquidez, tributação
    e fluxo de caixa ficam em colunas, não em código: novos produtos são só novas linhas."""

    __tablename__ = "fixed_income_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(120), unique=True)
    template_key: Mapped[str | None] = mapped_column(String(60), index=True)       # ofertas de exemplo
    name: Mapped[str] = mapped_column(String(200))
    issuer: Mapped[str] = mapped_column(String(160))
    product_type: Mapped[FixedIncomeType] = mapped_column(StrEnumType(FixedIncomeType, "fi_type"), index=True)
    indexer: Mapped[Indexer] = mapped_column(StrEnumType(Indexer, "fi_indexer"))
    rate_mode: Mapped[RateMode] = mapped_column(StrEnumType(RateMode, "fi_rate_mode"))
    rate: Mapped[Decimal] = mapped_column(Rate())                  # % (a.a. ou % do índice, conforme rate_mode)
    maturity_date: Mapped[date] = mapped_column(Date, index=True)
    min_investment_brl: Mapped[Decimal] = mapped_column(Money())

    unit_price: Mapped[Decimal | None] = mapped_column(Price())          # PU de compra (títulos públicos)
    market_rate: Mapped[Decimal | None] = mapped_column(Rate())          # taxa de venda (marcação a mercado)
    market_unit_price: Mapped[Decimal | None] = mapped_column(Price())   # PU de venda

    liquidity: Mapped[Liquidity] = mapped_column(StrEnumType(Liquidity, "fi_liquidity"))
    grace_days: Mapped[int] = mapped_column(Integer, default=0)          # carência para resgate
    liquidity_dates: Mapped[list] = mapped_column(JSONB, default=list)   # janelas (ISO) quando SPECIFIC_DATES
    early_redemption: Mapped[bool] = mapped_column(Boolean, default=False)
    secondary_discount_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=Decimal("0"))  # deságio no secundário
    uses_mtm: Mapped[bool] = mapped_column(Boolean, default=False)       # resgate antecipado a preço de mercado
    payment_frequency: Mapped[PaymentFrequency] = mapped_column(StrEnumType(PaymentFrequency, "fi_frequency"))
    tax_regime: Mapped[TaxRegime] = mapped_column(StrEnumType(TaxRegime, "fi_tax_regime"))
    risk_level: Mapped[RiskLevel] = mapped_column(StrEnumType(RiskLevel, "fi_risk"))
    fgc_covered: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[ProductSource] = mapped_column(StrEnumType(ProductSource, "fi_source"))
    as_of: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FixedIncomeInvestment(Base):
    """Aplicação de uma carteira. As condições contratadas são COPIADAS do produto na compra
    (a taxa ofertada muda todo dia, a sua não)."""

    __tablename__ = "fixed_income_investments"
    __table_args__ = (
        CheckConstraint("principal_brl > 0", name="ck_fi_principal_positive"),
        Index("ix_fi_investment_portfolio_status", "portfolio_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="RESTRICT"))
    product_id: Mapped[int] = mapped_column(ForeignKey("fixed_income_products.id"))
    status: Mapped[InvestmentStatus] = mapped_column(
        StrEnumType(InvestmentStatus, "fi_inv_status"), default=InvestmentStatus.ACTIVE)
    applied_on: Mapped[date] = mapped_column(Date)
    principal_brl: Mapped[Decimal] = mapped_column(Money())             # custo (base do imposto)
    units: Mapped[Decimal | None] = mapped_column(Quantity())           # títulos públicos: principal / PU

    # contrato (cópia)
    indexer: Mapped[Indexer] = mapped_column(StrEnumType(Indexer, "fi_indexer"))
    rate_mode: Mapped[RateMode] = mapped_column(StrEnumType(RateMode, "fi_rate_mode"))
    rate: Mapped[Decimal] = mapped_column(Rate())
    maturity_date: Mapped[date] = mapped_column(Date)
    payment_frequency: Mapped[PaymentFrequency] = mapped_column(StrEnumType(PaymentFrequency, "fi_frequency"))
    tax_regime: Mapped[TaxRegime] = mapped_column(StrEnumType(TaxRegime, "fi_tax_regime"))
    uses_mtm: Mapped[bool] = mapped_column(Boolean, default=False)

    # estado de acumulação
    base_brl: Mapped[Decimal] = mapped_column(Price())                  # valor-base (corrigido por inflação após cupons)
    last_settlement_date: Mapped[date] = mapped_column(Date)            # início do período de acumulação atual
    interest_paid_net_brl: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))

    closed_on: Mapped[date | None] = mapped_column(Date)
    closed_gross_brl: Mapped[Decimal | None] = mapped_column(Money())
    closed_tax_brl: Mapped[Decimal | None] = mapped_column(Money())
    closed_net_brl: Mapped[Decimal | None] = mapped_column(Money())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped["FixedIncomeProduct"] = relationship()
    events: Mapped[list["FinancialEvent"]] = relationship(back_populates="investment", order_by="FinancialEvent.scheduled_date")


class FinancialEvent(Base):
    """Fluxo de caixa programado de uma aplicação (cupons e vencimento). Genérico, separado
    de dividendos: o valor é calculado no pagamento, com os índices conhecidos na data do evento."""

    __tablename__ = "financial_events"
    __table_args__ = (
        UniqueConstraint("investment_id", "kind", "scheduled_date", name="uq_financial_event"),
        Index("ix_financial_event_status_date", "status", "scheduled_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    investment_id: Mapped[int] = mapped_column(ForeignKey("fixed_income_investments.id"), index=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[EventKind] = mapped_column(StrEnumType(EventKind, "fi_event_kind"))
    scheduled_date: Mapped[date] = mapped_column(Date)
    status: Mapped[EventStatus] = mapped_column(StrEnumType(EventStatus, "fi_event_status"), default=EventStatus.PENDING)
    gross_brl: Mapped[Decimal | None] = mapped_column(Money())
    tax_brl: Mapped[Decimal | None] = mapped_column(Money())
    net_brl: Mapped[Decimal | None] = mapped_column(Money())
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), unique=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    investment: Mapped["FixedIncomeInvestment"] = relationship(back_populates="events")


class IndexRate(Base):
    """Histórico de índices (fonte: Banco Central, séries SGS). CDI/Selic: % ao dia útil.
    IPCA/IGP-M: % ao mês, com ref_date = 1º dia do mês."""

    __tablename__ = "index_rates"
    __table_args__ = (UniqueConstraint("index_name", "ref_date", name="uq_index_rate"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    index_name: Mapped[IndexName] = mapped_column(StrEnumType(IndexName, "index_name"))
    ref_date: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 10, asdecimal=True))
