from fastapi import APIRouter, HTTPException, Query

from backend.dependencies import CurrentUser, DbSession
from backend.models import Asset
from backend.schemas.market import AssetOut, QuoteOut
from backend.services import asset_catalog, market_data

router = APIRouter(prefix="/assets", tags=["assets"])


def _get_asset(db, asset_id: int) -> Asset:
    asset = db.get(Asset, asset_id)
    if not asset or not asset.is_active:
        raise HTTPException(404, "Ativo não encontrado")
    return asset


@router.get("/search", response_model=list[AssetOut])
def search_assets(_: CurrentUser, db: DbSession, q: str = Query(min_length=1, max_length=60)):
    return asset_catalog.search(db, q)


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: int, _: CurrentUser, db: DbSession):
    return _get_asset(db, asset_id)


@router.get("/{asset_id}/quote", response_model=QuoteOut)
def get_asset_quote(asset_id: int, _: CurrentUser, db: DbSession):
    asset = _get_asset(db, asset_id)
    try:
        pq = market_data.get_priced_quote(asset)
    except market_data.MarketDataUnavailable:
        raise HTTPException(503, "Cotação indisponível no momento") from None
    return QuoteOut(asset_id=asset.id, price=pq.quote.price, currency=pq.quote.currency, fx_rate=pq.fx_rate,
                    price_brl=pq.price_brl, change_pct=pq.quote.change_pct, as_of=pq.quote.as_of)
