"""Camada ISOLADA de dados de mercado. Nenhum outro módulo conhece o Yahoo.

Para trocar de fonte, implemente `MarketDataProvider` e chame `set_provider`.
Todos os valores saem como Decimal (via `to_decimal`, nunca float direto).
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Protocol

import httpx

from backend.core.clock import get_clock
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


@dataclass(frozen=True)
class Candle:
    time: int                         # unix seconds (UTC)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class DividendEvent:
    ex_date: date
    amount: Decimal                   # por unidade, na moeda do ativo


# período -> (range, interval) na fonte
HISTORY_RANGES: dict[str, tuple[str, str]] = {
    "1d": ("1d", "5m"), "5d": ("5d", "15m"), "1mo": ("1mo", "1d"), "6mo": ("6mo", "1d"),
    "1y": ("1y", "1d"), "5y": ("5y", "1wk"), "max": ("max", "1mo"),
}
INTRADAY_RANGES = {"1d", "5d"}


class MarketDataProvider(Protocol):
    def get_quote(self, provider_symbol: str) -> Quote: ...
    def get_history(self, provider_symbol: str, period: str) -> list[Candle]: ...
    def get_dividends(self, provider_symbol: str) -> list[DividendEvent]: ...
    def search(self, query: str) -> list[SearchHit]: ...


class YahooProvider:
    CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"
    HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}

    RATE_LIMIT_COOLDOWN = 20.0         # s sem chamar a fonte depois de um 429 (não martela quem já nos limitou)
    MAX_CONCURRENCY = 6                # chamadas simultâneas à fonte, somando todas as threads

    def __init__(self) -> None:
        # conexões reutilizadas (keep-alive) e timeouts curtos: connect 3s, resposta 6s
        self._client = httpx.Client(headers=self.HEADERS, timeout=httpx.Timeout(6.0, connect=3.0),
                                    limits=httpx.Limits(max_connections=12, max_keepalive_connections=8))
        self._slots = threading.BoundedSemaphore(self.MAX_CONCURRENCY)
        self._cooldown_until = 0.0

    def _get(self, url: str, params: dict) -> dict:
        if time.monotonic() < self._cooldown_until:
            raise MarketDataUnavailable("fonte em pausa após limite de requisições (429)")
        last: Exception | None = None
        with self._slots:
            for attempt in range(2):
                try:
                    r = self._client.get(url, params=params)
                    if r.status_code == 429:
                        self._cooldown_until = time.monotonic() + self.RATE_LIMIT_COOLDOWN
                        raise MarketDataUnavailable("limite de requisições (429)")
                    r.raise_for_status()
                    return r.json()
                except MarketDataUnavailable:
                    raise
                except (httpx.HTTPError, ValueError) as exc:
                    last = exc
                    if attempt == 0:
                        time.sleep(0.25)
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

    def get_history(self, provider_symbol: str, period: str) -> list[Candle]:
        rng, interval = HISTORY_RANGES[period]
        data = self._get(self.CHART.format(symbol=provider_symbol), {"range": rng, "interval": interval})
        try:
            result = data["chart"]["result"][0]
            stamps = result["timestamp"]
            q = result["indicators"]["quote"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise MarketDataUnavailable(f"sem histórico para {provider_symbol}") from exc
        candles = []
        for i, ts in enumerate(stamps):
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            if None in (o, h, l, c):
                continue
            v = q["volume"][i] or 0
            # a fonte devolve floats com ruído binário (45.299999): 4 casas, ou 8 para preços < 1 (cripto barata)
            prec = Decimal("0.0001") if to_decimal(c) >= 1 else Decimal("0.00000001")
            candles.append(Candle(int(ts), *(to_decimal(x).quantize(prec) for x in (o, h, l, c)), to_decimal(v)))
        if not candles:
            raise MarketDataUnavailable(f"histórico vazio para {provider_symbol}")
        return candles

    def get_dividends(self, provider_symbol: str) -> list[DividendEvent]:
        """Distribuições dos últimos 5 anos. A fonte informa a data EX e o valor por unidade."""
        data = self._get(self.CHART.format(symbol=provider_symbol),
                         {"range": "5y", "interval": "1mo", "events": "div"})
        try:
            result = data["chart"]["result"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise MarketDataUnavailable(f"sem dividendos para {provider_symbol}") from exc
        events = (result.get("events") or {}).get("dividends") or {}
        out = []
        for ev in events.values():
            amount = to_decimal(ev["amount"]).quantize(Decimal("0.000001"))
            if amount > 0:
                out.append(DividendEvent(datetime.fromtimestamp(ev["date"], UTC).date(), amount))
        return sorted(out, key=lambda e: e.ex_date)

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
# sym -> (monotônico, Quote, hora de relógio em que foi buscada)
_cache: dict[str, tuple[float, Quote, datetime]] = {}
_lock = threading.Lock()
_inflight: dict[str, threading.Lock] = {}          # single-flight: uma busca por símbolo de cada vez
_failed: dict[str, float] = {}                     # sym -> quando falhou (cache negativo)
_refreshing: set[str] = set()
_bg = ThreadPoolExecutor(max_workers=3, thread_name_prefix="quote-refresh")
QUOTE_TTL = 60.0
FX_TTL = 300.0
NEGATIVE_TTL = 15.0       # após falhar, não tenta de novo por N s (as requisições seguintes respondem na hora)
STALE_MAX = 6 * 3600.0    # cotação "velha" só é servida (marcada como stale) em telas de EXIBIÇÃO, nunca em negociação
FX_SYMBOLS = {Currency.USD: "USDBRL=X"}


def set_provider(p: MarketDataProvider) -> None:
    global _provider
    _provider = p
    clear_cache()


def clear_cache() -> None:
    with _lock:
        _cache.clear()
        _hist_cache.clear()
        _div_cache.clear()
        _failed.clear()
        _refreshing.clear()


@dataclass(frozen=True)
class Fetched:
    quote: Quote
    fetched_at: datetime        # quando NÓS buscamos na fonte
    stale: bool                 # True = servida além do TTL enquanto atualiza em segundo plano


def _fetch_into_cache(sym: str, ttl: float) -> Fetched:
    """Busca na fonte com single-flight. Quem chega durante a busca espera a mesma resposta (sem chamada duplicada)."""
    with _lock:
        flight = _inflight.setdefault(sym, threading.Lock())
    with flight:
        now = time.monotonic()
        with _lock:
            hit = _cache.get(sym)
            failed_at = _failed.get(sym)
        if hit and now - hit[0] < ttl:                         # outra thread acabou de buscar
            return Fetched(hit[1], hit[2], False)
        if failed_at is not None and now - failed_at < NEGATIVE_TTL:
            if hit:
                return Fetched(hit[1], hit[2], True)
            raise MarketDataUnavailable(f"{sym} indisponível (falha recente)")
        try:
            quote = _provider.get_quote(sym)
        except MarketDataUnavailable:
            with _lock:
                _failed[sym] = time.monotonic()
                stale = _cache.get(sym)
            if stale:
                log.warning("usando cotação em cache (fonte indisponível): %s", sym)
                return Fetched(stale[1], stale[2], True)
            raise
        wall = datetime.now(UTC)
        with _lock:
            _cache[sym] = (time.monotonic(), quote, wall)
            _failed.pop(sym, None)
        return Fetched(quote, wall, False)


def _refresh_async(sym: str, ttl: float) -> None:
    with _lock:
        if sym in _refreshing:
            return
        _refreshing.add(sym)

    def run():
        try:
            _fetch_into_cache(sym, ttl)
        except MarketDataUnavailable:
            pass
        finally:
            with _lock:
                _refreshing.discard(sym)
    _bg.submit(run)


def _cached_quote_ex(provider_symbol: str, ttl: float, allow_stale: bool = False) -> Fetched:
    now = time.monotonic()
    with _lock:
        hit = _cache.get(provider_symbol)
    if hit and now - hit[0] < ttl:
        return Fetched(hit[1], hit[2], False)
    if allow_stale and hit and now - hit[0] < STALE_MAX:       # exibição: responde já e atualiza em segundo plano
        _refresh_async(provider_symbol, ttl)
        return Fetched(hit[1], hit[2], True)
    return _fetch_into_cache(provider_symbol, ttl)


def _cached_quote(provider_symbol: str, ttl: float) -> Quote:
    return _cached_quote_ex(provider_symbol, ttl).quote


def warm(provider_symbols: list[str]) -> int:
    """Renova em segundo plano as cotações que passaram do TTL (usado pelo worker). Devolve quantas buscou."""
    n = 0
    now = time.monotonic()
    for sym in provider_symbols:
        ttl = FX_TTL if sym in FX_SYMBOLS.values() else QUOTE_TTL
        with _lock:
            hit = _cache.get(sym)
        if hit and now - hit[0] < ttl * 0.6:
            continue
        try:
            _fetch_into_cache(sym, ttl * 0.6)
            n += 1
        except MarketDataUnavailable:
            pass
    return n


def get_quote(asset: Asset, allow_stale: bool = False) -> Quote:
    return get_quote_ex(asset, allow_stale).quote


def get_quote_ex(asset: Asset, allow_stale: bool = False) -> Fetched:
    clock = get_clock()
    if clock is not None:                       # partida: preço da data simulada/histórica
        q = clock.quote_fn(asset)
        return Fetched(q, datetime.now(UTC), False)
    return _cached_quote_ex(asset.provider_symbol, QUOTE_TTL, allow_stale)


def get_fx_rate(currency: Currency, allow_stale: bool = False) -> Decimal:
    """Taxa moeda -> BRL."""
    if currency == Currency.BRL:
        return Decimal("1")
    clock = get_clock()
    if clock is not None and clock.fx_fn is not None:
        return clock.fx_fn(currency)
    symbol = FX_SYMBOLS.get(currency)
    if symbol is None:
        raise MarketDataUnavailable(f"sem câmbio para {currency}")
    return _cached_quote_ex(symbol, FX_TTL, allow_stale).quote.price


@dataclass(frozen=True)
class PricedQuote:
    quote: Quote
    fx_rate: Decimal
    price_brl: Decimal
    previous_close_brl: Decimal | None
    fetched_at: datetime | None = None   # quando a cotação foi buscada na fonte
    stale: bool = False                  # servida além do TTL (a tela deve avisar)


def get_priced_quote(asset: Asset, allow_stale: bool = False) -> PricedQuote:
    """Cotação convertida para reais. `allow_stale=False` (compra, venda, risco) exige cotação dentro do TTL;
    `allow_stale=True` (telas de exibição) aceita a anterior enquanto atualiza em segundo plano."""
    f = get_quote_ex(asset, allow_stale)
    quote = f.quote
    fx = get_fx_rate(quote.currency, allow_stale)
    prev = quantize_price(quote.previous_close * fx) if quote.previous_close else None
    return PricedQuote(quote, fx, quantize_price(quote.price * fx), prev, f.fetched_at, f.stale)


_hist_cache: dict[tuple[str, str], tuple[float, list[Candle]]] = {}


def get_history(asset: Asset, period: str) -> list[Candle]:
    """Candles OHLCV na moeda do ativo. Cache curto (intraday) ou longo (diário+)."""
    if period not in HISTORY_RANGES:
        raise ValueError(f"período inválido: {period}")
    clock = get_clock()
    if clock is not None and clock.history_fn is not None:
        return clock.history_fn(asset, period)
    ttl = 60.0 if period in INTRADAY_RANGES else 900.0
    key, now = (asset.provider_symbol, period), time.monotonic()
    with _lock:
        hit = _hist_cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    try:
        candles = _provider.get_history(asset.provider_symbol, period)
    except MarketDataUnavailable:
        with _lock:
            stale = _hist_cache.get(key)
        if stale:
            log.warning("usando histórico em cache: %s %s", *key)
            return stale[1]
        raise
    with _lock:
        _hist_cache[key] = (now, candles)
    return candles


_div_cache: dict[str, tuple[float, list[DividendEvent]]] = {}


def get_dividends(asset: Asset) -> list[DividendEvent]:
    key, now = asset.provider_symbol, time.monotonic()
    with _lock:
        hit = _div_cache.get(key)
        if hit and now - hit[0] < 3600:
            return hit[1]
    events = _provider.get_dividends(key)          # MarketDataUnavailable sobe: o worker tenta de novo depois
    with _lock:
        _div_cache[key] = (now, events)
    return events


def search_remote(query: str) -> list[SearchHit]:
    try:
        return _provider.search(query)
    except MarketDataUnavailable:
        return []
