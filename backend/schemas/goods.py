"""Schemas de bens e patrimônio. Decimal sai como string no JSON."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from backend.models import (
    AmortizationSystem, Condition, CostKind, Frequency, GoodCategory, GoodEventType, GoodStatus, InstallmentStatus,
    LoanStatus, Occupancy, ValueSource,
)

Pos = Field(gt=0, max_digits=20, decimal_places=2)
NonNeg = Field(ge=0, max_digits=20, decimal_places=2)


# ------------------------------------------------------------------ entrada

class PurchaseIn(BaseModel):
    listing_key: str
    idempotency_key: str = Field(min_length=8, max_length=100)
    financed: bool = False
    down_payment: Decimal | None = Field(None, ge=0, max_digits=20, decimal_places=2)
    term_months: int = Field(0, ge=0, le=480)
    system: AmortizationSystem = AmortizationSystem.PRICE
    annual_rate_pct: Decimal | None = Field(None, ge=0, le=100, max_digits=8, decimal_places=4)
    extra_costs: Decimal = Field(Decimal("0"), ge=0, max_digits=20, decimal_places=2)
    usage_km_month: int | None = Field(None, ge=0, le=20000)


class SimulateIn(BaseModel):
    listing_key: str
    down_payment: Decimal = NonNeg
    term_months: int = Field(ge=1, le=480)
    system: AmortizationSystem = AmortizationSystem.PRICE
    annual_rate_pct: Decimal | None = Field(None, ge=0, le=100, max_digits=8, decimal_places=4)


class SaleIn(BaseModel):
    sale_price: Decimal | None = Field(None, gt=0, max_digits=20, decimal_places=2)
    extra_fees: Decimal = Field(Decimal("0"), ge=0, max_digits=20, decimal_places=2)


class OccupancyIn(BaseModel):
    mode: Occupancy
    monthly_rent: Decimal | None = Field(None, gt=0, max_digits=20, decimal_places=2)
    end_recurring_item_ids: list[int] = []


class CostIn(BaseModel):
    kind: CostKind
    name: str = Field("", max_length=80)
    amount: Decimal = Pos
    frequency: Frequency = Frequency.MONTHLY


class CostPatch(BaseModel):
    amount: Decimal | None = Field(None, gt=0, max_digits=20, decimal_places=2)
    active: bool | None = None
    frequency: Frequency | None = None


class MaintenanceIn(BaseModel):
    amount: Decimal = Pos
    description: str = Field("", max_length=200)
    idempotency_key: str | None = Field(None, min_length=8, max_length=100)


class WriteOffIn(BaseModel):
    reason: str = Field("", max_length=200)


class GoodPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=1000)
    location: str | None = Field(None, max_length=120)
    condition: Condition | None = None


# ------------------------------------------------------------------ saída

class FinancingOut(BaseModel):
    max_ltv_pct: Decimal
    min_down_payment: Decimal
    annual_rate_pct: Decimal
    max_term_months: int


class ListingOut(BaseModel):
    key: str
    category: GoodCategory
    name: str
    description: str
    price: Decimal
    purchase_fee: Decimal
    location: str
    condition: Condition | None
    property_type: str | None
    address: str | None
    area_m2: Decimal | None
    bedrooms: int | None
    suggested_rent: Decimal | None
    owned: bool
    financing: FinancingOut | None


class InstallmentOut(BaseModel):
    number: int
    due_month: date
    payment: Decimal
    interest: Decimal
    amortization: Decimal
    balance_after: Decimal
    status: InstallmentStatus | None = None


class SimulationOut(BaseModel):
    price: Decimal
    down_payment: Decimal
    financed: Decimal
    annual_rate_pct: Decimal
    first_payment: Decimal
    last_payment: Decimal
    total_interest: Decimal
    total_paid: Decimal
    purchase_fee: Decimal
    cash_needed_now: Decimal
    preview: list[InstallmentOut]


class GoodOut(BaseModel):
    id: int
    name: str
    category: GoodCategory
    status: GoodStatus
    condition: Condition | None
    location: str | None
    acquired_on: date
    purchase_price: Decimal
    acquisition_cost: Decimal
    current_value: Decimal
    unrealized_result: Decimal
    occupancy: Occupancy | None
    monthly_rent: Decimal | None
    loan_balance: Decimal | None
    sold_on: date | None
    sale_result: Decimal | None


class RealEstateOut(BaseModel):
    property_type: str
    address: str
    area_m2: Decimal
    bedrooms: int | None
    occupancy: Occupancy
    monthly_rent: Decimal
    rent_tax_pct: Decimal
    market_rent: Decimal


class CostOut(BaseModel):
    id: int
    kind: CostKind
    name: str
    amount: Decimal
    frequency: Frequency
    start_month: date
    active: bool


class ValueOut(BaseModel):
    ref_month: date
    value: Decimal
    source: ValueSource


class EventOut(BaseModel):
    ref_month: date
    type: GoodEventType
    description: str
    amount: Decimal | None
    created_at: datetime


class LoanOut(BaseModel):
    principal: Decimal
    down_payment: Decimal
    annual_rate_pct: Decimal
    term_months: int
    system: AmortizationSystem
    start_month: date
    end_month: date
    balance: Decimal
    status: LoanStatus
    paid_installments: int
    next_payment: Decimal | None
    installments: list[InstallmentOut]


class GoodEntryOut(BaseModel):
    id: int
    kind: str
    amount: Decimal
    description: str
    ref_month: date
    capital: bool
    origin: str


class AppraisalOut(BaseModel):
    estimate: Decimal
    low: Decimal
    high: Decimal
    uncertainty_pct: Decimal


class GoodDetailOut(BaseModel):
    good: GoodOut
    description: str | None
    real_estate: RealEstateOut | None
    vehicle_usage_km_month: int | None
    costs: list[CostOut]
    values: list[ValueOut]
    events: list[EventOut]
    loan: LoanOut | None
    entries: list[GoodEntryOut]
    income_total: Decimal
    expense_total: Decimal
    appraisal: AppraisalOut


class SaleQuoteOut(BaseModel):
    sale_price: Decimal
    fees: Decimal
    loan_payoff: Decimal
    net_cash: Decimal
    result: Decimal


class HousingCandidateOut(BaseModel):
    id: int
    name: str
    amount: Decimal | None


class SeriesPoint(BaseModel):
    ref_month: date
    goods_value: Decimal
    debts: Decimal
    net: Decimal


class CategoryTotalOut(BaseModel):
    category: GoodCategory
    count: int
    value: Decimal


class WealthOverviewOut(BaseModel):
    count: int
    sold_count: int
    total_value: Decimal
    total_acquisition_cost: Decimal
    debts: Decimal
    net_worth: Decimal
    unrealized_result: Decimal
    monthly_income: Decimal
    monthly_expense: Decimal
    monthly_debt_service: Decimal
    income_received_total: Decimal
    expense_paid_total: Decimal
    by_category: list[CategoryTotalOut]
    series: list[SeriesPoint]
