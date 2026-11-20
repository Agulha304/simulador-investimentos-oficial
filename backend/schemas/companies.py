"""Schemas de empresas. Decimal sai como string no JSON."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from backend.models import (
    CompanyCostKind, CompanyEventType, CompanySegment, CompanySize, CompanyStatus, EmployeeLevel, EmployeeStatus,
    FlowKind, InstallmentStatus, LeaseKind, LoanStatus,
)

Pos = Field(gt=0, max_digits=20, decimal_places=2)


# ------------------------------------------------------------------ entrada

class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    segment: CompanySegment
    location: str = "bairro"
    size: CompanySize = CompanySize.SMALL
    capital: Decimal = Pos
    owner_share_pct: Decimal = Field(Decimal("100"), gt=0, le=100, max_digits=5, decimal_places=2)
    business_type: str = Field("", max_length=60)
    partner_invite_ids: list[int] = []


class PartnerInviteIn(BaseModel):
    person_id: int
    share_pct: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)
    capital: Decimal = Pos


class QuoteIn(BaseModel):
    segment: CompanySegment
    location: str = "bairro"
    size: CompanySize = CompanySize.SMALL


class MoneyIn(BaseModel):
    amount: Decimal = Pos
    idempotency_key: str = Field(min_length=8, max_length=100)


class SettingsIn(BaseModel):
    price: Decimal | None = Field(None, gt=0, max_digits=20, decimal_places=2)
    owner_salary: Decimal | None = Field(None, ge=0, max_digits=20, decimal_places=2)
    auto_restock: bool | None = None


class HireIn(BaseModel):
    role: str
    level: EmployeeLevel = EmployeeLevel.MID
    confirm_risk: bool = False


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


class SegmentOut(BaseModel):
    key: CompanySegment
    label: str
    description: str
    unit_label: str
    price: Decimal
    tax_pct: Decimal
    roles: list[RoleOut]
    stock: list[str]
    required_capital: Decimal          # para porte pequeno em bairro residencial


class CatalogOut(BaseModel):
    segments: list[SegmentOut]
    locations: list[dict]
    sizes: list[dict]


class QuoteOut(BaseModel):
    required_capital: Decimal
    setup_cost: Decimal
    monthly_fixed: Decimal
    monthly_payroll: Decimal
    initial_stock: Decimal
    expected_units: float


class CompanyOut(BaseModel):
    id: int
    name: str
    segment: CompanySegment
    segment_label: str
    business_type: str
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
    role: str
    role_label: str
    level: EmployeeLevel
    salary: Decimal
    total_cost: Decimal
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
