"""Camada ISOLADA de dados de mercado. Nenhum outro módulo conhece o Yahoo.

Para trocar de fonte, implemente `MarketDataProvider` e chame `set_provider`.
Todos os valores saem como Decimal (via `to_decimal`, nunca float direto).
"""
import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

import httpx

from backend.core.money import quantize_price, to_decimal
from backend.models import Asset, Currency

log = logging.getLogger(__name__)


class MarketDataUnavailable(Exception):
    """A fonte não retornou dados utilizáveis (rede, limite, símbolo inválido)."""


@dataclass(frozen=True)
class Quote:
    price: Decimal                    # na moeda do ativo
    currency: Currency
    as_of: datetime
    previous_close: Decimal | None = None

    @property
    def change_pct(self) -> Decimal | None:
        if not self.previous_close:
            return None
        return ((self.price - self.previous_close) / self.previous_close * 100).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class SearchHit:
    provider_symbol: str
    symbol: str
    name: str
    quote_type: str                   # EQUITY, ETF, CRYPTOCURRENCY...
    exchange: str


class MarketDataProvider(Protocol):
    def get_quote(self, provider_symbol: str) -> Quote: ...
    def search(self, query: str) -> list[SearchHit]: ...


class YahooProvider:
    CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"
    HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}

    def __init__(self) -> None:
        self._client = httpx.Client(headers=self.HEADERS, timeout=10.0)

    def _get(self, url: str, params: dict) -> dict:
        last: Exception | None = None
        for attempt in range(3):
            try:
                r = self._client.get(url, params=params)
                if r.status_code == 429:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
                time.sleep(0.5)
        raise MarketDataUnavailable(f"falha ao consultar {url}: {last}")

    def get_quote(self, provider_symbol: str) -> Quote:
        data = self._get(self.CHART.format(symbol=provider_symbol), {"range": "5d", "interval": "1d"})
        try:
            result = data["chart"]["result"][0]
            meta = result["meta"]
            price = to_decimal(meta["regularMarketPrice"])
            currency = Currency(meta["currency"])
            as_of = datetime.fromtimestamp(meta["regularMarketTime"], UTC)
            closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
            stamps = result.get("timestamp") or []
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise MarketDataUnavailable(f"resposta inesperada para {provider_symbol}") from exc
        prev = None
        if closes:
            last_is_today = stamps and datetime.fromtimestamp(stamps[-1], UTC).date() == as_of.date()
            idx = -2 if last_is_today and len(closes) >= 2 else -1
            prev = to_decimal(closes[idx])
        return Quote(quantize_price(price), currency, as_of, quantize_price(prev) if prev else None)

    def search(self, query: str) -> list[SearchHit]:
        data = self._get(self.SEARCH, {"q": query, "quotesCount": 8, "newsCount": 0})
        hits = []
        for q in data.get("quotes", []):
            if q.get("quoteType") not in {"EQUITY", "ETF", "CRYPTOCURRENCY"} or not q.get("symbol"):
                continue
            hits.append(SearchHit(
                provider_symbol=q["symbol"],
                symbol=q["symbol"].removesuffix(".SA").removesuffix("-USD"),
                name=q.get("longname") or q.get("shortname") or q["symbol"],
                quote_type=q["quoteType"],
                exchange=q.get("exchDisp") or q.get("exchange") or "",
            ))
        return hits


# ---------------------------------------------------------------- cache + API

_provider: MarketDataProvider = YahooProvider()
_cache: dict[str, tuple[float, Quote]] = {}
_lock = threading.Lock()
QUOTE_TTL = 60.0
FX_TTL = 300.0
FX_SYMBOLS = {Currency.USD: "USDBRL=X"}


def set_provider(p: MarketDataProvider) -> None:
    global _provider
    _provider = p
    clear_cache()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _cached_quote(provider_symbol: str, ttl: float) -> Quote:
    now = time.monotonic()
    with _lock:
        hit = _cache.get(provider_symbol)
        if hit and now - hit[0] < ttl:
            return hit[1]
    try:
        quote = _provider.get_quote(provider_symbol)
    except MarketDataUnavailable:
        with _lock:
            stale = _cache.get(provider_symbol)
        if stale:
            log.warning("usando cotação em cache (fonte indisponível): %s", provider_symbol)
            return stale[1]
        raise
    with _lock:
        _cache[provider_symbol] = (now, quote)
    return quote


def get_quote(asset: Asset) -> Quote:
    return _cached_quote(asset.provider_symbol, QUOTE_TTL)


def get_fx_rate(currency: Currency) -> Decimal:
    """Taxa moeda -> BRL."""
    if currency == Currency.BRL:
        return Decimal("1")
    symbol = FX_SYMBOLS.get(currency)
    if symbol is None:
        raise MarketDataUnavailable(f"sem câmbio para {currency}")
    return _cached_quote(symbol, FX_TTL).price


@dataclass(frozen=True)
class PricedQuote:
    quote: Quote
    fx_rate: Decimal
    price_brl: Decimal
    previous_close_brl: Decimal | None


def get_priced_quote(asset: Asset) -> PricedQuote:
    """Cotação convertida para reais — usada em compra, venda e carteira."""
    quote = get_quote(asset)
    fx = get_fx_rate(quote.currency)
    prev = quantize_price(quote.previous_close * fx) if quote.previous_close else None
    return PricedQuote(quote, fx, quantize_price(quote.price * fx), prev)


def search_remote(query: str) -> list[SearchHit]:
    try:
        return _provider.search(query)
    except MarketDataUnavailable:
        return []
