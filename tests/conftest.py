"""Testes rodam contra TEST_DATABASE_URL (banco separado), com o schema
criado pelas migrations do Alembic e tabelas limpas a cada teste."""
import os

from backend.config import get_settings

os.environ["DATABASE_URL"] = get_settings().test_database_url
os.environ["SCHEDULER_ENABLED"] = "false"
get_settings.cache_clear()

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from backend.config import ROOT_DIR  # noqa: E402
from backend.database import SessionLocal, engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    cfg = Config(str(ROOT_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _clean_db():
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE dividend_payments, dividend_eligibilities, dividends, chart_layouts, transactions, holdings, portfolios, assets, users RESTART IDENTITY CASCADE"))


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def client():
    from backend.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    r = client.post("/api/auth/register", json={"email": "ana@example.com", "name": "Ana", "password": "segredo123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------- mercado falso
from datetime import UTC, datetime  # noqa: E402
from decimal import Decimal  # noqa: E402

from backend.models import Currency  # noqa: E402
from backend.services import market_data  # noqa: E402


class FakeProvider:
    """Cotações determinísticas: USD/BRL 5,20; AAPL US$ 300; PETR4 R$ 40; BTC US$ 100.000."""
    def __init__(self):
        self.prices = {   # cópia por teste: os testes podem alterar preços
            "USDBRL=X": ("5.20", Currency.BRL), "AAPL": ("300", Currency.USD),
            "PETR4.SA": ("40", Currency.BRL), "BTC-USD": ("100000", Currency.USD),
            "HGLG11.SA": ("160", Currency.BRL), "O": ("55", Currency.USD), "SPY": ("500", Currency.USD),
            "BOVA11.SA": ("130", Currency.BRL),
        }
        self.dividends = {}          # provider_symbol -> [DividendEvent]
        self.dividends_down = set()  # símbolos cuja consulta de dividendos falha

    def get_quote(self, provider_symbol):
        if provider_symbol not in self.prices:
            raise market_data.MarketDataUnavailable(provider_symbol)
        price, cur = self.prices[provider_symbol]
        return market_data.Quote(Decimal(price), cur, datetime.now(UTC), Decimal(price) * Decimal("0.99"))

    def get_history(self, provider_symbol, period):
        if provider_symbol not in self.prices:
            raise market_data.MarketDataUnavailable(provider_symbol)
        base = Decimal(self.prices[provider_symbol][0])
        out = []
        for i in range(120):   # onda determinística
            close = base + Decimal((i % 10) - 5) + Decimal(i) / 10
            out.append(market_data.Candle(1_700_000_000 + i * 86_400, close - 1, close + 2, close - 2, close, Decimal(1000 + i)))
        return out

    def get_dividends(self, provider_symbol):
        if provider_symbol in self.dividends_down:
            raise market_data.MarketDataUnavailable(provider_symbol)
        return list(self.dividends.get(provider_symbol, []))

    def search(self, query):
        return []


@pytest.fixture(autouse=True)
def _fake_market():
    provider = FakeProvider()
    market_data.set_provider(provider)
    yield provider
    market_data.clear_cache()


@pytest.fixture
def assets(client, db):
    from sqlalchemy import select
    from backend.models import Asset
    return {a.symbol: a for a in db.scalars(select(Asset))}
