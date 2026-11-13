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
        conn.execute(text("TRUNCATE transactions, holdings, portfolios, assets, users RESTART IDENTITY CASCADE"))


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
