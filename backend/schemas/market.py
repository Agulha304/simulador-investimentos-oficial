from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from backend.models import AssetClass, Currency


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    symbol: str
    name: str
    asset_class: AssetClass
    exchange: str
    country: str | None
    currency: Currency
    allows_fractional: bool


class QuoteOut(BaseModel):
    asset_id: int
    price: Decimal                 # na moeda do ativo
    currency: Currency
    fx_rate: Decimal               # moeda do ativo -> BRL
    price_brl: Decimal
    change_pct: Decimal | None
    as_of: datetime


class BuyRequest(BaseModel):
    asset_id: int
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=38, decimal_places=18)
    amount_brl: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=2)


class SellRequest(BaseModel):
    asset_id: int
    quantity: Decimal = Field(gt=0, max_digits=38, decimal_places=18)


class DepositRequest(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("10000000"), max_digits=20, decimal_places=2)
