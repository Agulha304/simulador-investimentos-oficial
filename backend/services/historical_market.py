"""Mercado histórico (modo treino): preços reais de uma data do passado, a partir das séries mensais do provedor.

Convenção: o relógio de um mês aponta para o dia 1 e o preço é a ABERTURA do mês (≈ fechamento do mês anterior).
Avançar um mês mostra, portanto, a variação real que aconteceu. Antes de o ativo existir não há preço: o ativo fica
indisponível naquela data (e a interface explica).
"""
import threading
import time
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal

from backend.core.clock import MarketClock
from backend.models import Currency
from backend.services import market_data
from backend.services.market_data import Candle, MarketDataUnavailable, Quote

_lock = threading.Lock()
_cache: dict[str, tuple[float, list[tuple[date, Candle]]]] = {}
TTL = 6 * 3600.0
MIN_DATE = date(2015, 1, 1)


def monthly(symbol: str) -> list[tuple[date, Candle]]:
    """Série mensal [(1º dia do mês, candle agregado)] — agrega candles diários se a fonte entregar mais que um por mês."""
    now = time.monotonic()
    with _lock:
        hit = _cache.get(symbol)
        if hit and now - hit[0] < TTL:
            return hit[1]
    raw = market_data._provider.get_history(symbol, "max")
    by_month: dict[date, list[Candle]] = defaultdict(list)
    for c in sorted(raw, key=lambda c: c.time):
        d = datetime.fromtimestamp(c.time, UTC).date()
        by_month[date(d.year, d.month, 1)].append(c)
    out = []
    for m, cs in sorted(by_month.items()):
        out.append((m, Candle(cs[0].time, cs[0].open, max(c.high for c in cs), min(c.low for c in cs), cs[-1].close,
                              sum((c.volume for c in cs), Decimal(0)))))
    with _lock:
        _cache[symbol] = (now, out)
    return out


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def price_at(symbol: str, day: date) -> tuple[Decimal, Decimal | None]:
    """(preço no mês de `day`, preço no mês anterior). Levanta MarketDataUnavailable se não existia cotação."""
    key = date(day.year, day.month, 1)
    series = monthly(symbol)
    for i, (m, c) in enumerate(series):
        if m == key:
            prev = series[i - 1][1].open if i > 0 else None
            return c.open, prev
        if m > key:
            break
    raise MarketDataUnavailable(f"sem cotação de {symbol} em {key:%m/%Y}")


def _quote(asset, day: date) -> Quote:
    price, prev = price_at(asset.provider_symbol, day)
    return Quote(price, asset.currency, datetime(day.year, day.month, day.day, tzinfo=UTC), prev)


def _fx(currency: Currency, day: date) -> Decimal:
    symbol = market_data.FX_SYMBOLS.get(currency)
    if symbol is None:
        raise MarketDataUnavailable(f"sem câmbio para {currency}")
    return price_at(symbol, day)[0]


def _history(asset, period: str, day: date) -> list[Candle]:
    """Candles até a data do relógio (nada do futuro aparece). Períodos intradiários não existem no passado."""
    if period in market_data.INTRADAY_RANGES:
        return []
    months = {"1mo": 2, "6mo": 7, "1y": 13, "5y": 61, "max": 10_000}[period]
    series = [c for m, c in monthly(asset.provider_symbol) if m <= date(day.year, day.month, 1)]
    return series[-months:]


def clock_for(day: date) -> MarketClock:
    return MarketClock("HISTORICAL", day, quote_fn=lambda a: _quote(a, day), fx_fn=lambda cur: _fx(cur, day),
                       history_fn=lambda a, p: _history(a, p, day))
