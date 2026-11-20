"""Motor econômico e de mercado: relações entre indicadores, crises, ativos, reprodutibilidade, simulações longas e integração."""
import math
import statistics as st
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import Asset, EconomicCrisis, EconomyState, SimMonth, SimPrice
from backend.services.engine import crises as cr
from backend.services.engine import markets as mk
from backend.services.engine import regimes as rg
from backend.services.engine import world as wd
from backend.services.engine.params import SimParams
from backend.services.engine.rng import Rng
from tests.conftest import credit
from tests.test_budget import B, close

D = Decimal
P = SimParams()


def run(seed, months, overrides=None, shocks=None, params=P, force=None, start_year=2030):
    """Roda `months` meses; `shocks` (dict) vale em todos os meses; `force` = (mês, Crisis) injeta uma crise."""
    ws = wd.initial_world(overrides)
    out = [ws]
    infos = []
    for i in range(months):
        y, m = divmod(i, 12)
        if force and i == force[0]:
            ws.crises = ws.crises + [force[1].to_dict()]
        ws, info = wd.step(ws, seed, f"{start_year + y:04d}-{m + 1:02d}", params, shocks)
        out.append(ws)
        infos.append(info)
    return out, infos


def forced(kind="FINANCIAL", peak=0.9):
    return cr.Crisis(type=kind, start="2030-01", intensity=0.5, peak=peak, hold=4, triggers={"debt": 1.0})


def mean(xs):
    return sum(xs) / len(xs)


# ------------------------------------------------------------------ relações entre indicadores

def test_supply_shock_on_food_raises_food_prices_and_general_inflation():
    base, _ = run(3, 12)
    shocked, _ = run(3, 12, shocks={"price_pp": {"alimentacao": 1.5}})
    assert shocked[-1].indices["alimentacao"] > base[-1].indices["alimentacao"] * 1.10
    assert shocked[-1].indices["geral"] > base[-1].indices["geral"]
    assert shocked[-1].indices["educacao"] == pytest.approx(base[-1].indices["educacao"], rel=0.03)    # outras categorias quase iguais


def test_high_inflation_pressures_central_bank_to_raise_rates():
    states, _ = run(5, 18, overrides={"inflation": 13.0})
    assert states[-1].macro["policy"] > states[0].macro["policy"] + 2.0
    low, _ = run(5, 18, overrides={"inflation": 1.0})
    assert states[-1].macro["policy"] > low[-1].macro["policy"] + 3.0


def test_high_rates_reduce_credit_and_demand():
    cheap, _ = run(7, 18, overrides={"policy": 7.0, "inflation": 4.0})
    dear, _ = run(7, 18, overrides={"policy": 22.0, "inflation": 4.0}, shocks={"policy": 0.8})
    window = slice(1, 10)                                     # enquanto os juros estão altos (depois o BC corta, com a economia fraca)
    assert mean([s.macro["credit"] for s in dear[window]]) < mean([s.macro["credit"] for s in cheap[window]]) - 8
    assert mean([s.macro["demand"] for s in dear[window]]) < mean([s.macro["demand"] for s in cheap[window]]) - 10
    assert mean([s.macro["business_conf"] for s in dear[window]]) < mean([s.macro["business_conf"] for s in cheap[window]])
    assert dear[-1].macro["policy"] < dear[1].macro["policy"] - 8                             # e o banco central responde cortando


def test_recession_raises_unemployment_and_lowers_demand():
    base, _ = run(11, 24)
    rec, _ = run(11, 24, shocks={"demand": -0.7})
    assert rec[-1].macro["unemployment"] > base[-1].macro["unemployment"] + 2.0
    assert rec[-1].macro["demand"] < base[-1].macro["demand"] - 5
    assert rec[-1].macro["consumer_conf"] < base[-1].macro["consumer_conf"]
    assert rec[-1].macro["default_rate"] > base[-1].macro["default_rate"]                 # inadimplência acompanha


def test_fx_devaluation_pushes_imported_prices_and_inflation():
    base, _ = run(13, 12)
    dev, _ = run(13, 12, shocks={"fx": 4.0})
    assert dev[-1].macro["fx"] > base[-1].macro["fx"] * 1.25
    assert dev[-1].indices["importados"] / base[-1].indices["importados"] > dev[-1].indices["educacao"] / base[-1].indices["educacao"]
    assert dev[-1].indices["geral"] > base[-1].indices["geral"]


def test_currency_crisis_depreciates_the_currency_and_hits_imports():
    base, _ = run(17, 12)
    crisis, _ = run(17, 12, force=(0, forced("CURRENCY")))
    assert crisis[-1].macro["fx"] > base[-1].macro["fx"] * 1.15
    assert crisis[-1].indices["importados"] > base[-1].indices["importados"] * 1.05


def test_supply_crisis_presses_the_affected_categories():
    base, _ = run(19, 10)
    crisis, _ = run(19, 10, force=(0, forced("SUPPLY")))
    assert crisis[-1].macro["commodity"] > base[-1].macro["commodity"]
    for cat in ("combustiveis", "energia", "alimentacao"):
        assert crisis[-1].indices[cat] > base[-1].indices[cat]
    assert crisis[-1].indices["geral"] > base[-1].indices["geral"] * 1.01


def test_liquidity_and_credit_tighten_in_a_financial_crisis():
    base, _ = run(23, 8)
    fin, _ = run(23, 8, force=(0, forced("FINANCIAL")))
    assert fin[-1].macro["liquidity"] < base[-1].macro["liquidity"] - 10
    assert fin[-1].macro["credit"] < base[-1].macro["credit"] - 8


# ------------------------------------------------------------------ crises: propagação, duração e recuperação

def test_crisis_propagates_through_the_economy_without_a_fixed_script():
    base, _ = run(29, 30)
    fin, _ = run(29, 30, force=(0, forced("FINANCIAL", 0.95)))
    # cadeia: liquidez/crédito ↓ → atividade ↓ → desemprego ↑ → confiança ↓ → inadimplência ↑
    assert min(s.macro["gap"] for s in fin) < min(s.macro["gap"] for s in base) - 1.0
    assert max(s.macro["unemployment"] for s in fin) > max(s.macro["unemployment"] for s in base) + 1.5
    assert min(s.macro["consumer_conf"] for s in fin) < min(s.macro["consumer_conf"] for s in base) - 5
    assert max(s.macro["default_rate"] for s in fin) > max(s.macro["default_rate"] for s in base) + 0.8


def test_crisis_lasts_several_months_then_recovers():
    states, infos = run(31, 72, force=(0, forced("FINANCIAL", 0.9)))
    path = next(c for s in states for c in s.crises if c["type"] == "FINANCIAL" and c["ended"])["path"]
    phases = [p["phase"] for p in path]
    assert len(path) >= 6 and phases[0] == "ONSET" and "PEAK" in phases and phases[-1] == "RECOVERY"
    assert phases.index("PEAK") < len([p for p in phases if p != "RECOVERY"]) + 1
    inten = [p["i"] for p in path]
    assert max(inten) >= 0.85 and inten[-1] < 0.1 and inten.index(max(inten)) > 0           # sobe, atinge pico, cai
    # recuperação da economia depois do fim da crise
    end_idx = next(i for i, s in enumerate(states) if any(c["type"] == "FINANCIAL" and c["ended"] for c in s.crises))
    tail = states[min(end_idx + 24, len(states) - 1):]
    assert mean([s.macro["gap"] for s in tail]) > -2.0 and mean([s.macro["unemployment"] for s in tail]) < 12.5
    first_crisis = next(i for i, s in enumerate(states) if s.regime == "CRISIS")
    assert "RECOVERY" in {s.regime for s in states[first_crisis:end_idx + 12]}             # regime de recuperação depois da crise
    assert any(i.regime == "CRISIS" for i in infos)                                          # regime de crise durante


def test_crisis_triggers_depend_on_accumulated_vulnerabilities():
    calm = wd.initial_world().macro
    fragile = {**calm, "household_debt": 85.0, "firm_debt": 110.0, "credit": 85.0, "default_rate": 11.0, "liquidity": 30.0, "gap": -3.0}
    v_calm, v_frag = cr.vulnerabilities(calm, {}), cr.vulnerabilities(fragile, {"bubble": 30.0, "months_neg_gap": 12})
    assert v_frag["debt"] > v_calm["debt"] + 0.8 and v_frag["credit_boom"] > v_calm["credit_boom"] and v_frag["bank"] > v_calm["bank"]
    n_calm = n_frag = 0
    for i in range(1500):
        ref = f"{2030 + i // 12}-{i % 12 + 1:02d}"
        n_calm += cr.maybe_start(calm, {}, [], {}, ref, Rng(101, ref), P) is not None
        n_frag += cr.maybe_start(fragile, {"bubble": 30.0, "months_neg_gap": 12}, [], {}, ref, Rng(101, ref), P) is not None
    assert n_frag > n_calm * 2


def test_localized_crisis_hits_sectors_without_general_recession():
    effects = cr.effects([cr.Crisis(type="HOUSING", start="2030-01", intensity=0.9, peak=0.9, phase="PEAK")])
    assert effects["sector"]["REAL_ESTATE_AGENCY"] < -15 and effects["sector"]["CONSTRUCTION"] < -10
    assert "SUPERMARKET" not in effects["sector"] and effects["demand"] > -0.3          # choque geral pequeno
    assert effects["class_ret"]["FII"] < 0 and effects["house"] < 0 and effects.get("vacancy", 0) > 0


def test_crisis_does_not_always_make_the_player_lose_some_assets_gain():
    eff = cr.effects([forced("CURRENCY", 0.9)])
    assert eff["class_ret"]["CRYPTO"] > 0 and eff["class_ret"]["REIT"] > 0 and eff["class_ret"]["STOCK"] < 0


# ------------------------------------------------------------------ regimes e ativos

def test_market_regimes_have_variable_durations_and_respond_to_stress():
    states, _ = run(37, 1200)
    runs, cur, n = [], states[0].regime, 0
    for s in states[1:]:
        if s.regime == cur:
            n += 1
        else:
            runs.append((cur, n + 1)); cur, n = s.regime, 0
    kinds = {r for r, _ in runs}
    assert {"BULL", "BEAR", "SIDEWAYS", "HIGH_VOL", "LOW_VOL", "RECOVERY", "CRISIS"} <= kinds
    lens = [l for _, l in runs]
    assert len(set(lens)) > 8 and max(lens) > 12 and min(lens) >= 1                         # durações variáveis, não alterna todo mês
    calm, stressed = wd.initial_world().macro, {**wd.initial_world().macro, "gap": -4.0, "consumer_conf": 25.0, "unemployment": 14.0, "liquidity": 30.0}
    assert rg.stress_score(stressed) > rg.stress_score(calm) + 0.4
    bear = {"BEAR": 0, "HIGH_VOL": 0}
    for i in range(3000):
        for name, macro in (("calm", calm), ("stress", stressed)):
            r, _ = rg.step_regime("SIDEWAYS", 5, macro, 0.0, Rng(7, f"{i}"))
            if name == "stress" and r in bear:
                bear[r] += 1
    assert bear["BEAR"] + bear["HIGH_VOL"] > 0


def _asset_paths(seed, months, assets, params=P):
    ws = wd.initial_world()
    price = {a["symbol"]: 100.0 for a in assets}
    rets = {a["symbol"]: [] for a in assets}
    for i in range(months):
        ref = f"{2030 + i // 12}-{i % 12 + 1:02d}"
        ws, info = wd.step(ws, seed, ref, params)
        rv = rg.REGIMES[ws.regime][1]
        for a in assets:
            p = mk.step_price(price[a["symbol"]], a, info.factors, rv, info.crisis_effects["class_ret"], Rng(seed, ref), params.volatility)
            rets[a["symbol"]].append(math.log(p / price[a["symbol"]]))
            price[a["symbol"]] = p
    return rets, price


ASSETS = [{"symbol": "PETR4", "asset_class": "STOCK"}, {"symbol": "VALE3", "asset_class": "STOCK"}, {"symbol": "AAPL", "asset_class": "BDR"},
          {"symbol": "BOVA11", "asset_class": "ETF"}, {"symbol": "HGLG11", "asset_class": "FII"}, {"symbol": "O", "asset_class": "REIT"},
          {"symbol": "BTC", "asset_class": "CRYPTO"}]


def test_asset_classes_have_different_volatilities_and_prices_stay_positive():
    rets, price = _asset_paths(41, 900, ASSETS)
    vol = {k: st.pstdev(v) * math.sqrt(12) for k, v in rets.items()}
    assert vol["BTC"] > vol["PETR4"] > vol["BOVA11"] > vol["HGLG11"]
    assert vol["BTC"] > 0.45 and 0.15 < vol["BOVA11"] < 0.30 and vol["HGLG11"] < 0.18
    assert all(p > 0 and math.isfinite(p) for p in price.values())
    ann = {k: mean(v) * 12 for k, v in rets.items()}
    assert all(-0.05 < a < 0.25 for a in ann.values()), ann                                   # retornos plausíveis


def test_assets_are_correlated_through_common_factors_but_not_identical():
    rets, _ = _asset_paths(43, 900, ASSETS)
    corr = lambda a, b: sum((x - mean(a)) * (y - mean(b)) for x, y in zip(a, b)) / (len(a) * st.pstdev(a) * st.pstdev(b))   # noqa: E731
    assert corr(rets["PETR4"], rets["VALE3"]) > 0.35 and corr(rets["PETR4"], rets["BOVA11"]) > 0.5
    assert corr(rets["PETR4"], rets["VALE3"]) < 0.95 and rets["PETR4"] != rets["VALE3"]
    assert corr(rets["PETR4"], rets["BTC"]) < corr(rets["PETR4"], rets["BOVA11"])


def test_financial_crisis_hits_most_assets_at_once():
    losses = 0
    n = 0
    for seed in range(1, 9):
        ws = wd.initial_world()
        ws.crises = [forced("FINANCIAL", 0.95).to_dict()]
        price = {f"S{i}": 100.0 for i in range(30)}
        start = dict(price)
        for i in range(6):
            ref = f"2030-{i + 1:02d}"
            ws, info = wd.step(ws, seed, ref, P)
            rv = rg.REGIMES[ws.regime][1]
            for sym in price:
                price[sym] = mk.step_price(price[sym], {"symbol": sym, "asset_class": "STOCK"}, info.factors, rv, info.crisis_effects["class_ret"], Rng(seed, ref), 1.0)
        losses += sum(1 for s in price if price[s] < start[s])
        n += len(price)
    assert losses / n > 0.85                                                                 # queda simultânea


def test_rising_rates_hurt_real_estate_funds_more_than_stocks():
    ws = wd.initial_world()
    prev = dict(ws.macro)
    cur = {**prev, "policy": prev["policy"] + 2.0}
    F = {"mkt": 0.0, "mkt_us": 0.0, "rates": 2.0, "infl": 0, "growth": 0, "fx": 0, "comm": 0, "house": 0, "risk": 0}
    fii = mk.step_price(100.0, {"symbol": "X", "asset_class": "FII"}, F, 1.0, {}, Rng(1, "a"), 0.0)
    acao = mk.step_price(100.0, {"symbol": "X", "asset_class": "STOCK"}, F, 1.0, {}, Rng(1, "a"), 0.0)
    assert fii < 100.0 and fii / 100 < acao / 100 + 0.01 and cur["policy"] > prev["policy"]


def test_prices_never_negative_even_with_extreme_shocks():
    F = {"mkt": -80.0, "mkt_us": -80.0, "rates": 30, "infl": 20, "growth": -9, "fx": 0, "comm": 0, "house": -4, "risk": -55}
    for cls in mk.CLASSES:
        p = mk.step_price(100.0, {"symbol": "Z", "asset_class": cls}, F, 3.0, {cls: -40.0}, Rng(1, "x"), 3.0)
        assert 0 < p < 100.0


# ------------------------------------------------------------------ reprodutibilidade, parâmetros e simulações longas

def test_same_seed_reproduces_exactly_and_other_seed_diverges():
    a, _ = run(51, 60)
    b, _ = run(51, 60)
    c, _ = run(52, 60)
    assert [s.to_dict() for s in a] == [s.to_dict() for s in b]
    assert [s.macro["inflation"] for s in a] != [s.macro["inflation"] for s in c]
    assert Rng(1, "2030-01").z("x") == Rng(1, "2030-01").z("x") != Rng(2, "2030-01").z("x")


def test_parameters_change_the_simulation_without_touching_the_engine():
    none, i0 = run(61, 600, params=SimParams(crisis_frequency=0.0))
    more, i1 = run(61, 600, params=SimParams(crisis_frequency=3.0))
    assert sum(len(i.started) for i in i0) == 0 and sum(len(i.started) for i in i1) > 8
    lo, _ = _asset_paths(63, 300, ASSETS[:1], SimParams(volatility=0.5))
    hi, _ = _asset_paths(63, 300, ASSETS[:1], SimParams(volatility=2.0))
    assert st.pstdev(hi["PETR4"]) > 1.6 * st.pstdev(lo["PETR4"])
    with pytest.raises(ValueError):
        SimParams.from_dict({"crisis_frequency": 99})


@pytest.mark.parametrize("seed", [71, 72, 73])
def test_long_simulation_stays_sane_for_five_thousand_months(seed):
    states, infos = run(seed, 5000)
    inf = [s.macro["inflation"] for s in states]
    assert min(inf) > -3.5 and max(inf) < 40.5, "inflação não pode explodir"
    for k, (lo, hi) in {"unemployment": (3, 25), "policy": (2, 30), "credit": (5, 95), "consumer_conf": (0, 100), "fx": (2, 60),
                        "liquidity": (5, 100), "demand": (50, 150), "gap": (-9, 6), "default_rate": (0.5, 30)}.items():
        v = [s.macro[k] for s in states]
        assert min(v) >= lo - 1e-6 and max(v) <= hi + 1e-6 and all(math.isfinite(x) for x in v), k
    gap = [s.macro["gap"] for s in states]
    assert sum(1 for g in gap if g < -3.0) / len(gap) < 0.20, "não pode ficar em recessão permanente"
    assert sum(1 for s in states if s.macro["growth"] > 3.0) / len(states) > 0.20, "precisa haver períodos de crescimento"
    years = 5000 / 12
    started = [c for i in infos for c in i.started]
    assert 0.05 < len(started) / years < 0.40, "crises nem raras demais nem frequentes demais"
    share_crisis = sum(1 for s in states if s.regime == "CRISIS") / len(states)
    assert 0.03 < share_crisis < 0.25
    assert 0.05 < sum(1 for s in states if s.regime == "RECOVERY") / len(states) < 0.30
    assert 5.5 < mean([s.macro["unemployment"] for s in states]) < 12 and 1.5 < mean(inf) < 9
    quiet = max(len(list(g)) for k, g in __import__("itertools").groupby([bool(i.started) or any(not c["ended"] for c in s.crises) for i, s in zip(infos, states[1:])]) if not k)
    assert quiet >= 36, "deve haver longos períodos sem crise"
    eq = [s.class_index["equity"] for s in states]
    ann = (eq[-1] / eq[0]) ** (12 / 5000) - 1
    assert 0.0 < ann < 0.16, ann                                                             # não tende a zero nem explode sem motivo
    assert all(math.isfinite(x) and x > 0 for x in eq)


def test_asset_series_do_not_collapse_or_blow_up_over_long_horizons():
    rets, price = _asset_paths(81, 1200, ASSETS)
    for sym, p in price.items():
        assert 1e-3 < p / 100 < 1e9, (sym, p)             # 100 anos: nem zero nem infinito (retorno nominal composto, com muita dispersão)


# ------------------------------------------------------------------ integração com banco (partida de vida completa)

def _mk_world(client, auth_headers, seed=5, sim=None, scenario="young_pro"):
    g = client.post("/api/games", headers=auth_headers, json={"kind": "LIFE", "name": "Mundo"}).json()
    h = {**auth_headers, "X-Game-Id": str(g["id"])}
    r = client.post("/api/game/start", headers=h, json={"mode": "CAREER", "scenario": scenario, "seed": seed, "sim": sim})
    assert r.status_code == 200, r.text
    return g, h


def _advance(client, h, n=1):
    for _ in range(n):
        r = client.post(f"{B}/close", headers=h, json={"ref_month": client.get(f"{B}/overview", headers=h).json()["month"]["ref_month"][:7], "confirm": True})
        assert r.status_code == 200, r.text


def test_dynamic_world_prices_assets_with_the_simulator_not_the_real_market(client, auth_headers, assets):
    g, h = _mk_world(client, auth_headers)
    q0 = client.get(f"/api/assets/{assets['PETR4'].id}/quote", headers=h).json()
    assert D(q0["price"]) == D("40")                                                          # âncora = cotação real no início
    r = client.post("/api/trades/buy", headers=h, json={"asset_id": assets["PETR4"].id, "quantity": "10"})
    assert r.status_code == 201, r.text
    _advance(client, h, 6)
    q6 = client.get(f"/api/assets/{assets['PETR4'].id}/quote", headers=h).json()
    assert D(q6["price"]) != D("40") and D(q6["price"]) > 0
    with SessionLocal() as s:
        rows = list(s.scalars(select(SimPrice).where(SimPrice.asset_id == assets["PETR4"].id).order_by(SimPrice.ref_month)))
        assert [r.source for r in rows] == ["ANCHOR"] + ["SIM"] * 6 and len({r.ref_month for r in rows}) == 7
        frozen = [(r.ref_month, r.price) for r in rows]
    # outro ativo nunca usado também é calculado (sob demanda) a partir da âncora + fatores guardados
    q_btc = client.get(f"/api/assets/{assets['BTC'].id}/quote", headers=h).json()
    assert D(q_btc["price"]) > 0
    _advance(client, h, 2)
    with SessionLocal() as s:
        again = list(s.scalars(select(SimPrice).where(SimPrice.asset_id == assets["PETR4"].id).order_by(SimPrice.ref_month)))
        assert [(r.ref_month, r.price) for r in again[:7]] == frozen and len(again) == 9      # histórico não é recalculado
    # a conta e outras partidas continuam com preço real
    assert D(client.get(f"/api/assets/{assets['PETR4'].id}/quote", headers=auth_headers).json()["price"]) == D("40")
    # o patrimônio acompanha o preço simulado
    pf = client.get("/api/portfolio", headers=h).json()
    unit = D(client.get(f"/api/assets/{assets['PETR4'].id}/quote", headers=h).json()["price_brl"])
    assert D(pf["market_value_brl"]) == (unit * 10).quantize(D("0.01"))


def test_simulated_world_is_reproducible_across_two_games_with_same_seed(client, auth_headers, assets):
    _, h1 = _mk_world(client, auth_headers, seed=9)
    _, h2 = _mk_world(client, auth_headers, seed=9)
    for h in (h1, h2):
        client.get(f"/api/assets/{assets['PETR4'].id}/quote", headers=h)
        _advance(client, h, 4)
    p1 = D(client.get(f"/api/assets/{assets['PETR4'].id}/quote", headers=h1).json()["price"])
    p2 = D(client.get(f"/api/assets/{assets['PETR4'].id}/quote", headers=h2).json()["price"])
    assert p1 == p2


def test_crisis_is_persisted_with_history_and_affects_companies_and_prices(client, auth_headers, monkeypatch):
    from backend.services.engine import crises as engine_crises
    real = engine_crises.maybe_start
    state = {"done": False}

    def forced_start(m, ctx, active, last, ref, rng, params):
        if not state["done"]:
            state["done"] = True
            return forced("RECESSION", 0.9)
        return real(m, ctx, active, last, ref, rng, params)
    monkeypatch.setattr(engine_crises, "maybe_start", forced_start)
    g, h = _mk_world(client, auth_headers, seed=2)
    _advance(client, h, 8)
    eco = client.get("/api/economy", headers=h).json()
    c = next(x for x in eco["crises"] if x["type"] == "RECESSION")
    assert c["label"] == "Recessão econômica" and len(c["path"]) >= 7 and c["phase"] in ("ONSET", "PEAK", "RECOVERY")
    assert c["sectors"]["RESTAURANT"] < 0 and c["peak"] >= 0.85
    un = [float(x["unemployment"]) for x in eco["history"]]
    assert un[-1] > un[0] + 1.0                                                                # desemprego subiu pela propagação
    assert eco["history"][-1]["regime"] and eco["history"][-1]["fx"] and "class_index" in eco["history"][-1]
    # os efeitos setoriais entram na demanda das empresas
    from backend.models import Company
    from backend.services import economy_service
    with SessionLocal() as s:
        st_ = s.scalar(select(EconomyState).order_by(EconomyState.ref_month.desc()))
        assert st_.engine["info"]["sector"].get("RESTAURANT", 0) < 0
        assert len(list(s.scalars(select(EconomicCrisis)))) == len({(x.type, x.start_month) for x in s.scalars(select(EconomicCrisis))})


def test_month_processing_with_engine_is_idempotent_and_atomic(client, auth_headers, monkeypatch):
    g, h = _mk_world(client, auth_headers, seed=4)
    _advance(client, h, 2)
    with SessionLocal() as s:
        u = s.scalar(select(SimMonth.user_id).where(SimMonth.status == "OPEN"))
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        from backend.services import economy_service
        before = [(e.ref_month, e.inflation, e.engine) for e in s.scalars(select(EconomyState).where(EconomyState.user_id == u).order_by(EconomyState.ref_month))]
        economy_service.advance_to_month(s, u, month)
        economy_service.advance_to_month(s, u, month)
        s.commit()
        after = [(e.ref_month, e.inflation, e.engine) for e in s.scalars(select(EconomyState).where(EconomyState.user_id == u).order_by(EconomyState.ref_month))]
        assert before == after
    # falha no motor: o mês inteiro desfaz
    from backend.services.engine import world as engine_world
    from backend.services.finance_ledger import FinanceError
    monkeypatch.setattr(engine_world, "step", lambda *a, **k: (_ for _ in ()).throw(FinanceError("falha no motor")))
    r = client.post(f"{B}/close", headers=h, json={"ref_month": client.get(f"{B}/overview", headers=h).json()["month"]["ref_month"][:7], "confirm": True})
    assert r.status_code == 400
    monkeypatch.undo()
    with SessionLocal() as s:
        assert [(e.ref_month, e.inflation, e.engine) for e in s.scalars(select(EconomyState).where(EconomyState.user_id == u).order_by(EconomyState.ref_month))] == after


def test_nominal_and_real_values_in_reports(client, auth_headers):
    g, h = _mk_world(client, auth_headers, seed=6, sim={"crisis_frequency": 0})
    _advance(client, h, 13)
    reps = client.get("/api/progress/reports", headers=h).json()
    first = client.get(f"/api/progress/reports/{reps[0]['month'][:7]}", headers=h).json()
    last = client.get(f"/api/progress/reports/{reps[-1]['month'][:7]}", headers=h).json()
    assert first["real"]["cpi"] >= 1.0 and last["real"]["cpi"] > first["real"]["cpi"]
    assert last["real"]["purchasing_power"] < first["real"]["purchasing_power"] and last["real"]["purchasing_power"] < 1
    assert last["real"]["income_real"] < last["income"]                                        # renda nominal fixa perde poder de compra
    y = date.fromisoformat(reps[-1]["month"]).year
    a = client.get(f"/api/progress/reports/annual/{y}", headers=h).json()
    assert a["real"] and a["real"]["cost_of_living_change_pct"] >= 0 and a["real"]["income_real"] <= a["income"] + 1e-6


def test_economy_params_are_configurable_per_game(client, auth_headers):
    g, h = _mk_world(client, auth_headers, sim={"crisis_frequency": 0.0, "volatility": 1.5})
    assert client.get("/api/economy", headers=h).json()["params"]["volatility"] == 1.5
    r = client.put("/api/economy/params", headers=h, json={"crisis_severity": 2.0})
    assert r.status_code == 200 and r.json()["crisis_severity"] == 2.0 and r.json()["volatility"] == 1.5
    assert client.put("/api/economy/params", headers=h, json={"volatility": 50}).status_code == 400


def test_career_chart_has_real_past_plus_simulated_future(client, auth_headers, assets):
    g, h = _mk_world(client, auth_headers, seed=5)
    client.get(f"/api/assets/{assets['PETR4'].id}/quote", headers=h)
    _advance(client, h, 3)
    r = client.get(f"/api/assets/{assets['PETR4'].id}/chart?period=max", headers=h)
    assert r.status_code == 200, r.text
    times = [c["time"] for c in r.json()["candles"]]
    assert times == sorted(times) and len(times) > 4
    from datetime import datetime, timezone
    anchor = int(datetime(date.today().year, date.today().month, 1, tzinfo=timezone.utc).timestamp())
    assert any(t < anchor for t in times), "deve incluir os meses anteriores (passado real)"
    assert sum(1 for t in times if t >= anchor) == 4, "e os meses simulados (âncora + 3)"
