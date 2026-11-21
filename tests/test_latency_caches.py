"""Cache de cotações (single-flight, falha negativa, stale-while-revalidate), cache de índices e campos de idade da cotação."""
import threading
import time
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.models import Asset, Currency, IndexName, IndexRate
from backend.services import index_data, market_data

SYM = "AAPL"


class CountingProvider:
    def __init__(self, delay=0.0, fail=False):
        self.calls, self.delay, self.fail, self.price = 0, delay, fail, "300"
        self.lock = threading.Lock()

    def get_quote(self, sym):
        with self.lock:
            self.calls += 1
        time.sleep(self.delay)
        if self.fail:
            raise market_data.MarketDataUnavailable(sym)
        return market_data.Quote(Decimal(self.price), Currency.USD, datetime.now(UTC), Decimal("290"))

    def get_history(self, *a): raise market_data.MarketDataUnavailable("x")
    def get_dividends(self, *a): return []
    def search(self, q): return []


@pytest.fixture
def prov():
    p = CountingProvider()
    market_data.set_provider(p)
    return p


def test_single_flight_concurrent_requests_share_one_fetch(prov):
    prov.delay = 0.3
    out = []
    ts = [threading.Thread(target=lambda: out.append(market_data._cached_quote(SYM, 60))) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert prov.calls == 1 and len(out) == 8 and all(q.price == Decimal("300") for q in out)


def test_failure_is_remembered_so_next_requests_answer_immediately(prov):
    prov.fail = True
    with pytest.raises(market_data.MarketDataUnavailable):
        market_data._cached_quote(SYM, 60)
    t0 = time.perf_counter()
    for _ in range(5):
        with pytest.raises(market_data.MarketDataUnavailable):
            market_data._cached_quote(SYM, 60)
    assert prov.calls == 1 and time.perf_counter() - t0 < 0.2


def test_stale_is_only_served_for_display_and_refreshes_in_background(prov):
    market_data._cached_quote(SYM, 60)
    q, wall = market_data._cache[SYM][1], market_data._cache[SYM][2]
    market_data._cache[SYM] = (time.monotonic() - 120, q, wall)               # passou do TTL de 60s
    prov.price = "310"
    shown = market_data._cached_quote_ex(SYM, 60, allow_stale=True)            # exibição: responde já, marcada como stale
    assert shown.stale is True and shown.quote.price == Decimal("300")
    for _ in range(50):                                                        # a atualização acontece em segundo plano
        if market_data._cache[SYM][1].price == Decimal("310"):
            break
        time.sleep(0.05)
    assert market_data._cache[SYM][1].price == Decimal("310")


def test_trading_path_never_gets_stale_price(prov):
    market_data._cached_quote(SYM, 60)
    q, wall = market_data._cache[SYM][1], market_data._cache[SYM][2]
    market_data._cache[SYM] = (time.monotonic() - 120, q, wall)
    prov.price = "320"
    fresh = market_data._cached_quote_ex(SYM, 60, allow_stale=False)           # negociação: espera o preço novo
    assert fresh.stale is False and fresh.quote.price == Decimal("320")


def test_source_down_falls_back_to_cached_quote_marked_stale(prov):
    market_data._cached_quote(SYM, 60)
    q, wall = market_data._cache[SYM][1], market_data._cache[SYM][2]
    market_data._cache[SYM] = (time.monotonic() - 120, q, wall)
    prov.fail = True
    got = market_data._cached_quote_ex(SYM, 60, allow_stale=False)
    assert got.stale is True and got.quote.price == Decimal("300") and got.fetched_at == wall


def test_portfolio_exposes_quote_age(client, auth_headers, db):
    a = db.scalar(select(Asset).where(Asset.symbol == "PETR4"))
    r = client.post("/api/trades/buy", headers=auth_headers, json={"asset_id": a.id, "quantity": "10"})
    assert r.status_code == 201, r.text
    h = client.get("/api/portfolio", headers=auth_headers).json()["holdings"][0]
    assert h["quote_fetched_at"] is not None and h["quote_stale"] is False
    q = client.get(f"/api/assets/{a.id}/quote", headers=auth_headers).json()
    assert q["fetched_at"] is not None and q["stale"] is False


def test_index_cache_reflects_new_rates_immediately(db):
    before = index_data.load(db)
    assert date(2026, 1, 2) not in before.daily.get(IndexName.CDI, {})
    db.add(IndexRate(index_name=IndexName.CDI, ref_date=date.today(), value=Decimal("0.0500")))
    db.commit()
    after = index_data.load(db)                                                # a impressão digital mudou: recarrega
    assert after.daily[IndexName.CDI][date.today()] == Decimal("0.0500")
    after.daily[IndexName.CDI].clear()                                         # mexer na cópia não contamina o cache
    assert index_data.load(db).daily[IndexName.CDI][date.today()] == Decimal("0.0500")
