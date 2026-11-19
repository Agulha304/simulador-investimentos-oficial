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
        conn.execute(text("TRUNCATE ledger_entries, budget_items, recurring_item_versions, recurring_items, sim_months, budget_categories, finance_accounts, lesson_progress, portfolio_snapshots, financial_events, fixed_income_investments, fixed_income_products, index_rates, dividend_payments, dividend_eligibilities, dividends, chart_layouts, transactions, holdings, portfolios, assets, users RESTART IDENTITY CASCADE"))


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


# ---------------------------------------------------- índices e Tesouro falsos (sem rede)
from datetime import timedelta  # noqa: E402

from backend.core import calendar_br  # noqa: E402
from backend.core.dates import today_br  # noqa: E402
from backend.models import IndexName  # noqa: E402
from backend.services import index_data, treasury_data  # noqa: E402


class FakeIndexProvider:
    """CDI e Selic a 0,05% ao dia útil (~13,4% a.a.); IPCA e IGP-M a 0,5% ao mês."""
    fail = False

    def fetch(self, name, start, end):
        if self.fail:
            raise index_data.IndexDataUnavailable("fora do ar")
        start = max(start, end - timedelta(days=400))
        if name in (IndexName.CDI, IndexName.SELIC):
            return [(d, Decimal("0.05")) for d in calendar_br.iter_business_days(start - timedelta(days=1), end)]
        out, m = [], start.replace(day=1)
        while m <= end:
            out.append((m, Decimal("0.5")))
            m = (m + timedelta(days=32)).replace(day=1)
        return out


class FakeTreasuryProvider:
    def __init__(self):
        self.drop: set[str] = set()

    def fetch_latest(self):
        t = today_br()
        mk = lambda name, years, buy, sell, pu_b, pu_s: treasury_data.TreasuryQuote(   # noqa: E731
            name, calendar_br.add_months(t, 12 * years), t, Decimal(buy), Decimal(sell), Decimal(pu_b), Decimal(pu_s))
        quotes = [
            mk("Tesouro Prefixado", 3, "14.65", "14.77", "749.29", "747.23"),
            mk("Tesouro IPCA+", 5, "7.42", "7.54", "3998.55", "3986.20"),
            mk("Tesouro Selic", 4, "0.11", "0.12", "20201.00", "20181.99"),
            mk("Tesouro IPCA+ com Juros Semestrais", 11, "7.63", "7.75", "4389.42", "4351.48"),
            mk("Tesouro Prefixado com Juros Semestrais", 6, "15.20", "15.32", "845.05", "840.75"),
        ]
        return [q for q in quotes if q.type_name not in self.drop]


@pytest.fixture(autouse=True)
def _fake_fixed_income_sources():
    idx_provider, td_provider = FakeIndexProvider(), FakeTreasuryProvider()
    index_data.set_provider(idx_provider)
    treasury_data.set_provider(td_provider)
    from backend.workers import fixed_income_worker
    fixed_income_worker._last_sync = 0.0
    yield idx_provider, td_provider


# ---------------------------------------------------- mídia das aulas isolada (sem vídeos reais nos testes)
@pytest.fixture(autouse=True)
def _empty_media_dir(tmp_path, monkeypatch):
    from backend.services import video_service
    monkeypatch.setattr(video_service, "media_dir", lambda: tmp_path / "media_vazia")
