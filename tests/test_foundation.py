from decimal import Decimal

import pytest

from backend.core.money import quantize_money, quantize_quantity, to_decimal
from backend.models import Portfolio, TransactionType
from backend.services import ledger_service


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


def test_register_creates_portfolio_with_initial_balance(client, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers).json()
    assert me["email"] == "ana@example.com"

    p = client.get("/api/portfolio", headers=auth_headers).json()
    assert p["cash_balance"] == "100000.00"          # Decimal serializado como string
    assert p["total_equity_brl"] == "100000.00"
    assert p["pnl_brl"] == "0.00"
    assert p["holdings"] == []

    txs = client.get("/api/portfolio/transactions", headers=auth_headers).json()
    assert len(txs) == 1
    assert txs[0]["type"] == "DEPOSIT" and txs[0]["source"] == "SYSTEM"
    assert txs[0]["cash_balance_after"] == "100000.00"


def test_duplicate_email_and_login(client, auth_headers):
    r = client.post("/api/auth/register", json={"email": "ANA@example.com", "name": "X", "password": "segredo123"})
    assert r.status_code == 409
    assert client.post("/api/auth/login", json={"email": "ana@example.com", "password": "errada123"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "Ana@Example.com", "password": "segredo123"})
    assert r.status_code == 200 and r.json()["access_token"]


def test_requires_auth(client):
    assert client.get("/api/portfolio").status_code == 401
    assert client.get("/api/portfolio", headers={"Authorization": "Bearer lixo"}).status_code == 401


def test_ledger_idempotency_and_overdraft(client, auth_headers, db):
    pid = db.query(Portfolio.id).scalar()
    with pytest.raises(ledger_service.DuplicateTransactionError):
        ledger_service.deposit(db, pid, Decimal("1"), idempotency_key=f"initial-deposit:portfolio:{pid}")
    db.rollback()

    with pytest.raises(ledger_service.InsufficientFundsError):
        ledger_service.record(db, pid, ledger_service.CashMovement(
            type=TransactionType.WITHDRAWAL, gross_amount_brl=Decimal("100000.01"),
            cash_amount_brl=Decimal("-100000.01")))
    db.rollback()
    assert db.get(Portfolio, pid).cash_balance == Decimal("100000.00")


def test_money_helpers():
    assert to_decimal(0.1) + to_decimal(0.2) == Decimal("0.3")
    assert quantize_money(Decimal("2.345")) == Decimal("2.34")   # half-even
    assert quantize_quantity(Decimal("500") / Decimal("500000")) == Decimal("0.001")


# ------------------------------------------------------------------ configuração para produção

def test_database_url_gets_the_psycopg_driver():
    from backend.config import Settings
    assert Settings(database_url="postgres://u:p@db.example.com/app").database_url == "postgresql+psycopg://u:p@db.example.com/app"
    assert Settings(database_url="postgresql://u:p@db.example.com/app?sslmode=require").database_url == \
        "postgresql+psycopg://u:p@db.example.com/app?sslmode=require"
    ready = "postgresql+psycopg://u:p@h/db"
    assert Settings(database_url=ready).database_url == ready


def test_production_refuses_weak_configuration():
    from backend.config import Settings
    good = dict(environment="production", jwt_secret="x" * 40, database_url="postgresql://u:p@db.example.com/app")
    Settings(**good).check_production()                                           # configuração boa passa
    for bad in ({"jwt_secret": "dev-secret-change-me"}, {"jwt_secret": "curto"}, {"jwt_secret": ""},
                {"database_url": "postgresql://u:p@localhost/app"}):
        with pytest.raises(RuntimeError):
            Settings(**{**good, **bad}).check_production()
    Settings(environment="development", jwt_secret="dev-secret-change-me").check_production()   # dev não é barrado
