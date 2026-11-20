"""Dinâmica macroeconômica mensal. Os indicadores se influenciam (ver comentários em cada equação)."""
import math

from backend.services.engine import inflation as infl
from backend.services.engine.params import NAIRU, NEUTRAL_REAL_RATE, TARGET_INFLATION, TREND_GROWTH


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def step_macro(m: dict, shocks: dict, rng, scale: float, infl_hist: list[float], prev_changes: dict, fx_ppp: float) -> tuple[dict, dict, float]:
    """Devolve (novo estado macro, variações de preços por categoria, retorno mensal da casa própria %)."""
    s = lambda k: shocks.get(k, 0.0)                                  # noqa: E731
    n = lambda name, sd: sd * scale * rng.z("macro", name)            # noqa: E731
    real_rate = m["policy"] - m["inflation"]

    # 1) atividade: juro real alto, crédito escasso e baixa confiança reduzem o hiato do produto
    gap = (0.80 * m["gap"] - 0.18 * (real_rate - NEUTRAL_REAL_RATE) + 0.012 * (m["consumer_conf"] - 55.0)
           + 0.006 * (m["credit"] - 55.0) + s("demand") + n("gap", 0.30))
    gap = clamp(gap, -9.0, 6.0)
    growth = clamp(TREND_GROWTH + 0.8 * gap + 2.0 * (gap - m["gap"]) + s("prod"), -12.0, 12.0)
    # 2) emprego (lei de Okun): hiato negativo eleva o desemprego
    unemp = clamp(m["unemployment"] + 0.04 * (NAIRU - m["unemployment"]) - 0.08 * gap + s("unemp") + n("u", 0.05), 3.0, 25.0)
    # 3) câmbio: paridade de poder de compra, diferencial de juros (carry), aversão ao risco e choques
    carry = -0.0015 * (m["policy"] - 8.5)
    ppp = (m["inflation"] - 3.8) / 1200.0              # sem tendência estrutural: o câmbio acompanha o diferencial de inflação
    risk_off = 0.0040 * (55.0 - m["risk_appetite"]) / 10.0
    fx_ret = 100.0 * (ppp + carry + risk_off) - 4.0 * math.log(m["fx"] / fx_ppp) + s("fx") + n("fx", 2.2)
    fx_ret = clamp(fx_ret, -12.0, 25.0)
    fx = clamp(m["fx"] * math.exp(fx_ret / 100.0), 2.0, 100.0)
    fx_ret = 100.0 * math.log(fx / m["fx"])                          # variação efetivamente ocorrida (o repasse usa esta)
    # 4) commodities: ciclo global, reversão à média e choques de oferta
    comm_ret = clamp(0.3 * gap - 1.2 * math.log(m["commodity"] / 100.0) + s("comm") + n("comm", 3.5), -25.0, 25.0)
    commodity = clamp(m["commodity"] * math.exp(comm_ret / 100.0), 30.0, 400.0)
    # 5) salários: acompanham a inflação passada e o aperto do mercado de trabalho
    wage_g = clamp(0.8 * m["wage_growth"] + 0.2 * (0.7 * m["inflation"] + 0.3 * TARGET_INFLATION + 0.5 * (NAIRU - unemp) + 1.0), 0.0, 25.0)
    # 6) inflação por categoria → geral
    changes = infl.step_prices(prev_changes=prev_changes, infl12=m["inflation"], gap=gap, fx_ret=fx_ret, comm_ret=comm_ret,
                               wage_m=wage_g / 12.0, shocks=shocks, rng=rng, vol=scale, supply_pp=s("supply"))
    hist = infl_hist + [changes["geral"]]
    inflation = clamp(infl.trailing_inflation(hist), -3.0, 40.0)
    # 7) política monetária (regra de Taylor suavizada): reage à inflação e ao hiato; choques de política (ex.: liquidez em crise)
    taylor = NEUTRAL_REAL_RATE + inflation + 1.0 * (inflation - TARGET_INFLATION) + 0.5 * gap + s("policy")
    policy = 0.85 * m["policy"] + 0.15 * taylor
    policy = clamp(policy, m["policy"] - 1.5, m["policy"] + 1.5)
    policy = clamp(policy, 2.0, 30.0)
    # 8) confiança: renda, emprego, inflação e juros; crises derrubam
    cc = clamp(0.75 * m["consumer_conf"] + 0.25 * (55 + 3.0 * gap - 2.0 * (unemp - NAIRU) - 1.2 * (inflation - 4.5)) + s("conf") + n("cc", 1.5), 0, 100)
    bc = clamp(0.75 * m["business_conf"] + 0.25 * (55 + 2.5 * gap - 0.9 * (policy - 10.5) + 0.25 * (m["credit"] - 55.0)) + 0.8 * s("conf") + n("bc", 1.5), 0, 100)
    # 9) crédito, liquidez e inadimplência (canal financeiro)
    default = clamp(0.8 * m["default_rate"] + 0.2 * (3.0 + 0.5 * (unemp - NAIRU) + 0.06 * (m["household_debt"] - 45.0)
                                                    + 0.30 * (policy - 10.5)) + s("default"), 0.5, 30.0)
    liq = clamp(0.85 * m["liquidity"] + 0.15 * (65.0 + 0.2 * (m["credit"] - 55.0) - 1.5 * (default - 3.0)) + s("liq") + n("liq", 1.5), 5, 100)
    credit = clamp(0.80 * m["credit"] + 0.20 * (55.0 - 3.0 * (policy - 10.5) + 0.3 * (liq - 65.0) + 0.2 * (bc - 55.0)
                                                 - 1.0 * (default - 3.0)) + s("credit") + n("cr", 1.0), 5, 95)
    hh = clamp(m["household_debt"] + 0.012 * (credit - 50.0) - 0.02 * (m["household_debt"] - 45.0) - 0.03 * max(0.0, default - 6.0), 20, 130)
    firm = clamp(m["firm_debt"] + 0.015 * (credit - 50.0) - 0.02 * (m["firm_debt"] - 60.0) - 0.04 * max(0.0, default - 6.0), 20, 160)
    risk = clamp(0.80 * m["risk_appetite"] + 0.20 * (55 + 0.4 * (cc - 55) + 0.3 * (liq - 65.0) - 0.5 * max(0.0, fx_ret)) + s("risk") + n("risk", 2.0), 0, 100)
    demand = clamp(100.0 + 3.0 * gap + 0.10 * (cc - 55.0), 50.0, 150.0)
    house = 0.30 + 0.10 * gap - 0.06 * (policy - 10.5) + 0.004 * (credit - 55.0) + s("house") + n("house", 0.4)
    new = {"inflation": inflation, "policy": policy, "unemployment": unemp, "growth": growth, "gap": gap, "fx": fx,
           "consumer_conf": cc, "business_conf": bc, "credit": credit, "liquidity": liq, "risk_appetite": risk,
           "household_debt": hh, "firm_debt": firm, "default_rate": default, "wage_growth": wage_g, "commodity": commodity,
           "demand": demand, "fx_ret": fx_ret, "comm_ret": comm_ret}
    return new, changes, clamp(house, -4.0, 4.0)
