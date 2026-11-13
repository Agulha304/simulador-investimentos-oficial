from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from backend.database import SessionLocal, engine
from backend.models import Dividend, DividendEligibility, DividendPayment, EligibilityStatus, Transaction
from backend.services import distribution_service as ds
from backend.services import market_data
from backend.services.distribution_service import TZ

D = Decimal
TODAY = datetime.now(TZ).date()


def at(day: date, hour=12) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=TZ)


def api(client, h, side, asset, qty, when: date | None = None):
    r = client.post(f"/api/trades/{side}", headers=h, json={"asset_id": asset.id, "quantity": str(qty)})
    assert r.status_code == 201, r.text
    if when:
        with engine.begin() as c:
            c.execute(text("UPDATE transactions SET created_at=:t WHERE id=:i"), {"t": at(when), "i": r.json()["id"]})
    return r.json()


def register(client, email):
    r = client.post("/api/auth/register", json={"email": email, "name": "U", "password": "segredo123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def cash(client, h):
    return D(client.get("/api/portfolio", headers=h).json()["cash_balance"])


def event(fake, symbol, ex: date, amount):
    fake.dividends.setdefault(symbol, []).append(market_data.DividendEvent(ex, D(str(amount))))


def counts(db):
    return {t: db.scalar(select(func.count()).select_from(t)) for t in (Dividend, DividendEligibility, DividendPayment)}


def test_eligibility_is_rebuilt_from_transactions_around_ex_date(client, auth_headers, assets, db, _fake_market):
    petr, ex = assets["PETR4"], TODAY - timedelta(days=5)
    api(client, auth_headers, "buy", petr, 10, TODAY - timedelta(days=20))
    api(client, auth_headers, "sell", petr, 4, TODAY - timedelta(days=10))
    api(client, auth_headers, "buy", petr, 6, ex)        # compra NA data EX: não conta
    api(client, auth_headers, "sell", petr, 2, ex)       # venda NA data EX: não retira o direito
    b = register(client, "b@example.com")                 # só comprou na data EX: sem direito
    api(client, b, "buy", petr, 100, ex)
    c = register(client, "c@example.com")                 # vendeu tudo antes da data EX: sem direito
    api(client, c, "buy", petr, 5, TODAY - timedelta(days=30))
    api(client, c, "sell", petr, 5, TODAY - timedelta(days=15))
    event(_fake_market, "PETR4.SA", ex, "0.50")

    assert ds.discover(db) == 1
    e = db.scalar(select(DividendEligibility))
    assert e.quantity == D("6") and e.status == EligibilityStatus.PENDING
    assert e.pay_date == ex + timedelta(days=30)         # ação BR: estimativa de 30 dias
    d = db.get(Dividend, e.dividend_id)
    assert d.pay_date_estimated and d.kind.value == "DIVIDEND" and d.currency.value == "BRL"


def test_event_before_first_purchase_is_ignored(client, auth_headers, assets, db, _fake_market):
    petr = assets["PETR4"]
    api(client, auth_headers, "buy", petr, 10, TODAY - timedelta(days=10))
    event(_fake_market, "PETR4.SA", TODAY - timedelta(days=60), "1.00")   # antes da compra
    assert ds.discover(db) == 0 and counts(db)[DividendEligibility] == 0


def test_discovery_is_idempotent(client, auth_headers, assets, db, _fake_market):
    petr = assets["PETR4"]
    api(client, auth_headers, "buy", petr, 10, TODAY - timedelta(days=40))
    event(_fake_market, "PETR4.SA", TODAY - timedelta(days=5), "0.50")
    assert [ds.discover(db) for _ in range(3)] == [1, 0, 0]
    assert counts(db) == {Dividend: 1, DividendEligibility: 1, DividendPayment: 0}


def test_payment_credits_cash_once(client, auth_headers, assets, db, _fake_market):
    petr, ex = assets["PETR4"], TODAY - timedelta(days=5)
    api(client, auth_headers, "buy", petr, 6, TODAY - timedelta(days=20))
    event(_fake_market, "PETR4.SA", ex, "0.50")
    ds.discover(db)
    before = cash(client, auth_headers)

    assert ds.pay_due(db, today=ex + timedelta(days=29)) == 0            # ainda não venceu
    assert cash(client, auth_headers) == before
    assert ds.pay_due(db, today=ex + timedelta(days=30)) == 1
    assert ds.pay_due(db, today=ex + timedelta(days=30)) == 0            # reexecução não paga de novo
    assert ds.pay_due(db, today=ex + timedelta(days=90)) == 0
    assert cash(client, auth_headers) == before + D("3.00")              # 6 × 0,50, isento no Brasil

    tx = db.scalar(select(Transaction).where(Transaction.type == "DIVIDEND"))
    assert tx.gross_amount_brl == D("3.00") and tx.tax_brl == 0 and tx.cash_amount_brl == D("3.00")
    assert tx.idempotency_key.startswith("dividend:") and tx.source.value == "DISTRIBUTION_WORKER"
    assert counts(db)[DividendPayment] == 1
    assert db.scalar(select(DividendEligibility.status)) == EligibilityStatus.PAID


def test_us_distribution_converts_fx_and_withholds_30_percent(client, auth_headers, assets, db, _fake_market):
    aapl, ex = assets["AAPL"], TODAY - timedelta(days=5)
    api(client, auth_headers, "buy", aapl, 10, TODAY - timedelta(days=40))
    event(_fake_market, "AAPL", ex, "0.25")
    ds.discover(db)
    before = cash(client, auth_headers)
    assert ds.pay_due(db, today=ex + timedelta(days=21)) == 1            # EUA: estimativa de 21 dias
    tx = db.scalar(select(Transaction).where(Transaction.type == "DIVIDEND"))
    assert (tx.gross_amount_brl, tx.tax_brl, tx.cash_amount_brl) == (D("13.00"), D("3.90"), D("9.10"))
    assert tx.fx_rate == D("5.2") and tx.price_currency.value == "USD"   # 10 × US$ 0,25 × 5,20
    assert cash(client, auth_headers) == before + D("9.10")


def test_fii_rendimento_is_exempt(client, auth_headers, assets, db, _fake_market):
    fii, ex = assets["HGLG11"], TODAY - timedelta(days=5)
    api(client, auth_headers, "buy", fii, 10, TODAY - timedelta(days=40))
    event(_fake_market, "HGLG11.SA", ex, "1.17")
    ds.discover(db)
    assert db.scalar(select(Dividend.kind)).value == "RENDIMENTO"
    assert db.scalar(select(DividendEligibility.pay_date)) == ex + timedelta(days=14)
    assert ds.pay_due(db, today=ex + timedelta(days=14)) == 1
    tx = db.scalar(select(Transaction).where(Transaction.type == "DIVIDEND"))
    assert tx.cash_amount_brl == D("11.70") and tx.tax_brl == 0


def test_two_workers_cannot_pay_twice(client, auth_headers, assets, db, _fake_market):
    petr, ex = assets["PETR4"], TODAY - timedelta(days=60)
    api(client, auth_headers, "buy", petr, 10, TODAY - timedelta(days=90))
    event(_fake_market, "PETR4.SA", ex, "0.50")
    ds.discover(db)
    eid = db.scalar(select(DividendEligibility.id))
    with SessionLocal() as s1, SessionLocal() as s2:
        assert ds.pay_one(s1, eid) is True
        assert ds.pay_one(s2, eid) is False                              # segundo worker enxerga PAID
    assert counts(db)[DividendPayment] == 1


def test_database_constraints_block_duplicates(client, auth_headers, assets, db, _fake_market):
    petr = assets["PETR4"]
    api(client, auth_headers, "buy", petr, 10, TODAY - timedelta(days=40))
    event(_fake_market, "PETR4.SA", TODAY - timedelta(days=5), "0.50")
    ds.discover(db)
    e = db.scalar(select(DividendEligibility))
    db.add(DividendEligibility(portfolio_id=e.portfolio_id, dividend_id=e.dividend_id, quantity=D("1"),
                               pay_date=TODAY, status=EligibilityStatus.PENDING))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    d = db.scalar(select(Dividend))
    db.add(Dividend(asset_id=d.asset_id, kind=d.kind, ex_date=d.ex_date, pay_date=d.pay_date,
                    amount_per_unit=d.amount_per_unit, currency=d.currency))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_data_source_down_is_not_fatal(client, auth_headers, assets, db, _fake_market):
    petr = assets["PETR4"]
    api(client, auth_headers, "buy", petr, 10, TODAY - timedelta(days=40))
    event(_fake_market, "PETR4.SA", TODAY - timedelta(days=5), "0.50")
    _fake_market.dividends_down.add("PETR4.SA")
    assert ds.discover(db) == 0 and counts(db)[Dividend] == 0
    _fake_market.dividends_down.clear()
    market_data.clear_cache()
    assert ds.discover(db) == 1                                          # na próxima rodada recupera


def test_fx_down_postpones_payment(client, auth_headers, assets, db, _fake_market):
    aapl, ex = assets["AAPL"], TODAY - timedelta(days=30)
    api(client, auth_headers, "buy", aapl, 10, TODAY - timedelta(days=60))
    event(_fake_market, "AAPL", ex, "0.25")
    ds.discover(db)
    del _fake_market.prices["USDBRL=X"]
    market_data.clear_cache()
    assert ds.pay_due(db, today=TODAY) == 0
    assert db.scalar(select(DividendEligibility.status)) == EligibilityStatus.PENDING


def test_endpoints_list_and_sync_only_own_portfolio(client, auth_headers, assets, db, _fake_market):
    petr = assets["PETR4"]
    api(client, auth_headers, "buy", petr, 10, TODAY - timedelta(days=90))
    other = register(client, "o@example.com")
    api(client, other, "buy", petr, 10, TODAY - timedelta(days=90))
    event(_fake_market, "PETR4.SA", TODAY - timedelta(days=60), "0.50")     # pagamento estimado: há 30 dias

    r = client.post("/api/portfolio/dividends/sync", headers=auth_headers)
    assert r.status_code == 200 and r.json() == {"new_rights": 2, "paid": 1}   # só a minha carteira foi paga
    items = client.get("/api/portfolio/dividends", headers=auth_headers).json()
    assert len(items) == 1 and items[0]["status"] == "PAID" and items[0]["net_brl"] == "5.00"
    assert items[0]["asset"]["symbol"] == "PETR4" and items[0]["pay_date_estimated"] is True
    assert client.get("/api/portfolio/dividends", headers=other).json()[0]["status"] == "PENDING"
    assert client.post("/api/portfolio/dividends/sync", headers=auth_headers).json() == {"new_rights": 0, "paid": 0}
    assert client.get("/api/portfolio/dividends").status_code == 401


def test_scheduler_registers_distribution_jobs():
    from backend.workers.scheduler import shutdown_scheduler, start_scheduler
    sch = start_scheduler()
    try:
        assert {"distribution_discover", "distribution_pay"} <= {j.id for j in sch.get_jobs()}
    finally:
        shutdown_scheduler()
