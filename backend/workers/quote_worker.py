"""Aquece o cache de cotações em segundo plano: as telas quase nunca esperam a fonte externa.

A sessão do banco é FECHADA antes de qualquer chamada HTTP (nada de conexão presa esperando o Yahoo)."""
import logging

from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import Asset, Currency, Holding
from backend.services import market_data

log = logging.getLogger(__name__)
MAX_SYMBOLS = 150


def run() -> None:
    with SessionLocal() as db:
        rows = list(db.scalars(select(Asset.provider_symbol).join(Holding, Holding.asset_id == Asset.id)
                               .where(Holding.quantity > 0).group_by(Asset.provider_symbol).limit(MAX_SYMBOLS)))
    if not rows:
        return
    symbols = list(dict.fromkeys([*market_data.FX_SYMBOLS.values(), *rows]))
    n = market_data.warm(symbols)
    log.debug("cotações renovadas: %d de %d", n, len(symbols))
