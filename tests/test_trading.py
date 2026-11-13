from decimal import Decimal

D = Decimal


def buy(client, h, asset, **kw):
    return client.post("/api/trades/buy", headers=h, json={"asset_id": asset.id, **kw})


def sell(client, h, asset, qty):
    return client.post("/api/trades/sell", headers=h, json={"asset_id": asset.id, "quantity": str(qty)})


def portfolio(client, h):
    return client.get("/api/portfolio", headers=h).json()


def test_catalog_seeded_and_search(client, auth_headers, assets):
    assert {"PETR4", "AAPL", "BTC", "HGLG11", "BOVA11", "SPY", "O"} <= set(assets)
    hits = client.get("/api/assets/search?q=petr", headers=auth_headers).json()
    assert {h["symbol"] for h in hits} >= {"PETR4", "PETR3"}
    assert client.get("/api/assets/search?q=petr").status_code == 401


def test_quote_converts_usd_to_brl(client, auth_headers, assets):
    q = client.get(f"/api/assets/{assets['AAPL'].id}/quote", headers=auth_headers).json()
    assert D(q["price"]) == D("300") and q["currency"] == "USD"
    assert D(q["fx_rate"]) == D("5.2") and D(q["price_brl"]) == D("1560")


def test_buy_foreign_stock_converts_to_brl(client, auth_headers, assets):
    r = buy(client, auth_headers, assets["AAPL"], quantity="2")
    assert r.status_code == 201, r.text
    tx = r.json()
    assert tx["type"] == "BUY" and D(tx["gross_amount_brl"]) == D("3120.00")
    assert D(tx["unit_price"]) == D("300") and tx["price_currency"] == "USD" and D(tx["fx_rate"]) == D("5.2")
    p = portfolio(client, auth_headers)
    assert p["cash_balance"] == "96880.00"
    assert p["holdings"][0]["quantity"] == "2.000000000000000000"
    assert D(p["total_equity_brl"]) == D("100000.00")          # compra a mercado não altera patrimônio


def test_average_price_and_sell_realized_pnl(client, auth_headers, assets, _fake_market):
    petr = assets["PETR4"]
    assert buy(client, auth_headers, petr, quantity="10").status_code == 201      # 10 @ 40 = 400
    _fake_market.prices["PETR4.SA"] = ("60", _fake_market.prices["PETR4.SA"][1])
    from backend.services import market_data
    market_data.clear_cache()
    assert buy(client, auth_headers, petr, quantity="10").status_code == 201      # 10 @ 60 = 600
    h = portfolio(client, auth_headers)["holdings"][0]
    assert D(h["avg_price_brl"]) == D("50") and D(h["total_cost_brl"]) == D("1000.00")
    assert D(h["pnl_brl"]) == D("200.00")                                          # 20 * 60 - 1000

    r = sell(client, auth_headers, petr, 5)
    assert r.status_code == 201
    assert D(r.json()["realized_pnl_brl"]) == D("50.00")                           # 5*60 - 5*50
    h = portfolio(client, auth_headers)["holdings"][0]
    assert D(h["quantity"]) == 15 and D(h["avg_price_brl"]) == D("50")

    assert sell(client, auth_headers, petr, 15).status_code == 201
    assert portfolio(client, auth_headers)["holdings"] == []


def test_crypto_buy_by_amount(client, auth_headers, assets):
    r = buy(client, auth_headers, assets["BTC"], amount_brl="500")
    assert r.status_code == 201, r.text
    qty = D(r.json()["quantity"])
    assert qty == D("500") / D("520000") // D("1e-18") * D("1e-18")                # truncado em 18 casas
    assert D(r.json()["gross_amount_brl"]) == D("500.00")
    assert portfolio(client, auth_headers)["cash_balance"] == "99500.00"


def test_validation_rules(client, auth_headers, assets):
    assert buy(client, auth_headers, assets["PETR4"], quantity="1.5").status_code == 422       # fração em ação
    assert buy(client, auth_headers, assets["PETR4"], amount_brl="100").status_code == 422     # valor em ação
    assert buy(client, auth_headers, assets["PETR4"]).status_code == 422                       # nada informado
    assert buy(client, auth_headers, assets["PETR4"], quantity="1", amount_brl="10").status_code == 422
    r = buy(client, auth_headers, assets["AAPL"], quantity="1000")                             # R$ 1,56 mi
    assert r.status_code == 422 and "saldo insuficiente" in r.json()["detail"]
    assert sell(client, auth_headers, assets["PETR4"], 1).status_code == 422                   # sem posição
    assert portfolio(client, auth_headers)["cash_balance"] == "100000.00"                      # nada mudou


def test_idempotency_key_prevents_double_buy(client, auth_headers, assets):
    hdr = {**auth_headers, "Idempotency-Key": "abc-123"}
    body = {"asset_id": assets["PETR4"].id, "quantity": "5"}
    assert client.post("/api/trades/buy", headers=hdr, json=body).status_code == 201
    assert client.post("/api/trades/buy", headers=hdr, json=body).status_code == 409
    assert portfolio(client, auth_headers)["cash_balance"] == "99800.00"


def test_market_down_does_not_break_portfolio(client, auth_headers, assets, _fake_market):
    buy(client, auth_headers, assets["PETR4"], quantity="10")
    del _fake_market.prices["PETR4.SA"]
    from backend.services import market_data
    market_data.clear_cache()
    p = portfolio(client, auth_headers)
    assert p["holdings"][0]["current_price_brl"] is None and D(p["holdings"][0]["pnl_brl"]) == 0
    assert buy(client, auth_headers, assets["PETR4"], quantity="1").status_code == 422


def test_virtual_deposit(client, auth_headers):
    r = client.post("/api/portfolio/deposit", headers=auth_headers, json={"amount": "250.50"})
    assert r.status_code == 201
    p = portfolio(client, auth_headers)
    assert p["cash_balance"] == "100250.50" and p["total_deposits_brl"] == "100250.50"
    assert client.post("/api/portfolio/deposit", headers=auth_headers, json={"amount": "-5"}).status_code == 422
