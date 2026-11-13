from decimal import Decimal

import pytest

from backend.services import indicators as ind
from backend.services.market_data import Candle

D = Decimal


def ds(*xs):
    return [None if x is None else D(str(x)) for x in xs]


def candle(i, o, h, l, c, v=1000):
    return Candle(1_700_000_000 + i * 86_400, D(str(o)), D(str(h)), D(str(l)), D(str(c)), D(v))


def test_sma_and_ema_by_hand():
    assert ind.sma(ds(1, 2, 3, 4, 5), 3) == ds(None, None, 2, 3, 4)
    # semente = SMA(1,2,3) = 2; alpha = 0,5 -> 3, 4
    assert ind.ema(ds(1, 2, 3, 4, 5), 3) == ds(None, None, 2, 3, 4)
    assert ind.ema(ds(10, 10, 10, 10), 3) == ds(None, None, 10, 10)
    assert ind.ema(ds(1, 2), 5) == [None, None]            # série menor que o período


def test_rsi_by_hand_and_bounds():
    assert ind.rsi(ds(1, 2, 1), 2) == ds(None, None, 50)
    assert ind.rsi(ds(1, 2, 1, 2), 2)[3] == D("75")        # ganho médio 0,75 / perda média 0,25 -> RS 3
    assert ind.rsi(ds(*range(1, 20)), 14)[-1] == 100         # só altas
    vals = [v for v in ind.rsi(ds(5, 6, 5.5, 7, 6, 8, 7, 9, 8.5, 10, 9, 11, 10, 12, 11, 13), 5) if v is not None]
    assert vals and all(0 <= v <= 100 for v in vals)


def test_bollinger():
    b = ind.bollinger(ds(1, 2, 3), 3, D(2))
    assert b["middle"][2] == 2
    assert abs(b["upper"][2] - D("3.63299316")) < D("1e-7") and abs(b["lower"][2] - D("0.36700684")) < D("1e-7")
    flat = ind.bollinger(ds(5, 5, 5, 5), 3)
    assert flat["upper"][3] == flat["lower"][3] == 5


def test_macd_constant_is_zero():
    m = ind.macd(ds(*[10] * 60))
    assert m["macd"][-1] == 0 and m["signal"][-1] == 0 and m["histogram"][-1] == 0
    assert m["macd"][24] is None and m["macd"][25] == 0     # precisa de 26 pontos


def test_atr_stoch_vwap():
    flat = [candle(i, 10, 11, 9, 10) for i in range(30)]       # amplitude constante = 2, sem gaps
    assert ind.atr(flat, 14)[-1] == 2
    up = [candle(i, i, i + 1, i - 1, i + 1) for i in range(1, 30)]  # fecha sempre na máxima
    st = ind.stochastic(up)
    assert st["k"][-1] == 100 and all(v is None or 0 <= v <= 100 for v in st["d"])
    cs = [candle(0, 10, 12, 8, 10, 100), candle(1, 10, 13, 9, 12, 300)]
    # típico1 = 10, típico2 = 34/3 ; VWAP2 = (10*100 + (34/3)*300)/400 = 11
    assert ind.vwap(cs, reset_daily=False)[1] == D("11")
    assert ind.vwap(cs, reset_daily=True)[1] == D("11.33333333")   # reinicia por dia


def test_adx_trend():
    up = [candle(i, 10 + i, 11 + i, 9 + i, 10.5 + i) for i in range(60)]
    r = ind.adx(up, 14)
    assert r["adx"][26] is None and r["adx"][27] is not None
    assert r["adx"][-1] > 50 and r["plus_di"][-1] > r["minus_di"][-1]
    assert all(v is None or 0 <= v <= 100 for v in r["adx"])


def test_parse_and_compute_validation():
    assert ind.parse_spec("SMA:50") == ("sma", (50,))
    assert ind.parse_spec("bbands") == ("bbands", (20, 2))
    for bad in ("foo", "sma:abc", "sma:0", "sma:1:2", "sma:9999"):
        with pytest.raises(ind.IndicatorError):
            ind.parse_spec(bad)
    cs = [candle(i, 10, 11, 9, 10) for i in range(40)]
    out = ind.compute(cs, ["sma:5", "SMA:5", "rsi", "volume"])
    assert list(out) == ["sma:5", "rsi", "volume"] and out["sma:5"]["kind"] == "overlay"
    assert all(len(s) == 40 for v in out.values() for s in v["series"].values())


def test_chart_endpoint(client, auth_headers, assets):
    a = assets["PETR4"]
    r = client.get(f"/api/assets/{a.id}/chart?period=6mo&indicators=sma:20,rsi:14,macd,bbands,volume", headers=auth_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    n = len(d["candles"])
    assert n == 120 and d["currency"] == "BRL"
    assert set(d["indicators"]) == {"sma:20", "rsi:14", "macd", "bbands", "volume"}
    assert all(len(v) == n for i in d["indicators"].values() for v in i["series"].values())
    assert d["indicators"]["sma:20"]["series"]["sma"][18] is None and d["indicators"]["sma:20"]["series"]["sma"][19] is not None
    assert client.get(f"/api/assets/{a.id}/chart?indicators=xyz", headers=auth_headers).status_code == 422
    assert client.get(f"/api/assets/{a.id}/chart?period=2d", headers=auth_headers).status_code == 422


def test_chart_unavailable_returns_503(client, auth_headers, assets, _fake_market):
    del _fake_market.prices["AAPL"]
    assert client.get(f"/api/assets/{assets['AAPL'].id}/chart", headers=auth_headers).status_code == 503


def test_layout_roundtrip_is_per_user(client, auth_headers, assets):
    a = assets["PETR4"].id
    assert client.get(f"/api/assets/{a}/layout", headers=auth_headers).json() == {"indicators": [], "drawings": []}
    body = {"indicators": ["sma:20", "rsi:14"], "drawings": [{"id": "x"}]}
    assert client.put(f"/api/assets/{a}/layout", headers=auth_headers, json=body).json() == body
    assert client.get(f"/api/assets/{a}/layout", headers=auth_headers).json() == body
    assert client.put(f"/api/assets/{a}/layout", headers=auth_headers, json={"indicators": ["lixo"]}).status_code == 422
    other = client.post("/api/auth/register", json={"email": "b@example.com", "name": "B", "password": "segredo123"}).json()
    h2 = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get(f"/api/assets/{a}/layout", headers=h2).json()["indicators"] == []
