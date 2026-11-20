"""Preços dos ativos: modelo de fatores com retornos logarítmicos (preço nunca fica negativo).

    r(i,t) = α(classe) + β(i,mercado)·F_mercado + β(i,juros)·ΔJuros + β(i,inflação)·ΔInflação + β(i,crescimento)·ΔHiato
             + β(i,câmbio)·F_câmbio + β(i,commodities)·F_commodities + β(i,imóveis)·F_imóveis + β(i,risco)·F_risco
             + choque da crise (classe) + ε(i,t)·σ_idio(i)·√regime_vol  − ½σ²        ;  P(t) = P(t−1)·exp(r/100)

Os fatores são COMUNS (geram correlação); ε é o choque próprio de cada ativo (t de Student: caudas gordas). Parâmetros
por classe e ajustes determinísticos por ativo (β e volatilidade variam ±20–25% conforme o símbolo).
"""
import math

from backend.services.life_rules import hash01

# classe: (α %/mês, σ idio %/mês, β {mkt, rates, infl, growth, fx, comm, house, risk}, usa o fator de mercado dos EUA)
CLASSES = {
    "STOCK":  (0.30, 4.3, {"mkt": 1.00, "rates": -0.45, "infl": -0.10, "growth": 0.5, "fx": -0.10, "comm": 0.10, "risk": 0.010}, False),
    "BDR":    (0.30, 4.0, {"mkt": 0.85, "rates": -0.25, "infl": -0.05, "growth": 0.3, "fx": 0.60, "comm": 0.00, "risk": 0.008}, True),
    "ETF":    (0.07, 1.6, {"mkt": 0.95, "rates": -0.40, "infl": -0.10, "growth": 0.4, "fx": -0.05, "comm": 0.05, "risk": 0.008}, False),
    "FII":    (0.60, 2.3, {"mkt": 0.40, "rates": -1.25, "infl": 0.15, "growth": 0.3, "fx": 0.00, "comm": 0.00, "house": 0.35, "risk": 0.006}, False),
    "REIT":   (0.50, 3.2, {"mkt": 0.50, "rates": -0.80, "infl": 0.10, "growth": 0.3, "fx": 0.45, "comm": 0.00, "house": 0.25, "risk": 0.006}, True),
    "CRYPTO": (2.30, 16.0, {"mkt": 0.75, "rates": -0.35, "infl": 0.05, "growth": 0.2, "fx": 0.00, "comm": 0.00, "risk": 0.035}, True),
}
DEFAULT_CLASS = "STOCK"


def asset_class(a: dict) -> str:
    c = a["asset_class"]
    return c if c in CLASSES else DEFAULT_CLASS


def jitter(symbol: str, what: str, spread: float) -> float:
    return 1.0 + spread * (2.0 * hash01("asset", symbol, what) - 1.0)


def factors(*, regime_m: float, regime_vol: float, macro: dict, prev: dict, house_ret: float, shocks: dict, crisis: dict, rng, vol: float) -> dict:
    mkt_br = (1.10 + regime_m + regime_vol * vol * 4.8 * rng.t(5.0, "mkt_br") + 0.9 * (macro["gap"] - prev["gap"])
              + crisis.get("equity", 0.0) + shocks.get("equity", 0.0) + shocks.get("assets_all", 0.0))
    mkt_us = 0.60 * mkt_br + 0.80 * (0.30 * regime_m + regime_vol * vol * 3.6 * rng.t(5.0, "mkt_us"))
    return {"mkt": mkt_br, "mkt_us": mkt_us, "rates": macro["policy"] - prev["policy"], "infl": macro["inflation"] - prev["inflation"],
            "growth": macro["gap"] - prev["gap"], "fx": macro["fx_ret"], "comm": macro["comm_ret"], "house": house_ret,
            "risk": macro["risk_appetite"] - 55.0}


def step_price(price: float, meta: dict, F: dict, regime_vol: float, class_shock: dict, rng, vol: float) -> float:
    cls = asset_class(meta)
    alpha, sd, betas, us = CLASSES[cls]
    sym = meta["symbol"]
    b = jitter(sym, "beta", 0.20)
    sigma = sd * jitter(sym, "vol", 0.25) * vol * math.sqrt(regime_vol)
    r = alpha + b * betas["mkt"] * (F["mkt_us"] if us else F["mkt"])
    for k in ("rates", "infl", "growth", "fx", "comm", "house", "risk"):
        r += betas.get(k, 0.0) * F[k]
    r += class_shock.get(cls, 0.0) + sigma * rng.t(4.0, "asset", sym)
    r -= 0.5 * (sigma / 100.0) ** 2 * 100.0                 # correção de convexidade: o retorno esperado do preço não "foge"
    r = max(-60.0, min(r, 60.0))
    return max(price * math.exp(r / 100.0), 1e-8)
