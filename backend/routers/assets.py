from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from backend.dependencies import CurrentUser, DbSession
from backend.models import Asset, AssetClass, ChartLayout
from backend.schemas.market import (
    AssetOut, CandleOut, ChartOut, Drawing, IndicatorOut, LayoutIn, LayoutOut, QuoteBrief, QuoteOut,
)
from backend.services import asset_catalog, indicators, market_data

router = APIRouter(prefix="/assets", tags=["assets"])


def _get_asset(db, asset_id: int) -> Asset:
    asset = db.get(Asset, asset_id)
    if not asset or not asset.is_active:
        raise HTTPException(404, "Ativo não encontrado")
    return asset


@router.get("/search", response_model=list[AssetOut])
def search_assets(_: CurrentUser, db: DbSession, q: str = Query(min_length=1, max_length=60)):
    return asset_catalog.search(db, q)


@router.get("", response_model=list[AssetOut])
def list_assets(
    _: CurrentUser, db: DbSession,
    asset_class: AssetClass | None = None, country: Annotated[str | None, Query(pattern="^[A-Za-z]{2}$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60, offset: Annotated[int, Query(ge=0)] = 0,
):
    """Navegação por classe (ações, ETFs, FIIs, REITs, cripto) e país."""
    q = select(Asset).where(Asset.is_active)
    if asset_class:
        q = q.where(Asset.asset_class == asset_class)
    if country:
        q = q.where(Asset.country == country.upper())
    return list(db.scalars(q.order_by(Asset.symbol).limit(limit).offset(offset)))


@router.get("/quotes", response_model=list[QuoteBrief])
def get_quotes(_: CurrentUser, db: DbSession, ids: Annotated[str, Query(max_length=400)]):
    """Cotações de vários ativos de uma vez. Ativos sem cotação disponível são omitidos."""
    try:
        wanted = list(dict.fromkeys(int(x) for x in ids.split(",") if x.strip()))[:40]
    except ValueError:
        raise HTTPException(422, "ids inválidos") from None
    assets = {a.id: a for a in db.scalars(select(Asset).where(Asset.id.in_(wanted), Asset.is_active))}

    def one(a: Asset) -> QuoteBrief | None:
        try:
            pq = market_data.get_priced_quote(a, allow_stale=True)
        except market_data.MarketDataUnavailable:
            return None
        return QuoteBrief(asset_id=a.id, price=pq.quote.price, currency=pq.quote.currency,
                          price_brl=pq.price_brl, change_pct=pq.quote.change_pct, as_of=pq.quote.as_of,
                          fetched_at=pq.fetched_at, stale=pq.stale)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(one, [assets[i] for i in wanted if i in assets]))
    return [r for r in results if r is not None]


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: int, _: CurrentUser, db: DbSession):
    return _get_asset(db, asset_id)


@router.get("/{asset_id}/quote", response_model=QuoteOut)
def get_asset_quote(asset_id: int, _: CurrentUser, db: DbSession):
    asset = _get_asset(db, asset_id)
    try:
        pq = market_data.get_priced_quote(asset, allow_stale=True)
    except market_data.MarketDataUnavailable:
        raise HTTPException(503, "Cotação indisponível no momento") from None
    return QuoteOut(asset_id=asset.id, price=pq.quote.price, currency=pq.quote.currency, fx_rate=pq.fx_rate,
                    price_brl=pq.price_brl, change_pct=pq.quote.change_pct, as_of=pq.quote.as_of,
                    fetched_at=pq.fetched_at, stale=pq.stale)


@router.get("/{asset_id}/chart", response_model=ChartOut)
def get_chart(
    asset_id: int, _: CurrentUser, db: DbSession,
    period: Annotated[str, Query(pattern="^(1d|5d|1mo|6mo|1y|5y|max)$")] = "6mo",
    indicators_: Annotated[str, Query(alias="indicators", max_length=300)] = "",
):
    """Candles OHLCV + indicadores calculados no servidor (ex.: indicators=sma:20,rsi:14,macd)."""
    asset = _get_asset(db, asset_id)
    specs = [x for x in indicators_.split(",") if x.strip()]
    try:
        candles = market_data.get_history(asset, period)
        calc = indicators.compute(candles, specs, intraday=period in market_data.INTRADAY_RANGES)
    except indicators.IndicatorError as exc:
        raise HTTPException(422, str(exc)) from None
    except market_data.MarketDataUnavailable:
        raise HTTPException(503, "Histórico indisponível no momento") from None
    return ChartOut(
        asset_id=asset.id, period=period, currency=asset.currency,
        candles=[CandleOut(time=c.time, open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume) for c in candles],
        indicators={k: IndicatorOut(**v) for k, v in calc.items()},
    )


@router.get("/{asset_id}/layout", response_model=LayoutOut)
def get_layout(asset_id: int, user: CurrentUser, db: DbSession):
    _get_asset(db, asset_id)
    row = db.scalar(select(ChartLayout).where(ChartLayout.user_id == user.id, ChartLayout.asset_id == asset_id))
    if row is None:
        return LayoutOut()
    return LayoutOut(indicators=row.indicators, drawings=[Drawing.model_validate(d) for d in row.drawings])


@router.put("/{asset_id}/layout", response_model=LayoutOut)
def put_layout(asset_id: int, body: LayoutIn, user: CurrentUser, db: DbSession):
    _get_asset(db, asset_id)
    try:
        for spec in body.indicators:
            indicators.parse_spec(spec)
    except indicators.IndicatorError as exc:
        raise HTTPException(422, str(exc)) from None
    row = db.scalar(select(ChartLayout).where(ChartLayout.user_id == user.id, ChartLayout.asset_id == asset_id))
    if row is None:
        row = ChartLayout(user_id=user.id, asset_id=asset_id)
        db.add(row)
    row.indicators = body.indicators
    row.drawings = [d.model_dump(mode="json") for d in body.drawings]
    db.commit()
    return body
