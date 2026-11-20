"""Orquestração do mês econômico (função pura). Ordem — cada passo só usa dados já atualizados no passo anterior:

  1 registrar o estado inicial · 2 vulnerabilidades · 3 crises (avanço e novas) · 4 regime de mercado
  5 choques (crises + eventos) · 6 macro, inflação e índices de preços · 7 câmbio, juros, crédito (dentro do macro)
  8 fatores comuns de mercado · 9 índices de classes de ativos · 10 devolve o novo estado para persistir.
Os preços de cada ativo são calculados por `markets.step_price` com os fatores devolvidos aqui.
"""
import copy
import math
from dataclasses import dataclass, field

from backend.services.engine import crises as cr
from backend.services.engine import inflation as infl
from backend.services.engine import macro as mc
from backend.services.engine import markets as mk
from backend.services.engine import regimes as rg
from backend.services.engine.params import INITIAL_MACRO, SimParams
from backend.services.engine.rng import Rng

CLASS_INDEX_KEYS = ("equity", "equity_us", "fii", "crypto", "bond", "house", "commodity")


@dataclass
class WorldState:
    macro: dict
    indices: dict
    changes: dict = field(default_factory=dict)
    infl_hist: list = field(default_factory=list)
    regime: str = "SIDEWAYS"
    regime_age: int = 0
    crises: list = field(default_factory=list)            # [Crisis.to_dict()] ativas e recém-encerradas
    since_end: dict = field(default_factory=dict)         # tipo -> meses desde o fim (cooldown)
    ctx: dict = field(default_factory=lambda: {"bubble": 0.0, "months_high_infl": 0, "months_neg_gap": 0, "fx_ppp": 5.2,
                                               "house_hist": []})
    class_index: dict = field(default_factory=lambda: {k: 100.0 for k in CLASS_INDEX_KEYS})

    def to_dict(self) -> dict:
        return copy.deepcopy({"macro": self.macro, "indices": self.indices, "changes": self.changes, "infl_hist": self.infl_hist[-12:],
                              "regime": self.regime, "regime_age": self.regime_age, "crises": self.crises, "since_end": self.since_end,
                              "ctx": {**self.ctx, "house_hist": self.ctx["house_hist"][-36:]}, "class_index": self.class_index})

    @staticmethod
    def from_dict(d: dict) -> "WorldState":
        return WorldState(**copy.deepcopy(d))


def initial_world(overrides: dict | None = None) -> WorldState:
    macro = dict(INITIAL_MACRO)
    macro.update({"fx_ret": 0.0, "comm_ret": 0.0})
    for k, v in (overrides or {}).items():
        macro[k] = float(v)
    ws = WorldState(macro=macro, indices={c: 1.0 for c in infl.ALL_CATEGORIES})
    ws.ctx["fx_ppp"] = macro["fx"]
    # semeia 12 meses de inflação coerentes com o nível inicial (a inflação de 12 meses começa no valor pedido)
    ws.infl_hist = [((1 + macro["inflation"] / 100.0) ** (1 / 12.0) - 1) * 100.0] * 12
    return ws


@dataclass
class StepInfo:
    factors: dict
    crisis_effects: dict
    started: list
    ended: list
    house_ret: float
    regime: str


def step(ws: WorldState, seed: int, ref: str, params: SimParams, event_shocks: dict | None = None) -> tuple[WorldState, StepInfo]:
    rng = Rng(seed, ref)
    ev = event_shocks or {}
    prev_macro = dict(ws.macro)
    ctx = dict(ws.ctx)
    # 2-3) crises: avança as ativas, cria no máximo uma nova conforme as vulnerabilidades acumuladas
    active = [cr.Crisis.from_dict(c) for c in ws.crises]
    ended = []
    for c in active:
        if not c.ended:
            cr.step_crisis(c, ws.macro, ref)
            if c.ended:
                ended.append(c)
    since = {k: v + 1 for k, v in ws.since_end.items()}
    for c in ended:
        since[c.type] = 0
    live = [c for c in active if not c.ended]
    started = []
    new = cr.maybe_start(ws.macro, {**ctx, "fx_dev": math.log(ws.macro["fx"] / ctx["fx_ppp"]),
                                    "house_growth_36": sum(ctx["house_hist"][-36:])}, live, since, ref, rng, params)
    if new is not None:
        live.append(new)
        started.append(new)
        new.path.append({"m": ref, "i": round(new.intensity, 3), "phase": new.phase})
    crisis_fx = cr.effects(live)
    # 4) regime de mercado
    top = max((c.intensity for c in live), default=0.0)
    regime, age = rg.step_regime(ws.regime, ws.regime_age, ws.macro, top, rng)
    # 5) choques totais (crises + eventos), em unidades das equações do macro
    shocks: dict = {"price_pp": dict(ev.get("price_pp", {}))}
    for k in ("demand", "supply", "conf", "credit", "liq", "fx", "comm", "policy", "unemp", "risk", "house", "prod", "default", "equity", "assets_all"):
        shocks[k] = crisis_fx.get(k, 0.0) + ev.get(k, 0.0)
    shocks["price_pp"]["energia"] = shocks["price_pp"].get("energia", 0.0) + 0.05 * crisis_fx.get("comm", 0.0)
    shocks["price_pp"]["combustiveis"] = shocks["price_pp"].get("combustiveis", 0.0) + 0.06 * crisis_fx.get("comm", 0.0)
    # 6-7) macro (inclui câmbio, juros, crédito, liquidez, desemprego) e preços por categoria
    macro, changes, house_ret = mc.step_macro(ws.macro, shocks, rng, params.shock_scale, ws.infl_hist, ws.changes, ctx["fx_ppp"])
    indices = infl.apply(ws.indices, changes)
    # 8) fatores comuns dos ativos
    reg_m, reg_vol, _ = rg.REGIMES[regime]
    F = mk.factors(regime_m=reg_m, regime_vol=reg_vol, macro=macro, prev=prev_macro, house_ret=house_ret, shocks=shocks,
                   crisis=crisis_fx, rng=rng, vol=params.volatility)
    # 9) índices de classes (acompanham as séries para gráficos e vulnerabilidades)
    ci = dict(ws.class_index)
    ci["equity"] *= math.exp(F["mkt"] / 100.0)
    ci["equity_us"] *= math.exp(F["mkt_us"] / 100.0)
    ci["fii"] *= math.exp((mk.CLASSES["FII"][0] + mk.CLASSES["FII"][2]["mkt"] * F["mkt"] + mk.CLASSES["FII"][2]["rates"] * F["rates"]
                           + 0.35 * F["house"] + crisis_fx["class_ret"].get("FII", 0.0)) / 100.0)
    ci["crypto"] *= math.exp((mk.CLASSES["CRYPTO"][0] + 0.75 * F["mkt"] + 0.035 * F["risk"] + crisis_fx["class_ret"].get("CRYPTO", 0.0)) / 100.0)
    ci["bond"] *= math.exp((macro["policy"] / 12.0 - 3.5 * F["rates"]) / 100.0)                 # carrego do juro − duração × Δjuro
    ci["house"] *= math.exp(house_ret / 100.0)
    ci["commodity"] = macro["commodity"]
    # contexto de vulnerabilidades (memória do ciclo)
    ctx["bubble"] = 0.985 * ctx["bubble"] + (F["mkt"] - 0.7)
    ctx["months_high_infl"] = ctx["months_high_infl"] + 1 if macro["inflation"] > 6.5 else max(0, ctx["months_high_infl"] - 1)
    ctx["months_neg_gap"] = ctx["months_neg_gap"] + 1 if macro["gap"] < -1.0 else max(0, ctx["months_neg_gap"] - 1)
    ctx["fx_ppp"] = ctx["fx_ppp"] * math.exp((macro["inflation"] - 3.8) / 1200.0)
    ctx["house_hist"] = (ctx["house_hist"] + [house_ret])[-36:]
    keep = [c.to_dict() for c in live] + [c.to_dict() for c in ended]
    out = WorldState(macro=macro, indices=indices, changes=changes, infl_hist=(ws.infl_hist + [changes["geral"]])[-12:], regime=regime,
                     regime_age=age, crises=keep, since_end=since, ctx=ctx, class_index=ci)
    return out, StepInfo(F, crisis_fx, started, ended, house_ret, regime)


def simulate(seed: int, months: int, params: SimParams | None = None, overrides: dict | None = None):
    """Gera `months` meses de economia (para testes e calibração). Devolve a lista de estados e a de StepInfo."""
    params = params or SimParams()
    ws = initial_world(overrides)
    states, infos = [ws], []
    for i in range(months):
        y, m = divmod(i, 12)
        ws, info = step(ws, seed, f"{2030 + y:04d}-{m + 1:02d}", params)
        states.append(ws)
        infos.append(info)
    return states, infos
