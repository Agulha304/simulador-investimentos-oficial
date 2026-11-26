"""Empresas do usuário (etapa 3).

Cada empresa tem a sua `FinanceAccount` (tipo BUSINESS, saldo próprio). Todas as movimentações de dinheiro
continuam no mesmo `ledger_entries` (com `company_id`), nunca no orçamento pessoal. Os demonstrativos mensais
(`CompanyMonth`) são imutáveis: um mês só é processado uma vez (índice único).
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, UniqueConstraint, func, text,
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
    relevance: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"), server_default="0")   # 0..100: sobe devagar (fase 3a)
    relocated_on: Mapped[date | None] = mapped_column(Date)               # mês da última mudança de endereço (vendas reduzidas nele)
    marketing_until: Mapped[date | None] = mapped_column(Date)             # campanha ativa até este mês (inclusive)
    # empresas v2 (fase 5): campanha com efeito incerto, capacidade fracionária, qualidade, armazenagem, despejo/imprevistos
    marketing_boost: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("0.12"), server_default="0.12")   # alta de demanda da campanha
    capacity_boost: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("0"), server_default="0")   # níveis EFETIVOS de capacidade (1 = +25%)
    storage_boost: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("0"), server_default="0")    # +x no teto de estoque
    quality: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("50"), server_default="50")        # 0..100 (começa em 50)
    suspended_until: Mapped[date | None] = mapped_column(Date)             # despejo: sem operar até este mês (inclusive) ou até relocar
    incident_shield_until: Mapped[date | None] = mapped_column(Date)       # conserto premium: sem quebra de equipamento até este mês
    compliance_grace_months: Mapped[int] = mapped_column(Integer, default=0, server_default="0")   # adaptação de empresas legadas: meses sem multa/bloqueio por cargos obrigatórios
    owner_share_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("100"))
    owner_salary: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")  # pró-labore mensal
    auto_restock: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    status: Mapped[CompanyStatus] = mapped_column(StrEnumType(CompanyStatus, "company_status"), default=CompanyStatus.ACTIVE)
    founded_on: Mapped[date] = mapped_column(Date)
    last_processed_month: Mapped[date | None] = mapped_column(Date)
    opens_month: Mapped[date | None] = mapped_column(Date)                 # em abertura/obra: sem vendas até este mês (inclusive já opera)
    country: Mapped[str] = mapped_column(String(2), default="BR", server_default="BR")   # país da empresa (preços, custos, tributos e câmbio)
    acquired_from: Mapped[str | None] = mapped_column(String(80))           # nome da empresa comprada que deu origem a esta
    franchise_appeal: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"), server_default="0")   # 0..100: atratividade da franquia (publicidade)
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
    work_mode: Mapped[str] = mapped_column(String(6), default="ONSITE", server_default="ONSITE")   # ONSITE | REMOTE
    country: Mapped[str] = mapped_column(String(2), default="BR", server_default="BR")             # país onde mora/recebe (salário na moeda dele)
    lawsuit_history: Mapped[int] = mapped_column(Integer, default=0, server_default="0")    # nº de processos trabalhistas anteriores (0..3)


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
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)   # categoria de fornecimento (fase 4): 1 item por categoria


class CompanySupplier(Base):
    """Contrato com fornecedor (fase 4): um contrato ATIVO por (empresa, categoria). Preço, pedido mínimo e volume máximo valem
    para as compras de estoque e para o custo variável dos serviços; o fornecedor falha na entrega com prob. (1 - reliability)."""

    __tablename__ = "company_suppliers"
    __table_args__ = (
        Index("uq_company_suppliers_active", "company_id", "category", unique=True, postgresql_where=text("status = 'ACTIVE'")),
        UniqueConstraint("company_id", "idempotency_key", name="uq_company_suppliers_idem"),
        CheckConstraint("status IN ('ACTIVE', 'ENDED')", name="ck_company_suppliers_status"),
        CheckConstraint("unit_price > 0", name="ck_company_suppliers_price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(80))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))               # preço contratado por unidade de compra
    reference_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))          # referência do segmento na assinatura
    min_monthly_order: Mapped[Decimal] = mapped_column(Numeric(16, 3))        # pedido mínimo (unidades por compra)
    max_units_month: Mapped[Decimal] = mapped_column(Numeric(16, 3))          # volume contratado por mês (o que ele aguenta)
    reliability: Mapped[Decimal] = mapped_column(Numeric(4, 3))               # 0..1
    lead_days: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE", server_default="ACTIVE")   # ACTIVE | ENDED
    started_month: Mapped[date] = mapped_column(Date)
    ended_month: Mapped[date | None] = mapped_column(Date)
    term_months: Mapped[int] = mapped_column(Integer, default=6, server_default="6")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")     # "Fornecedor padrão" das empresas antigas
    volume_month: Mapped[date | None] = mapped_column(Date)                   # mês a que `volume_used` se refere
    volume_used: Mapped[Decimal] = mapped_column(Numeric(16, 3), default=Decimal("0"), server_default="0")
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # limites do contrato (contratador/headhunter): os dois primeiros valem nas COMPRAS; os outros dois são critérios ao renovar/trocar
    max_monthly_spend: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)   # gasto máximo por mês com este contrato
    volume_cap: Mapped[Decimal | None] = mapped_column(Numeric(16, 3), nullable=True)           # volume máximo por mês (<= max_units_month)
    min_reliability: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    max_lead_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spend_used: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"), server_default="0")   # gasto do mês `volume_month`


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
    taxes: Mapped[Decimal] = mapped_column(Money())                    # total de tributos do mês (soma do tax_breakdown)
    tax_regime: Mapped[str | None] = mapped_column(String(20), nullable=True)      # MEI | SIMPLES | LUCRO_PRESUMIDO (null: mês antigo)
    tax_breakdown: Mapped[list | None] = mapped_column(JSON, nullable=True)       # [{name, base, rate_pct, amount}]
    interest: Mapped[Decimal] = mapped_column(Money())
    operating_result: Mapped[Decimal] = mapped_column(Money())         # receita − custos variáveis − fixos − folha
    net_result: Mapped[Decimal] = mapped_column(Money())               # após impostos e juros
    cash_end: Mapped[Decimal] = mapped_column(Money())
    debts_end: Mapped[Decimal] = mapped_column(Money())
    equity_end: Mapped[Decimal] = mapped_column(Money())
    reputation_end: Mapped[int] = mapped_column(Integer)
    relevance_end: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"), server_default="0")
    zero_sales: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")     # mês sorteado sem nenhuma venda
    irregular: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")      # sem cargos obrigatórios no fechamento
    fines: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")   # multas do mês (já dentro de fixed_costs)
    units_detail: Mapped[list | None] = mapped_column(JSON, nullable=True)   # fase 5: resultado do mês por unidade (matriz + filiais)
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


class CompanyUnit(Base):
    """Unidade da empresa (fase 5). A MATRIZ é a própria `Company` (não tem linha aqui); cada FILIAL é uma linha. `Company.units` =
    1 + filiais abertas. A filial vende com a sua própria relevância (fração da relevância da marca ao abrir) e uma `viability`
    sorteada (0,3 a 1,4) que decide se ela vende menos ou mais do que a matriz; pode FALIR (status CLOSED)."""

    __tablename__ = "company_units"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_company_units_status"),
        CheckConstraint("kind IN ('HQ', 'BRANCH')", name="ck_company_units_kind"),
        Index("ix_company_units_company_status", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(8), default="BRANCH", server_default="BRANCH")          # HQ | BRANCH
    name: Mapped[str] = mapped_column(String(80), default="", server_default="")
    location: Mapped[str] = mapped_column(String(32))
    channel: Mapped[CompanyChannel] = mapped_column(StrEnumType(CompanyChannel, "company_channel"), default=CompanyChannel.PHYSICAL,
                                                    server_default="PHYSICAL")
    site_mode: Mapped[SiteMode | None] = mapped_column(StrEnumType(SiteMode, "company_site_mode"), nullable=True, default=None)
    site_value: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")
    monthly_rent: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")
    relevance: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"), server_default="0")
    viability: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("1"), server_default="1")
    status: Mapped[str] = mapped_column(String(8), default="OPEN", server_default="OPEN")            # OPEN | CLOSED
    opened_month: Mapped[date] = mapped_column(Date)
    closed_month: Mapped[date | None] = mapped_column(Date)
    closed_reason: Mapped[str | None] = mapped_column(String(160))
    cumulative_result: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")
    investment: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")    # custo de abertura (sem o terreno)
    opens_month: Mapped[date | None] = mapped_column(Date)                 # em obra/instalação: só opera a partir deste mês


class CompanyExpansion(Base):
    """Aporte de expansão já executado (fase 5): guarda o resultado para a repetição da MESMA chave de idempotência devolver o mesmo
    resultado sem cobrar de novo, e conta quantos aportes do tipo a empresa já fez (entra na semente do sorteio)."""

    __tablename__ = "company_expansions"
    __table_args__ = (UniqueConstraint("company_id", "idempotency_key", name="uq_company_expansions_idem"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    ref_month: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20))
    tier: Mapped[str] = mapped_column(String(8))
    option_key: Mapped[str] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(8))                        # FULL | PARTIAL | FAIL
    cost: Mapped[Decimal] = mapped_column(Money())
    message: Mapped[str] = mapped_column(String(400))
    effects: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompanyRecruiter(Base):
    """Contratador (headhunter) OPCIONAL da empresa: um por empresa (a linha é reaproveitada ao recontratar). Taxa mensal por nível
    cobrada no fechamento (linha FEES) + comissão por contratação (HIRING). `settings` = briefing (JSON)."""

    __tablename__ = "company_recruiters"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_company_recruiters_company"),
        CheckConstraint("tier IN ('BASIC', 'PRO', 'ELITE')", name="ck_company_recruiters_tier"),
        CheckConstraint("status IN ('ACTIVE', 'ENDED')", name="ck_company_recruiters_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    tier: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(8), default="ACTIVE", server_default="ACTIVE")
    hired_month: Mapped[date] = mapped_column(Date)
    ended_month: Mapped[date | None] = mapped_column(Date)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    last_key: Mapped[str | None] = mapped_column(String(100), nullable=True)               # última chave de idempotência (contratar/trocar)


class CompanyRecruiterRun(Base):
    """Operação do contratador já executada: a repetição da MESMA chave de idempotência devolve o mesmo relatório sem cobrar de novo."""

    __tablename__ = "company_recruiter_runs"
    __table_args__ = (UniqueConstraint("company_id", "idempotency_key", name="uq_company_recruiter_runs_idem"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))                            # MANDATORY | TEAM | SUPPLIERS
    ref_month: Mapped[date] = mapped_column(Date)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompanyAide(Base):
    """Marketeiro ou gerente OPCIONAL da empresa (um de cada tipo por empresa; a linha é reaproveitada ao recontratar). `level`
    LOW/MID/HIGH; `settings` = briefing (marketeiro: orçamento mensal; gerente: rigidez)."""

    __tablename__ = "company_aides"
    __table_args__ = (
        UniqueConstraint("company_id", "kind", name="uq_company_aides_company_kind"),
        CheckConstraint("kind IN ('MARKETER', 'MANAGER')", name="ck_company_aides_kind"),
        CheckConstraint("level IN ('LOW', 'MID', 'HIGH')", name="ck_company_aides_level"),
        CheckConstraint("status IN ('ACTIVE', 'ENDED')", name="ck_company_aides_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))
    level: Mapped[str] = mapped_column(String(6))
    status: Mapped[str] = mapped_column(String(8), default="ACTIVE", server_default="ACTIVE")
    hired_month: Mapped[date] = mapped_column(Date)
    ended_month: Mapped[date | None] = mapped_column(Date)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)


class CompanyFranchise(Base):
    """Franquia da marca aberta por um terceiro. Rende ao dono uma taxa inicial e royalties mensais (bem menos que uma filial própria)."""

    __tablename__ = "company_franchises"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_company_franchises_status"),
        Index("ix_company_franchises_company_status", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    location: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(8), default="OPEN", server_default="OPEN")
    signed_month: Mapped[date] = mapped_column(Date)
    opens_month: Mapped[date] = mapped_column(Date)                        # o franqueado leva alguns meses para montar a loja
    viability: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("1"), server_default="1")
    royalty_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    initial_fee: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")
    total_royalties: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")
    closed_month: Mapped[date | None] = mapped_column(Date)
    closed_reason: Mapped[str | None] = mapped_column(String(160))


class CompanyListing(Base):
    """Abertura de capital (IPO): a empresa vira S.A. de capital aberto. `PENDING` até `lists_month` (prazo do processo), depois `LISTED`
    com preço por ação que evolui mensalmente; o dono é diluído (`owner_share_pct`) e o público recebe a sua parte dos dividendos."""

    __tablename__ = "company_listings"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_company_listings_company"),
        CheckConstraint("status IN ('PENDING', 'LISTED', 'DELISTED')", name="ck_company_listings_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    ticker: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(10), default="PENDING", server_default="PENDING")
    shares_total: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    float_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))              # % do capital vendido ao público no IPO
    valuation: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")   # valor da empresa no pedido
    ipo_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"), server_default="0")
    price: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"), server_default="0")
    proceeds: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"), server_default="0")   # captação líquida
    applied_month: Mapped[date] = mapped_column(Date)
    lists_month: Mapped[date] = mapped_column(Date)
    listed_month: Mapped[date | None] = mapped_column(Date)
    prev_owner_share: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("100"), server_default="100")
    history: Mapped[list] = mapped_column(JSON, default=list)
