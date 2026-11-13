from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=38, decimal_places=18)
    amount_brl: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=2)


class DepositRequest(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("10000000"), max_digits=20, decimal_places=2)


class CandleOut(BaseModel):
    time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class IndicatorOut(BaseModel):
    kind: str                                   # overlay | pane
    series: dict[str, list[Decimal | None]]     # alinhadas a `candles`


class ChartOut(BaseModel):
    asset_id: int
    period: str
    currency: Currency
    candles: list[CandleOut]
    indicators: dict[str, IndicatorOut]


DrawingType = Literal["trend", "ray", "hline", "support", "resistance", "marker"]
POINTS_REQUIRED: dict[str, int] = {"trend": 2, "ray": 2, "hline": 1, "support": 1, "resistance": 1, "marker": 1}


class DrawingPoint(BaseModel):
    """Âncora do desenho no gráfico: instante (unix s, UTC) e preço na moeda do ativo.
    Por ser tempo+preço (e não pixels), o desenho acompanha zoom, pan e troca de período."""
    time: int = Field(ge=0, le=4_102_444_800)
    price: Decimal = Field(gt=0, max_digits=28, decimal_places=10)


class Drawing(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    type: DrawingType
    points: list[DrawingPoint]
    text: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")

    @model_validator(mode="after")
    def _check_points(self):
        need = POINTS_REQUIRED[self.type]
        if len(self.points) != need:
            raise ValueError(f"'{self.type}' exige {need} ponto(s)")
        return self


class LayoutIn(BaseModel):
    indicators: list[str] = Field(default_factory=list, max_length=12)
    drawings: list[Drawing] = Field(default_factory=list, max_length=300)

    @model_validator(mode="after")
    def _unique_ids(self):
        ids = [d.id for d in self.drawings]
        if len(ids) != len(set(ids)):
            raise ValueError("ids de desenhos devem ser únicos")
        return self


class LayoutOut(LayoutIn):
    pass


class RiskIn(BaseModel):
    """Níveis na moeda do ativo; null desativa o nível."""
    stop_loss: Decimal | None = Field(default=None, gt=0, max_digits=28, decimal_places=10)
    take_profit: Decimal | None = Field(default=None, gt=0, max_digits=28, decimal_places=10)


class RiskOut(RiskIn):
    asset_id: int
    currency: Currency


class QuoteBrief(BaseModel):
    asset_id: int
    price: Decimal
    currency: Currency
    price_brl: Decimal
    change_pct: Decimal | None
