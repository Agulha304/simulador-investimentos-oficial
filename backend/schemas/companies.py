"""Schemas de empresas. Decimal sai como string no JSON."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from backend.models import (
    CompanyChannel, CompanyCostKind, CompanyEventType, CompanySegment, CompanySize, CompanyStatus, EmployeeEducation, EmployeeLevel, EmployeeRegime, EmployeeStatus, WorkSchedule,
    FlowKind, InstallmentStatus, LeaseKind, LoanStatus, SiteMode,
)

Pos = Field(gt=0, max_digits=20, decimal_places=2)


# ------------------------------------------------------------------ entrada

class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    segment: CompanySegment
    channel: CompanyChannel | None = None              # padrão: física (ou online se o segmento só permitir online)
    site_mode: SiteMode | None = None                  # só canal físico: BUY (compra o terreno) ou RENT (padrão)
    location: str | None = None                        # chave do catálogo do segmento (padrão: bairro/primeira)
    size: CompanySize = CompanySize.SMALL
    extra_capital: Decimal = Field(Decimal("0"), ge=0, max_digits=20, decimal_places=2)   # além do mínimo para abrir
    owner_share_pct: Decimal = Field(Decimal("100"), gt=0, le=100, max_digits=5, decimal_places=2)
    partner_invite_ids: list[int] = []


class PartnerInviteIn(BaseModel):
    person_id: int
    share_pct: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)
    capital: Decimal = Pos


class QuoteIn(BaseModel):
    segment: CompanySegment
    channel: CompanyChannel | None = None
    site_mode: SiteMode | None = None
    location: str | None = None
    size: CompanySize = CompanySize.SMALL
    extra_capital: Decimal = Field(Decimal("0"), ge=0, max_digits=20, decimal_places=2)
    owner_share_pct: Decimal = Field(Decimal("100"), gt=0, le=100, max_digits=5, decimal_places=2)


class MoneyIn(BaseModel):
    amount: Decimal = Pos
    idempotency_key: str = Field(min_length=8, max_length=100)


class SettingsIn(BaseModel):
    price: Decimal | None = Field(None, gt=0, max_digits=20, decimal_places=2)
    owner_salary: Decimal | None = Field(None, ge=0, max_digits=20, decimal_places=2)
    auto_restock: bool | None = None


class CandidatesIn(BaseModel):
    role: str
    regime: EmployeeRegime = EmployeeRegime.CLT


class HireIn(BaseModel):
    """Proposta a um candidato. Só o id do candidato identifica quem é: pretensão, nível e escolaridade são recalculados no servidor."""
    candidate_id: str = Field(min_length=3, max_length=80)
    salary: Decimal = Pos
    hours_week: int = Field(ge=20, le=70)
    schedule: WorkSchedule
    regime: EmployeeRegime
    confirm_risk: bool = False
    idempotency_key: str = Field(min_length=8, max_length=100)


class HeadhunterIn(BaseModel):
    role: str
    regime: EmployeeRegime = EmployeeRegime.CLT
    max_salary: Decimal = Pos
    min_level: EmployeeLevel = EmployeeLevel.JUNIOR
    idempotency_key: str = Field(min_length=8, max_length=100)


class StockIn(BaseModel):
    item_id: int
    quantity: Decimal = Field(gt=0, max_digits=16, decimal_places=3)
    idempotency_key: str = Field(min_length=8, max_length=100)


class ExpandIn(BaseModel):
    kind: str = Field(pattern="^(CAPACITY|NEW_UNIT|LARGER_PREMISES|MARKETING)$")


class LeaseIn(BaseModel):
    kind: LeaseKind
    good_id: int | None = None
    monthly_rent: Decimal | None = Field(None, ge=0, max_digits=20, decimal_places=2)
    name: str | None = Field(None, max_length=120)


class LoanIn(BaseModel):
    amount: Decimal = Pos
    term_months: int = Field(ge=1, le=60)


class CompanyGoodIn(BaseModel):
    listing_key: str
    idempotency_key: str = Field(min_length=8, max_length=100)


# ------------------------------------------------------------------ saída

class RoleOut(BaseModel):
    key: str
    label: str
    salary: Decimal
    units: float
    generic: bool = False              # cargo geral (Contador, Advogado, Auxiliar de limpeza): não produz unidades
    mandatory: bool = False            # obrigatório para esta empresa (limpeza só no canal físico)


class LocationOut(BaseModel):
    key: str
    label: str
    demand: float
    rent_factor: Decimal
    land_price: Decimal                # terreno/ponto de porte pequeno


class SegmentOut(BaseModel):
    key: CompanySegment
    label: str
    description: str
    unit_label: str
    price: Decimal
    tax_pct: Decimal
    roles: list[RoleOut]
    stock: list[str]                   # vazio nos segmentos de serviço
    minimum_capital: Decimal           # para porte pequeno, canal padrão e ponto alugado
    channels: list[CompanyChannel]
    locations: list[LocationOut]
    metrics_kind: str                  # PRODUCTION | RETAIL | SERVICE
    default_location: str


class CatalogOut(BaseModel):
    segments: list[SegmentOut]
    sizes: list[dict]


class QuoteOut(BaseModel):
    channel: CompanyChannel
    site_mode: SiteMode | None
    location: str
    owner_share_pct: Decimal
    minimum_capital: Decimal           # mínimo para abrir (empresa inteira)
    owner_cost: Decimal                # parte do dono do mínimo (participação% × mínimo)
    extra_capital: Decimal
    total_owner_cost: Decimal          # owner_cost + extra_capital: o que sai da conta pessoal
    setup_cost: Decimal
    initial_stock: Decimal
    land_cost: Decimal
    monthly_fixed: Decimal             # custos fixos + aluguel, por mês
    monthly_rent: Decimal
    monthly_payroll: Decimal           # 1 mês de folha dos cargos obrigatórios (CLT, salário-base)
    mandatory_cost: Decimal            # folha de 1 mês + custo de contratação dos obrigatórios (já dentro do capital mínimo)
    mandatory_roles: list[str]         # nomes dos cargos obrigatórios
    expected_units: float


class CompanyOut(BaseModel):
    id: int
    name: str
    segment: CompanySegment
    segment_label: str
    unit_label: str
    metrics_kind: str
    channel: CompanyChannel
    site_mode: SiteMode | None
    site_value: Decimal
    location: str
    location_label: str
    size: CompanySize
    units: int
    capacity_level: int
    price: Decimal
    reputation: int
    owner_share_pct: Decimal
    owner_salary: Decimal
    auto_restock: bool
    status: CompanyStatus
    founded_on: date
    marketing_until: date | None
    cash: Decimal
    debts: Decimal
    equity: Decimal
    last_revenue: Decimal | None
    last_net_result: Decimal | None


class EmployeeOut(BaseModel):
    id: int
    name: str
    role: str
    role_label: str
    level: EmployeeLevel
    regime: EmployeeRegime
    schedule: WorkSchedule
    education: EmployeeEducation
    education_label: str
    experience_years: int
    salary: Decimal                    # salário negociado
    total_cost: Decimal                # custo mensal real: CLT 2x, PJ 1x
    severance_estimate: Decimal        # rescisão se demitir hoje
    lawsuit_risk_pct: float            # chance de processo trabalhista ao demitir hoje (%)
    hours_week: int
    productivity: Decimal
    status: EmployeeStatus
    hired_on: date
    terminated_on: date | None


class InventoryOut(BaseModel):
    id: int
    name: str
    unit: str
    quantity: Decimal
    unit_cost: Decimal
    value: Decimal
    supplier: str
    min_quantity: Decimal
    monthly_consumption_est: Decimal
    low: bool


class CostOut(BaseModel):
    id: int
    kind: CompanyCostKind
    name: str
    amount: Decimal
    active: bool


class LeaseOut(BaseModel):
    kind: LeaseKind
    good_id: int | None
    name: str
    monthly_rent: Decimal
    start_month: date


class InstallmentOut(BaseModel):
    number: int
    due_month: date
    payment: Decimal
    interest: Decimal
    amortization: Decimal
    balance_after: Decimal
    status: InstallmentStatus


class LoanOut(BaseModel):
    id: int
    principal: Decimal
    annual_rate_pct: Decimal
    term_months: int
    start_month: date
    balance: Decimal
    status: LoanStatus
    installments: list[InstallmentOut]


class CompanyGoodOut(BaseModel):
    id: int
    name: str
    category: str
    current_value: Decimal
    status: str


class MonthOut(BaseModel):
    ref_month: date
    demand_units: Decimal
    capacity_units: Decimal
    units_sold: Decimal
    stockout: bool
    revenue: Decimal
    variable_costs: Decimal
    fixed_costs: Decimal
    payroll: Decimal
    taxes: Decimal
    interest: Decimal
    operating_result: Decimal
    net_result: Decimal
    cash_end: Decimal
    debts_end: Decimal
    equity_end: Decimal
    reputation_end: int
    irregular: bool = False            # fechou sem cargos obrigatórios: vendas zeradas
    fines: Decimal = Decimal("0")      # multas do mês (dentro dos custos fixos)


class EventOut(BaseModel):
    ref_month: date
    type: CompanyEventType
    description: str
    amount: Decimal | None
    created_at: datetime


class LedgerLineOut(BaseModel):
    id: int
    kind: FlowKind
    amount: Decimal
    description: str
    line: str | None
    capital: bool
    ref_month: date


class RequiredRoleOut(BaseModel):
    role: str
    label: str
    present: bool


class ComplianceOut(BaseModel):
    regular: bool
    required: list[RequiredRoleOut]
    missing: list[str]                 # chaves dos cargos obrigatórios que faltam
    missing_labels: list[str]
    estimated_fine: Decimal            # multa que seria aplicada se o mês fechasse agora


class CandidateOut(BaseModel):
    id: str
    name: str
    role: str
    role_label: str
    regime: EmployeeRegime
    education: EmployeeEducation
    education_label: str
    experience_years: int
    level: EmployeeLevel
    level_label: str
    productivity: Decimal
    asking_salary: Decimal             # pretensão salarial
    hours_week: int                    # jornada pretendida
    schedule: WorkSchedule             # escala preferida
    monthly_cost_at_asking: Decimal    # custo real mensal se pagar a pretensão (CLT 2x / PJ 1x)


class CandidatesOut(BaseModel):
    role: str
    regime: EmployeeRegime
    month: date
    candidates: list[CandidateOut]


class CompanyDetailOut(BaseModel):
    company: CompanyOut
    distributable_profit: Decimal
    runway_months: Decimal | None
    monthly_obligations: Decimal
    loan_limit: Decimal
    expected_demand: float
    expected_capacity: float
    expansion_costs: dict[str, Decimal]
    roles: list[RoleOut]
    employees: list[EmployeeOut]
    inventory: list[InventoryOut]
    costs: list[CostOut]
    lease: LeaseOut | None
    loans: list[LoanOut]
    goods: list[CompanyGoodOut]
    months: list[MonthOut]
    events: list[EventOut]
    ledger: list[LedgerLineOut]
    partners: list[dict] = []
    compliance: ComplianceOut | None = None


class HireOut(BaseModel):
    accepted: bool
    status: str                        # ACCEPTED | COUNTER | REFUSED
    message: str
    counter_offer: Decimal | None = None
    company: CompanyDetailOut | None = None


class HeadhunterOut(BaseModel):
    fee: Decimal
    found: int
    message: str
    candidates: list[CandidateOut]
    company: CompanyDetailOut


class OverviewOut(BaseModel):
    count: int
    equity_total: Decimal              # patrimônio empresarial (100%)
    equity_user_share: Decimal         # parte do usuário (entra no patrimônio total)
    cash_total: Decimal
    debts_total: Decimal
    revenue_last_month: Decimal
    expenses_last_month: Decimal
    net_last_month: Decimal
    companies: list[CompanyOut]
