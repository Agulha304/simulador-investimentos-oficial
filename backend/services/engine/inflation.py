"""Inflação por categoria e índices de preços.

Cada categoria tem um índice próprio. A variação mensal combina: inflação subjacente (expectativa ancorada na meta),
pressão de demanda (hiato do produto), repasse cambial (importados), commodities (energia, combustíveis, alimentos),
salários (serviços) e choques específicos (eventos, crises). A inflação geral é a média ponderada da cesta.
"""
import math

from backend.services.engine.params import TARGET_INFLATION

# categoria: (peso na cesta, beta p/ inflação subjacente, sens. à demanda, repasse cambial, commodities, salários, volatilidade própria)
BASKET = {
    "alimentacao":  (0.20, 1.05, 0.020, 0.10, 0.10, 0.00, 0.55),
    "moradia":      (0.14, 0.90, 0.015, 0.00, 0.00, 0.10, 0.18),
    "energia":      (0.05, 0.85, 0.010, 0.00, 0.12, 0.00, 0.60),
    "combustiveis": (0.05, 0.70, 0.010, 0.20, 0.30, 0.00, 1.10),
    "transporte":   (0.10, 0.95, 0.015, 0.08, 0.10, 0.05, 0.30),
    "saude":        (0.12, 1.10, 0.008, 0.03, 0.00, 0.20, 0.15),
    "educacao":     (0.06, 1.00, 0.004, 0.00, 0.00, 0.25, 0.08),
    "vestuario":    (0.05, 0.80, 0.020, 0.15, 0.00, 0.00, 0.40),
    "lazer":        (0.07, 0.90, 0.030, 0.05, 0.00, 0.10, 0.30),
    "servicos":     (0.09, 1.10, 0.015, 0.00, 0.00, 0.35, 0.15),
    "importados":   (0.07, 0.30, 0.010, 0.60, 0.05, 0.00, 0.45),
}
CONSUMER = tuple(BASKET)
COST_INDICES = ("insumos", "materiais_construcao", "salarios")        # índices de custo (não entram na cesta do consumidor)
ALL_CATEGORIES = CONSUMER + COST_INDICES + ("geral",)
PERSISTENCE = 0.35                                                    # inércia da variação de cada categoria


def step_prices(*, prev_changes: dict[str, float], infl12: float, gap: float, fx_ret: float, comm_ret: float,
                wage_m: float, shocks: dict, rng, vol: float, supply_pp: float) -> dict[str, float]:
    """Variações mensais (%) por categoria + 'geral', 'insumos', 'materiais_construcao' e 'salarios'."""
    core_m = (0.55 * infl12 + 0.45 * TARGET_INFLATION) / 12.0               # inflação subjacente mensal (%)
    out: dict[str, float] = {}
    for cat, (w, beta, dem, fxp, com, wag, v) in BASKET.items():
        base = core_m * beta + dem * gap + fxp * fx_ret + com * comm_ret + wag * (wage_m - core_m) + supply_pp / 12.0 * (1.2 if com else 0.6)
        base += shocks.get("price_pp", {}).get(cat, 0.0) + 0.25 * v * vol * rng.z("infl", cat)
        prev = prev_changes.get(cat, core_m)
        out[cat] = (1 - PERSISTENCE) * base + PERSISTENCE * prev
        out[cat] = max(-3.0, min(out[cat], 12.0))
    out["geral"] = sum(BASKET[c][0] * out[c] for c in CONSUMER)
    out["insumos"] = max(-4.0, min(0.55 * out["geral"] + 0.12 * comm_ret + 0.10 * fx_ret + shocks.get("price_pp", {}).get("insumos", 0.0), 12.0))
    out["materiais_construcao"] = max(-4.0, min(0.6 * out["geral"] + 0.10 * comm_ret + shocks.get("price_pp", {}).get("materiais_construcao", 0.0)
                                                + 0.20 * shocks.get("house", 0.0), 12.0))
    out["salarios"] = wage_m
    return out


def apply(indices: dict[str, float], changes: dict[str, float]) -> dict[str, float]:
    return {c: round(indices.get(c, 1.0) * (1 + changes.get(c, 0.0) / 100.0), 6) for c in ALL_CATEGORIES}


def trailing_inflation(history: list[float]) -> float:
    """Inflação acumulada nos últimos 12 meses (%) a partir das variações mensais da cesta."""
    if not history:
        return TARGET_INFLATION
    last = history[-12:]
    acc = math.prod(1 + h / 100.0 for h in last)
    if len(last) < 12:                                   # início de partida: anualiza o que existe
        acc = acc ** (12.0 / len(last))
    return (acc - 1) * 100.0
