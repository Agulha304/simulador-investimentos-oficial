from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from backend.models import Holding, Transaction
from backend.services import distribution_service as ds
from tests.test_dividends import TODAY, api, cash, event

D = Decimal


def sell(client, h, asset, **body):
    return client.post("/api/trades/sell", headers=h, json={"asset_id": asset.id, **body})


def test_list_assets_by_class_and_country(client, auth_headers, assets):
    def symbols(qs):
        r = client.get(f"/api/assets?{qs}&limit=200", headers=auth_headers)
        assert r.status_code == 200, r.text
        return {a["symbol"] for a in r.json()}

    assert {"HGLG11", "MXRF11", "KNRI11"} <= symbols("asset_class=FII") and "PETR4" not in symbols("asset_class=FII")
    assert {"BTC", "ETH", "SOL"} <= symbols("asset_class=CRYPTO")
    assert {"O", "AMT", "PLD"} <= symbols("asset_class=REIT")
    assert {"BOVA11", "IVVB11"} <= symbols("asset_class=ETF&country=BR")
    assert {"SPY", "QQQ", "VOO"} <= symbols("asset_class=ETF&country=us") and "BOVA11" not in symbols("asset_class=ETF&country=US")
    assert {"AAPL", "MSFT", "NVDA", "GOOGL"} <= symbols("asset_class=STOCK&country=US")
    assert {"PETR4", "VALE3", "ITUB4", "BBAS3"} <= symbols("asset_class=STOCK&country=BR")
    assert client.get("/api/assets?asset_class=XYZ", headers=auth_headers).status_code == 422
    assert len(client.get("/api/assets?limit=5", headers=auth_headers).json()) == 5
    assert client.get("/api/assets").status_code == 401


def test_batch_quotes_skip_unavailable(client, auth_headers, assets):
    ids = ",".join(str(assets[s].id) for s in ("PETR4", "AAPL", "BTC", "MSFT"))     # MSFT: sem cotação no fake
    r = client.get(f"/api/assets/quotes?ids={ids}", headers=auth_headers)
    assert r.status_code == 200
    by = {q["asset_id"]: q for q in r.json()}
    assert set(by) == {assets[s].id for s in ("PETR4", "AAPL", "BTC")}
    assert D(by[assets["BTC"].id]["price_brl"]) == D("520000") and by[assets["BTC"].id]["currency"] == "USD"
    assert client.get("/api/assets/quotes?ids=abc", headers=auth_headers).status_code == 422


def test_crypto_fractional_buy_and_sell_by_amount(client, auth_headers, assets, db):
    btc = assets["BTC"]                                                     # US$ 100.000 × 5,20 = R$ 520.000
    r = client.post("/api/trades/buy", headers=auth_headers, json={"asset_id": btc.id, "amount_brl": "500"})
    assert r.status_code == 201
    bought = D(r.json()["quantity"])
    assert r.json()["quantity"] == "0.000961538461538461"                  # 500/520000, truncado em 18 casas
    assert bought * D("520000") <= D("500")                                 # nunca compra mais do que pagou

    r = sell(client, auth_headers, btc, amount_brl="200")
    assert r.status_code == 201, r.text
    assert D(r.json()["gross_amount_brl"]) == D("200.00") and D(r.json()["quantity"]) == D("200") / D("520000") // D("1e-18") * D("1e-18")
    assert cash(client, auth_headers) == D("99700.00")                      # -500 + 200
    left = D(client.get("/api/portfolio", headers=auth_headers).json()["holdings"][0]["quantity"])
    assert left == bought - D(r.json()["quantity"])

    assert sell(client, auth_headers, btc, amount_brl="500").status_code == 422     # mais do que a posição
    assert sell(client, auth_headers, btc, quantity=str(left)).status_code == 201   # vender tudo por quantidade
    assert client.get("/api/portfolio", headers=auth_headers).json()["holdings"] == []
    assert db.scalar(select(Holding.quantity)) == 0


def test_crypto_dust_and_input_limits(client, auth_headers, assets):
    btc = assets["BTC"]
    r = client.post("/api/trades/buy", headers=auth_headers, json={"asset_id": btc.id, "amount_brl": "0.01"})
    assert r.status_code == 201 and D(r.json()["quantity"]) > 0             # R$ 0,01 já gera fração válida
    assert client.post("/api/trades/buy", headers=auth_headers, json={"asset_id": btc.id, "amount_brl": "0.001"}).status_code == 422
    assert client.post("/api/trades/buy", headers=auth_headers, json={"asset_id": btc.id, "amount_brl": "0"}).status_code == 422
    assert sell(client, auth_headers, btc).status_code == 422                       # nada informado
    assert sell(client, auth_headers, btc, quantity="1", amount_brl="10").status_code == 422   # os dois


def test_sell_by_amount_not_allowed_for_whole_unit_assets(client, auth_headers, assets):
    petr = assets["PETR4"]
    client.post("/api/trades/buy", headers=auth_headers, json={"asset_id": petr.id, "quantity": "10"})
    assert sell(client, auth_headers, petr, amount_brl="100").status_code == 422
    assert sell(client, auth_headers, petr, quantity="2.5").status_code == 422


def test_average_price_with_fractional_crypto(client, auth_headers, assets, _fake_market):
    from backend.services import market_data
    btc = assets["BTC"]
    client.post("/api/trades/buy", headers=auth_headers, json={"asset_id": btc.id, "amount_brl": "1000"})
    _fake_market.prices["BTC-USD"] = ("200000", _fake_market.prices["BTC-USD"][1])        # dobra de preço
    market_data.clear_cache()
    client.post("/api/trades/buy", headers=auth_headers, json={"asset_id": btc.id, "amount_brl": "1000"})
    h = client.get("/api/portfolio", headers=auth_headers).json()["holdings"][0]
    assert D(h["total_cost_brl"]) == D("2000.00")
    # preço médio ≈ custo / quantidade = 2000 / (1000/520000 + 1000/1040000) = 693333,33...
    assert abs(D(h["avg_price_brl"]) - D("693333.3333")) < D("0.001")
    assert D(h["pnl_brl"]) > 0                                                         # preço atual R$ 1.040.000


def test_reit_and_etf_distributions(client, auth_headers, assets, db, _fake_market):
    ex = TODAY - timedelta(days=5)
    for sym in ("O", "SPY", "BOVA11"):
        api(client, auth_headers, "buy", assets[sym], {"O": 10, "SPY": 2, "BOVA11": 3}[sym], TODAY - timedelta(days=40))
    event(_fake_market, "O", ex, "0.27")
    event(_fake_market, "SPY", ex, "1.80")
    event(_fake_market, "BOVA11.SA", ex, "0.50")
    assert ds.discover(db) == 3
    assert ds.pay_due(db, today=ex + timedelta(days=21)) == 2           # REIT e ETF dos EUA (21 dias); BOVA11 só em 30
    assert ds.pay_due(db, today=ex + timedelta(days=30)) == 1

    by = {t.asset_id: t for t in db.scalars(select(Transaction).where(Transaction.type == "DIVIDEND"))}
    o, spy, bova = by[assets["O"].id], by[assets["SPY"].id], by[assets["BOVA11"].id]
    assert (o.gross_amount_brl, o.tax_brl, o.cash_amount_brl) == (D("14.04"), D("4.21"), D("9.83"))     # 10 × 0,27 × 5,20; 30%
    assert (spy.gross_amount_brl, spy.tax_brl, spy.cash_amount_brl) == (D("18.72"), D("5.62"), D("13.10"))
    assert (bova.gross_amount_brl, bova.tax_brl, bova.cash_amount_brl) == (D("1.50"), D("0.00"), D("1.50"))  # ETF BR isento
