from decimal import Decimal

from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import Holding, Transaction
from backend.services import market_data, risk_service

D = Decimal


def buy(client, h, asset, qty):
    r = client.post("/api/trades/buy", headers=h, json={"asset_id": asset.id, "quantity": str(qty)})
    assert r.status_code == 201, r.text


def set_risk(client, h, asset, **levels):
    return client.put(f"/api/trades/risk/{asset.id}", headers=h, json=levels)


def reprice(fake, key, price):
    fake.prices[key] = (str(price), fake.prices[key][1])
    market_data.clear_cache()


def cash(client, h):
    return D(client.get("/api/portfolio", headers=h).json()["cash_balance"])


def sells(client, h):
    return [t for t in client.get("/api/portfolio/transactions", headers=h).json() if t["type"] == "SELL"]


def test_level_validation(client, auth_headers, assets):
    petr = assets["PETR4"]                                                     # cotação R$ 40
    assert set_risk(client, auth_headers, petr, stop_loss="35").status_code == 422   # sem posição
    buy(client, auth_headers, petr, 10)
    assert set_risk(client, auth_headers, petr, stop_loss="41").status_code == 422   # stop acima do preço
    assert set_risk(client, auth_headers, petr, take_profit="39").status_code == 422  # take abaixo do preço
    assert set_risk(client, auth_headers, petr, stop_loss="30", take_profit="30").status_code == 422
    assert set_risk(client, auth_headers, petr, stop_loss="-1").status_code == 422
    r = set_risk(client, auth_headers, petr, stop_loss="35", take_profit="50")
    assert r.status_code == 200 and D(r.json()["stop_loss"]) == 35 and r.json()["currency"] == "BRL"
    h = client.get("/api/portfolio", headers=auth_headers).json()["holdings"][0]
    assert D(h["stop_loss"]) == 35 and D(h["take_profit"]) == 50
    r = set_risk(client, auth_headers, petr)                                   # remove os dois
    assert r.status_code == 200 and r.json()["stop_loss"] is None


def test_nothing_happens_inside_the_range(client, auth_headers, assets, db, _fake_market):
    petr = assets["PETR4"]
    buy(client, auth_headers, petr, 10)
    set_risk(client, auth_headers, petr, stop_loss="35", take_profit="50")
    reprice(_fake_market, "PETR4.SA", 36)
    assert risk_service.check_all(db) == 0
    assert D(client.get("/api/portfolio", headers=auth_headers).json()["holdings"][0]["quantity"]) == 10


def test_stop_loss_sells_everything_once(client, auth_headers, assets, db, _fake_market):
    petr = assets["PETR4"]
    buy(client, auth_headers, petr, 10)                                        # custo R$ 400
    set_risk(client, auth_headers, petr, stop_loss="35", take_profit="50")
    reprice(_fake_market, "PETR4.SA", 34)

    assert risk_service.check_all(db) == 1
    assert risk_service.check_all(db) == 0                                     # segunda rodada: nada a fazer
    assert risk_service.check_all(db) == 0
    assert cash(client, auth_headers) == D("99940.00")                         # 100000 - 400 + 340
    s = sells(client, auth_headers)
    assert len(s) == 1 and s[0]["source"] == "STOP_LOSS" and D(s[0]["realized_pnl_brl"]) == D("-60.00")
    assert "Stop Loss" in s[0]["note"]
    assert client.get("/api/portfolio", headers=auth_headers).json()["holdings"] == []
    h = db.scalar(select(Holding)); db.refresh(h)
    assert h.stop_loss is None and h.take_profit is None and h.quantity == 0   # níveis apagados


def test_take_profit(client, auth_headers, assets, db, _fake_market):
    petr = assets["PETR4"]
    buy(client, auth_headers, petr, 10)
    set_risk(client, auth_headers, petr, take_profit="50")
    reprice(_fake_market, "PETR4.SA", 55)
    assert risk_service.check_all(db) == 1
    assert cash(client, auth_headers) == D("100150.00")                        # lucro 10 * (55 - 40)
    assert sells(client, auth_headers)[0]["source"] == "TAKE_PROFIT"


def test_levels_use_asset_currency_and_convert_proceeds(client, auth_headers, assets, db, _fake_market):
    aapl = assets["AAPL"]                                                      # US$ 300, câmbio 5,20
    buy(client, auth_headers, aapl, 2)                                         # R$ 3.120
    assert set_risk(client, auth_headers, aapl, stop_loss="290", take_profit="400").status_code == 200
    reprice(_fake_market, "AAPL", 295)
    assert risk_service.check_all(db) == 0                                     # 295 > 290
    reprice(_fake_market, "AAPL", 289)
    assert risk_service.check_all(db) == 1
    assert cash(client, auth_headers) == D("99885.60")                         # 100000 - 3120 + 2*289*5,2


def test_second_worker_and_stale_read_do_not_double_sell(client, auth_headers, assets, _fake_market):
    petr = assets["PETR4"]
    buy(client, auth_headers, petr, 10)
    set_risk(client, auth_headers, petr, stop_loss="35")
    reprice(_fake_market, "PETR4.SA", 30)
    with SessionLocal() as s1, SessionLocal() as s2:
        hid = s1.scalar(select(Holding.id))
        assert risk_service._execute(s1, hid, D("30")) is not None
        assert risk_service._execute(s2, hid, D("30")) is None                 # já vendido: não repete
    assert len(sells(client, auth_headers)) == 1


def test_user_changing_levels_during_check_wins(client, auth_headers, assets, _fake_market):
    petr = assets["PETR4"]
    buy(client, auth_headers, petr, 10)
    set_risk(client, auth_headers, petr, stop_loss="35")
    reprice(_fake_market, "PETR4.SA", 34)
    with SessionLocal() as db:
        hid = db.scalar(select(Holding.id))
    set_risk(client, auth_headers, petr, take_profit="60")                     # usuário remove o stop depois da leitura do worker...
    with SessionLocal() as db:
        # ...mas a revalidação sob lock enxerga o estado novo (o worker teria lido stop=35 antes)
        assert risk_service._execute(db, hid, D("34")) is None
    assert sells(client, auth_headers) == []


def test_manual_full_sell_clears_levels_and_rebuy_can_trigger_again(client, auth_headers, assets, db, _fake_market):
    petr = assets["PETR4"]
    buy(client, auth_headers, petr, 10)
    set_risk(client, auth_headers, petr, stop_loss="35")
    reprice(_fake_market, "PETR4.SA", 34)
    assert risk_service.check_all(db) == 1                                     # 1º disparo

    reprice(_fake_market, "PETR4.SA", 40)
    buy(client, auth_headers, petr, 5)
    assert set_risk(client, auth_headers, petr, stop_loss="38").status_code == 200
    reprice(_fake_market, "PETR4.SA", 37)
    assert risk_service.check_all(db) == 1                                     # 2º disparo, chave nova
    assert [t["source"] for t in sells(client, auth_headers)] == ["STOP_LOSS", "STOP_LOSS"]

    buy(client, auth_headers, petr, 3)
    set_risk(client, auth_headers, petr, stop_loss="30")
    r = client.post("/api/trades/sell", headers=auth_headers, json={"asset_id": petr.id, "quantity": "3"})
    assert r.status_code == 201
    h = db.scalar(select(Holding)); db.refresh(h)
    assert h.stop_loss is None                                                 # venda manual total também limpa


def test_partial_sell_keeps_levels(client, auth_headers, assets, db):
    petr = assets["PETR4"]
    buy(client, auth_headers, petr, 10)
    set_risk(client, auth_headers, petr, stop_loss="35", take_profit="50")
    client.post("/api/trades/sell", headers=auth_headers, json={"asset_id": petr.id, "quantity": "4"})
    h = db.scalar(select(Holding)); db.refresh(h)
    assert h.quantity == 6 and h.stop_loss == 35 and h.take_profit == 50


def test_market_down_postpones_without_crashing(client, auth_headers, assets, db, _fake_market):
    petr = assets["PETR4"]
    buy(client, auth_headers, petr, 10)
    set_risk(client, auth_headers, petr, stop_loss="35")
    del _fake_market.prices["PETR4.SA"]
    market_data.clear_cache()
    assert risk_service.check_all(db) == 0
    assert db.scalar(select(Transaction.id).where(Transaction.type == "SELL")) is None


def test_scheduler_registers_risk_job():
    from backend.workers.scheduler import shutdown_scheduler, start_scheduler
    sch = start_scheduler()
    try:
        assert "stop_loss_take_profit" in [j.id for j in sch.get_jobs()]
    finally:
        shutdown_scheduler()
