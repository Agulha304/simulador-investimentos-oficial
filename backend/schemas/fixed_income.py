from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from backend.models import (
    EventKind, FixedIncomeType, Indexer, InvestmentStatus, Liquidity, PaymentFrequency, ProductSource, RateMode,
    RiskLevel, TaxRegime,
)
from backend.services.fixed_income_service import rate_label


class ProductBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    issuer: str
    product_type: FixedIncomeType
    indexer: Indexer
    rate_mode: RateMode
    rate: Decimal

    @computed_field
    @property
    def rate_label(self) -> str:
        return rate_label(self)


class ProductOut(ProductBrief):
    maturity_date: date
    min_investment_brl: Decimal
    liquidity: Liquidity
    grace_days: int
    liquidity_dates: list[str]
    early_redemption: bool
    secondary_discount_pct: Decimal
    uses_mtm: bool
    payment_frequency: PaymentFrequency
    tax_regime: TaxRegime
    risk_level: RiskLevel
    fgc_covered: bool
    description: str | None
    source: ProductSource
    as_of: date
    unit_price: Decimal | None = None
    market_rate: Decimal | None = None


class InvestRequest(BaseModel):
    product_id: int
    amount_brl: Decimal = Field(gt=0, max_digits=20, decimal_places=2)


class SimulateRequest(InvestRequest):
    pass


class FlowOut(BaseModel):
    on: date
    kind: str
    gross: Decimal
    tax: Decimal
    net: Decimal


class SimulationOut(BaseModel):
    product: ProductBrief
    principal_brl: Decimal
    total_gross_brl: Decimal
    total_tax_brl: Decimal
    total_net_brl: Decimal
    profit_net_brl: Decimal
    annualized_net_pct: Decimal | None
    flows: list[FlowOut]
    assumptions: str


class InvestmentOut(BaseModel):
    id: int
    product: ProductBrief
    status: InvestmentStatus
    applied_on: date
    maturity_date: date
    principal_brl: Decimal
    units: Decimal | None
    current_gross_brl: Decimal            # ativa: valor bruto hoje; encerrada: valor bruto do encerramento
    estimated_tax_brl: Decimal
    estimated_net_brl: Decimal
    interest_paid_net_brl: Decimal        # juros líquidos já recebidos (cupons)
    profit_net_brl: Decimal               # líquido atual + juros recebidos − principal
    valuation_method: str                 # CURVE | MTM | CLOSED
    can_redeem: bool
    redeem_block_reason: str | None
    redeem_net_brl: Decimal | None
    next_event_date: date | None
    next_event_kind: EventKind | None
    closed_on: date | None


class IndexesOut(BaseModel):
    cdi_annual: Decimal
    selic_annual: Decimal
    ipca_12m: Decimal
    igpm_12m: Decimal
    last_cdi_date: date | None
    source: str = "Banco Central do Brasil (SGS)"
    updated_at: datetime | None = None
