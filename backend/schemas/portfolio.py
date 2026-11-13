"""Schemas de saída. Decimal é serializado como STRING no JSON, para que o
frontend não perca precisão (ex.: quantidades de cripto com 18 casas)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from backend.models import AssetClass, Currency, TransactionSource, TransactionType


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
    market_value_brl: Decimal
    pnl_brl: Decimal
    pnl_pct: Decimal | None


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
