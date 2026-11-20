"""Bens, imóveis, financiamentos e patrimônio (etapa 2).

Regras de projeto:
  * Todo efeito financeiro passa pelo ledger (`LedgerEntry`); aqui só há o ESTADO dos bens.
  * O histórico é imutável: valores (`GoodValue`) e eventos (`GoodEvent`) só ganham linhas.
  * `owner_account_id` aponta para uma `FinanceAccount` (hoje a pessoal; empresas usarão a sua).
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.enums import (
    AmortizationSystem, Condition, CostKind, Frequency, GoodCategory, GoodEventType, GoodStatus, InstallmentStatus,
    LoanStatus, Occupancy, ValueSource,
)
from backend.models.types import Money, StrEnumType


class Good(Base):
    __tablename__ = "goods"
    __table_args__ = (
        UniqueConstraint("user_id", "purchase_key", name="uq_goods_user_purchase_key"),
        CheckConstraint("current_value >= 0", name="ck_goods_value_nonneg"),
        Index("ix_goods_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    owner_account_id: Mapped[int] = mapped_column(ForeignKey("finance_accounts.id", ondelete="RESTRICT"))
    category: Mapped[GoodCategory] = mapped_column(StrEnumType(GoodCategory, "good_category"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    listing_key: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[GoodStatus] = mapped_column(StrEnumType(GoodStatus, "good_status"), default=GoodStatus.ACTIVE)
    condition: Mapped[Condition | None] = mapped_column(StrEnumType(Condition, "good_condition"))
    location: Mapped[str | None] = mapped_column(String(120))
    acquired_on: Mapped[date] = mapped_column(Date)                       # mês do simulador (dia 1)
    purchase_price: Mapped[Decimal] = mapped_column(Money())
    acquisition_cost: Mapped[Decimal] = mapped_column(Money())            # preço + taxas e impostos
    current_value: Mapped[Decimal] = mapped_column(Money())
    purchase_key: Mapped[str] = mapped_column(String(128))                # idempotência da compra
    sold_on: Mapped[date | None] = mapped_column(Date)
    sale_price: Mapped[Decimal | None] = mapped_column(Money())
    sale_fees: Mapped[Decimal | None] = mapped_column(Money())
    sale_result: Mapped[Decimal | None] = mapped_column(Money())          # líquido da venda − custo de aquisição
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RealEstateDetails(Base):
    __tablename__ = "real_estate_details"

    good_id: Mapped[int] = mapped_column(ForeignKey("goods.id", ondelete="CASCADE"), primary_key=True)
    property_type: Mapped[str] = mapped_column(String(24))               # house | apartment | commercial | land
    address: Mapped[str] = mapped_column(String(160))
    area_m2: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    occupancy: Mapped[Occupancy] = mapped_column(StrEnumType(Occupancy, "occupancy"), default=Occupancy.VACANT)
    monthly_rent: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")
    rent_tax_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("7.50"), server_default="7.50")   # legado: o IR agora é progressivo (br_taxes)
    nightly_rate: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")             # diária da hospedagem de temporada
    management: Mapped[str] = mapped_column(String(8), default="SELF", server_default="SELF")                     # SELF (você) | HIRED (gestor)
    str_rating: Mapped[int] = mapped_column(Integer, default=70, server_default="70")                              # nota dos hóspedes (50..98)


class VehicleDetails(Base):
    __tablename__ = "vehicle_details"

    good_id: Mapped[int] = mapped_column(ForeignKey("goods.id", ondelete="CASCADE"), primary_key=True)
    usage_km_month: Mapped[int] = mapped_column(Integer, default=800)
    km_per_liter: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("11"))


class GoodCost(Base):
    """Custo recorrente do bem (IPTU, condomínio, seguro, IPVA...). Vira item do orçamento nos meses devidos."""

    __tablename__ = "good_costs"

    id: Mapped[int] = mapped_column(primary_key=True)
    good_id: Mapped[int] = mapped_column(ForeignKey("goods.id", ondelete="CASCADE"), index=True)
    kind: Mapped[CostKind] = mapped_column(StrEnumType(CostKind, "cost_kind"))
    name: Mapped[str] = mapped_column(String(80))
    amount: Mapped[Decimal] = mapped_column(Money())
    frequency: Mapped[Frequency] = mapped_column(StrEnumType(Frequency, "frequency"), default=Frequency.MONTHLY)
    start_month: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class GoodValue(Base):
    """Histórico de valor (nunca reescrito: cada mês ganha sua própria linha)."""

    __tablename__ = "good_values"
    __table_args__ = (UniqueConstraint("good_id", "ref_month", "source", name="uq_good_values_month_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    good_id: Mapped[int] = mapped_column(ForeignKey("goods.id", ondelete="CASCADE"), index=True)
    ref_month: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Money())
    source: Mapped[ValueSource] = mapped_column(StrEnumType(ValueSource, "value_source"))


class GoodEvent(Base):
    """Linha do tempo do bem: compra, venda, mudança de ocupação, manutenção, inquilino..."""

    __tablename__ = "good_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    good_id: Mapped[int] = mapped_column(ForeignKey("goods.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    ref_month: Mapped[date] = mapped_column(Date)
    type: Mapped[GoodEventType] = mapped_column(StrEnumType(GoodEventType, "good_event_type"))
    description: Mapped[str] = mapped_column(String(240))
    amount: Mapped[Decimal | None] = mapped_column(Money())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Loan(Base):
    __tablename__ = "loans"
    __table_args__ = (CheckConstraint("term_months > 0", name="ck_loans_term_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    good_id: Mapped[int] = mapped_column(ForeignKey("goods.id", ondelete="RESTRICT"), unique=True)
    principal: Mapped[Decimal] = mapped_column(Money())                  # valor financiado
    down_payment: Mapped[Decimal] = mapped_column(Money())
    annual_rate_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4))      # taxa efetiva anual
    monthly_rate: Mapped[Decimal] = mapped_column(Numeric(14, 12))
    term_months: Mapped[int] = mapped_column(Integer)
    system: Mapped[AmortizationSystem] = mapped_column(StrEnumType(AmortizationSystem, "amortization_system"))
    start_month: Mapped[date] = mapped_column(Date)                      # mês da contratação
    end_month: Mapped[date] = mapped_column(Date)                        # mês da última parcela
    balance: Mapped[Decimal] = mapped_column(Money())                    # saldo devedor
    status: Mapped[LoanStatus] = mapped_column(StrEnumType(LoanStatus, "loan_status"), default=LoanStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LoanInstallment(Base):
    __tablename__ = "loan_installments"
    __table_args__ = (UniqueConstraint("loan_id", "number", name="uq_loan_installments_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    due_month: Mapped[date] = mapped_column(Date)
    payment: Mapped[Decimal] = mapped_column(Money())
    interest: Mapped[Decimal] = mapped_column(Money())
    amortization: Mapped[Decimal] = mapped_column(Money())
    balance_after: Mapped[Decimal] = mapped_column(Money())
    status: Mapped[InstallmentStatus] = mapped_column(
        StrEnumType(InstallmentStatus, "installment_status"), default=InstallmentStatus.PENDING)


class ValuationRule(Base):
    """Regra de valorização por categoria. Sem linha aqui, valem os padrões de `goods_rules.py`."""

    __tablename__ = "valuation_rules"

    category: Mapped[GoodCategory] = mapped_column(StrEnumType(GoodCategory, "good_category"), primary_key=True)
    monthly_drift_pct: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    volatility_pct: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    uncertainty_pct: Mapped[Decimal] = mapped_column(Numeric(7, 4))


class ShortStayMonth(Base):
    """Resultado imutável de um mês de hospedagem de temporada (calculado uma vez por imóvel e mês)."""
    __tablename__ = "short_stay_months"
    __table_args__ = (UniqueConstraint("good_id", "ref_month", name="uq_short_stay_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    good_id: Mapped[int] = mapped_column(ForeignKey("goods.id", ondelete="CASCADE"), index=True)
    ref_month: Mapped[date] = mapped_column(Date)
    nights: Mapped[int] = mapped_column(Integer)
    occupancy_pct: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    nightly: Mapped[Decimal] = mapped_column(Money())
    gross: Mapped[Decimal] = mapped_column(Money())
    platform_fee: Mapped[Decimal] = mapped_column(Money())
    manager_fee: Mapped[Decimal] = mapped_column(Money())
    cleaning: Mapped[Decimal] = mapped_column(Money())
    iss: Mapped[Decimal] = mapped_column(Money())
    rating: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(160), default="")
