"""Schemas de saída. Decimal é serializado como STRING no JSON, para que o
frontend não perca precisão (ex.: quantidades de cripto com 18 casas)."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from backend.models import AssetClass, Currency, DistributionKind, EligibilityStatus, TransactionSource, TransactionType


class AssetBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    symbol: str
    name: str
    asset_class: AssetClass
    currency: Currency


class HoldingOut(BaseModel):
    asset: AssetBrief
    quantity: Decimal
    avg_price_brl: Decimal
    total_cost_brl: Decimal
    current_price_brl: Decimal | None
    stop_loss: Decimal | None = None          # na moeda do ativo
    take_profit: Decimal | None = None
    market_value_brl: Decimal
    pnl_brl: Decimal
    pnl_pct: Decimal | None
    quote_fetched_at: datetime | None = None   # quando a cotação foi buscada
    quote_stale: bool = False                  # cotação além do TTL (atualizando em segundo plano)


class PortfolioSummaryOut(BaseModel):
    id: int
    name: str
    base_currency: Currency
    cash_balance: Decimal
    invested_brl: Decimal
    market_value_brl: Decimal
    total_equity_brl: Decimal
    total_deposits_brl: Decimal
    pnl_brl: Decimal
    pnl_pct: Decimal | None
    fixed_income_invested_brl: Decimal
    fixed_income_value_brl: Decimal
    goods_net_brl: Decimal = Decimal("0.00")
    companies_net_brl: Decimal = Decimal("0.00")
    personal_debts_brl: Decimal = Decimal("0.00")
    holdings: list[HoldingOut]


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: TransactionType
    source: TransactionSource
    asset: AssetBrief | None
    quantity: Decimal | None
    unit_price: Decimal | None
    price_currency: Currency | None
    fx_rate: Decimal | None
    unit_price_brl: Decimal | None
    gross_amount_brl: Decimal
    tax_brl: Decimal
    fee_brl: Decimal
    cash_amount_brl: Decimal
    cash_balance_after: Decimal
    realized_pnl_brl: Decimal | None = None
    note: str | None
    created_at: datetime


class DividendItemOut(BaseModel):
    id: int                              # id da elegibilidade
    asset: AssetBrief
    kind: DistributionKind
    ex_date: date
    pay_date: date
    pay_date_estimated: bool
    status: EligibilityStatus
    quantity: Decimal
    amount_per_unit: Decimal
    currency: Currency
    expected_gross_native: Decimal       # quantidade × valor, na moeda do ativo
    gross_brl: Decimal | None = None     # preenchidos após o pagamento
    tax_brl: Decimal | None = None
    net_brl: Decimal | None = None
    paid_at: datetime | None = None


class DividendSyncOut(BaseModel):
    new_rights: int
    paid: int
