"""Empresas do usuário (etapa 3).

Cada empresa tem a sua `FinanceAccount` (tipo BUSINESS, saldo próprio). Todas as movimentações de dinheiro
continuam no mesmo `ledger_entries` (com `company_id`), nunca no orçamento pessoal. Os demonstrativos mensais
(`CompanyMonth`) são imutáveis: um mês só é processado uma vez (índice único).
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.enums import (
    AmortizationSystem, CompanyChannel, SiteMode, CompanyCostKind, CompanyEventType, CompanySegment, CompanySize, CompanyStatus, EmployeeEducation, EmployeeLevel,
    EmployeeRegime, EmployeeStatus, WorkSchedule, InstallmentStatus, LeaseKind, LoanStatus,
)
from backend.models.types import Money, StrEnumType


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_companies_user_name"),
        CheckConstraint("owner_share_pct > 0 AND owner_share_pct <= 100", name="ck_companies_share"),
        Index("ix_companies_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("finance_accounts.id", ondelete="RESTRICT"), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    segment: Mapped[CompanySegment] = mapped_column(StrEnumType(CompanySegment, "company_segment"))
    location: Mapped[str] = mapped_column(String(32))                       # chave em company_rules (por segmento; "online" se ONLINE)
    channel: Mapped[CompanyChannel] = mapped_column(StrEnumType(CompanyChannel, "company_channel"), default=CompanyChannel.PHYSICAL,
                                                    server_default="PHYSICAL")
    site_mode: Mapped[SiteMode | None] = mapped_column(StrEnumType(SiteMode, "company_site_mode"), nullable=True, default=None)
    site_value: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")   # terreno comprado (BUY)
    size: Mapped[CompanySize] = mapped_column(StrEnumType(CompanySize, "company_size"), default=CompanySize.SMALL)
    units: Mapped[int] = mapped_column(Integer, default=1, server_default="1")         # unidades/filiais
    capacity_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # expansões de capacidade
    price: Mapped[Decimal] = mapped_column(Money())                         # preço por unidade vendida
    reputation: Mapped[int] = mapped_column(Integer, default=50, server_default="50")  # 0..100
    marketing_until: Mapped[date | None] = mapped_column(Date)             # campanha ativa até este mês (inclusive)
    owner_share_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("100"))
    owner_salary: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")  # pró-labore mensal
    auto_restock: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    status: Mapped[CompanyStatus] = mapped_column(StrEnumType(CompanyStatus, "company_status"), default=CompanyStatus.ACTIVE)
    founded_on: Mapped[date] = mapped_column(Date)
    last_processed_month: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(40))
    level: Mapped[EmployeeLevel] = mapped_column(StrEnumType(EmployeeLevel, "employee_level"))
    salary: Mapped[Decimal] = mapped_column(Money())
    hours_week: Mapped[int] = mapped_column(Integer, default=44)
    productivity: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("1.00"))
    status: Mapped[EmployeeStatus] = mapped_column(StrEnumType(EmployeeStatus, "employee_status"), default=EmployeeStatus.ACTIVE)
    hired_on: Mapped[date] = mapped_column(Date)
    terminated_on: Mapped[date | None] = mapped_column(Date)
    # empresas v2 (fase 2): `salary` é o salário NEGOCIADO; o custo real depende do regime (CLT 2x, PJ 1x)
    name: Mapped[str] = mapped_column(String(80), default="", server_default="")
    regime: Mapped[EmployeeRegime] = mapped_column(StrEnumType(EmployeeRegime, "employee_regime"), default=EmployeeRegime.CLT,
                                                   server_default="CLT")
    schedule: Mapped[WorkSchedule] = mapped_column(StrEnumType(WorkSchedule, "employee_schedule"), default=WorkSchedule.ESC_5X2,
                                                   server_default="5x2")
    education: Mapped[EmployeeEducation] = mapped_column(StrEnumType(EmployeeEducation, "employee_education"),
                                                         default=EmployeeEducation.MEDIO, server_default="MEDIO")
    experience_years: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class CandidateBlock(Base):
    """Candidato indisponível para a empresa (recusou a proposta ou já foi contratado). O id do candidato é um token
    determinístico (ver `company_team`), por isso basta guardar o token: sem tabela de candidatos."""

    __tablename__ = "company_candidate_blocks"
    __table_args__ = (UniqueConstraint("company_id", "candidate_id", name="uq_candidate_block"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str] = mapped_column(String(80))
    ref_month: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(10))                       # REFUSED | HIRED


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_inventory_company_name"),
        CheckConstraint("quantity >= 0", name="ck_inventory_qty_nonneg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    unit: Mapped[str] = mapped_column(String(16), default="un")
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3), default=Decimal("0"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4))               # custo médio ponderado
    supplier: Mapped[str] = mapped_column(String(60), default="")
    min_quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3), default=Decimal("0"))
    units_per_sale: Mapped[Decimal] = mapped_column(Numeric(10, 3))           # consumo por unidade vendida
    waste_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))   # desperdício


class CompanyCost(Base):
    """Custo fixo mensal (energia/água, ferramentas, contabilidade, marketing fixo...). Editável."""

    __tablename__ = "company_costs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    kind: Mapped[CompanyCostKind] = mapped_column(StrEnumType(CompanyCostKind, "company_cost_kind"))
    name: Mapped[str] = mapped_column(String(80))
    amount: Mapped[Decimal] = mapped_column(Money())
    scales_with_units: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class CompanyLease(Base):
    """Imóvel usado pela empresa. Um mesmo imóvel nunca é usado por duas empresas ao mesmo tempo."""

    __tablename__ = "company_leases"
    __table_args__ = (
        Index("uq_company_leases_active_good", "good_id", unique=True,
              postgresql_where=text("active AND good_id IS NOT NULL")),
        Index("uq_company_leases_active_company", "company_id", unique=True, postgresql_where=text("active")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    kind: Mapped[LeaseKind] = mapped_column(StrEnumType(LeaseKind, "lease_kind"))
    good_id: Mapped[int | None] = mapped_column(ForeignKey("goods.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(120))
    monthly_rent: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    start_month: Mapped[date] = mapped_column(Date)
    end_month: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class CompanyLoan(Base):
    __tablename__ = "company_loans"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    principal: Mapped[Decimal] = mapped_column(Money())
    annual_rate_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    term_months: Mapped[int] = mapped_column(Integer)
    system: Mapped[AmortizationSystem] = mapped_column(StrEnumType(AmortizationSystem, "amortization_system"))
    start_month: Mapped[date] = mapped_column(Date)
    balance: Mapped[Decimal] = mapped_column(Money())
    status: Mapped[LoanStatus] = mapped_column(StrEnumType(LoanStatus, "loan_status"), default=LoanStatus.ACTIVE)


class CompanyLoanInstallment(Base):
    __tablename__ = "company_loan_installments"
    __table_args__ = (UniqueConstraint("loan_id", "number", name="uq_company_loan_inst_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("company_loans.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    due_month: Mapped[date] = mapped_column(Date)
    payment: Mapped[Decimal] = mapped_column(Money())
    interest: Mapped[Decimal] = mapped_column(Money())
    amortization: Mapped[Decimal] = mapped_column(Money())
    balance_after: Mapped[Decimal] = mapped_column(Money())
    status: Mapped[InstallmentStatus] = mapped_column(
        StrEnumType(InstallmentStatus, "installment_status"), default=InstallmentStatus.PENDING)


class CompanyMonth(Base):
    """Demonstrativo do mês da empresa (imutável). A unicidade (empresa, mês) impede processar duas vezes."""

    __tablename__ = "company_months"
    __table_args__ = (UniqueConstraint("company_id", "ref_month", name="uq_company_months_company_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    ref_month: Mapped[date] = mapped_column(Date)
    demand_units: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    capacity_units: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    units_sold: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    stockout: Mapped[bool] = mapped_column(Boolean, default=False)
    revenue: Mapped[Decimal] = mapped_column(Money())                  # receita bruta
    variable_costs: Mapped[Decimal] = mapped_column(Money())           # custo das mercadorias/insumos + variáveis
    fixed_costs: Mapped[Decimal] = mapped_column(Money())              # aluguel, energia, ferramentas, custos de bens
    payroll: Mapped[Decimal] = mapped_column(Money())                  # salários, encargos e pró-labore
    taxes: Mapped[Decimal] = mapped_column(Money())
    interest: Mapped[Decimal] = mapped_column(Money())
    operating_result: Mapped[Decimal] = mapped_column(Money())         # receita − custos variáveis − fixos − folha
    net_result: Mapped[Decimal] = mapped_column(Money())               # após impostos e juros
    cash_end: Mapped[Decimal] = mapped_column(Money())
    debts_end: Mapped[Decimal] = mapped_column(Money())
    equity_end: Mapped[Decimal] = mapped_column(Money())
    reputation_end: Mapped[int] = mapped_column(Integer)
    irregular: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")      # sem cargos obrigatórios no fechamento
    fines: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")   # multas do mês (já dentro de fixed_costs)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompanyEvent(Base):
    """Linha do tempo da empresa (imutável)."""

    __tablename__ = "company_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    ref_month: Mapped[date] = mapped_column(Date)
    type: Mapped[CompanyEventType] = mapped_column(StrEnumType(CompanyEventType, "company_event_type"))
    description: Mapped[str] = mapped_column(String(240))
    amount: Mapped[Decimal | None] = mapped_column(Money())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())



class PartnerInvite(Base):
    """Convite de sociedade a uma pessoa dos seus relacionamentos. A resposta é decidida UMA vez por pessoa e mês."""
    __tablename__ = "partner_invites"
    __table_args__ = (UniqueConstraint("user_id", "person_id", "ref_month", name="uq_partner_invite"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"))
    ref_month: Mapped[date] = mapped_column(Date)
    share_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    capital: Mapped[Decimal] = mapped_column(Money())                 # capital total previsto da empresa
    accepted: Mapped[bool] = mapped_column(Boolean)
    message: Mapped[str] = mapped_column(String(200), default="")
    used: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class CompanyPartner(Base):
    __tablename__ = "company_partners"
    __table_args__ = (UniqueConstraint("company_id", "person_id", name="uq_company_partner"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"))
    share_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    contribution: Mapped[Decimal] = mapped_column(Money())
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")       # ACTIVE | DEFAULTED | LEFT
    joined_month: Mapped[date] = mapped_column(Date)
    left_month: Mapped[date | None] = mapped_column(Date)
