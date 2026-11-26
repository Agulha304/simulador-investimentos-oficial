"""Economia SIMULADA dos países do jogo (nenhum dado da vida real é consultado em tempo de jogo).

Cada partida (semente) sorteia a trajetória de cada país: inflação, crescimento, juros, nível de preços, câmbio em reais e CRISES
(cambial, recessão, bancária, pico de inflação, choque de energia, boom) e CRISES GLOBAIS que atingem todos (com mais força nos emergentes,
menos nos "portos seguros"). O ponto de partida de cada país (inflação-alvo, crescimento, volatilidade, risco) é só um perfil inicial
FICTÍCIO, sorteado de novo a cada partida (±30%): dois jogos nunca têm a mesma economia mundial.

A simulação é determinística (semente + país + mês), roda mês a mês a partir de `EPOCH` e guarda o estado em cache incremental.
"""
import math
from dataclasses import dataclass
from datetime import date

from backend.services import country_rules as cr
from backend.services.budget_service import shift_month
from backend.services.goods_rules import hash01

EPOCH = date(2026, 11, 1)
MAX_STEPS = 720

# perfil inicial fictício por país: (crescimento-tendência % a.a., risco emergente 0..1, "porto seguro" no câmbio -1..1)
PROFILE = {
    "BR": (2.0, 0.8, -0.4), "US": (2.2, 0.1, 0.7), "CA": (1.8, 0.1, 0.2), "GB": (1.5, 0.2, 0.3), "IE": (3.0, 0.2, 0.1), "DE": (1.2, 0.1, 0.4),
    "FR": (1.2, 0.15, 0.3), "ES": (1.8, 0.25, 0.1), "IT": (0.8, 0.3, 0.0), "PT": (1.8, 0.3, 0.0), "NL": (1.6, 0.1, 0.4), "CH": (1.5, 0.05, 1.0),
    "AU": (2.0, 0.15, 0.1), "NZ": (2.0, 0.2, 0.0), "JP": (0.7, 0.1, 0.8), "KR": (2.2, 0.3, 0.0), "AR": (1.5, 1.0, -0.8), "CL": (2.2, 0.5, -0.3),
    "MX": (2.0, 0.6, -0.4),
}
CRISIS_TYPES = {
    "CURRENCY": ("Crise cambial", 6, 12), "RECESSION": ("Recessão", 6, 14), "BANKING": ("Crise bancária", 6, 12),
    "INFLATION": ("Pico de inflação", 6, 12), "ENERGY": ("Choque de energia", 4, 9), "BOOM": ("Boom econômico", 8, 18),
}
GLOBAL_TYPES = {"GLOBAL_RECESSION": "Recessão global", "FINANCIAL_PANIC": "Pânico financeiro mundial", "PANDEMIC": "Pandemia", "COMMODITY_BOOM": "Boom de commodities"}
P_LOCAL = 0.011               # chance mensal base de crise local (x risco do país)
P_GLOBAL = 0.011             # chance mensal de crise global


@dataclass
class Crisis:
    code: str                  # país ("*" = global)
    kind: str
    label: str
    start: date
    months: int
    intensity: float           # 0.4..1.6

    @property
    def end(self) -> date:
        return shift_month(self.start, self.months - 1)

    def active(self, ref: date) -> bool:
        return self.start <= ref <= self.end

    def phase(self, ref: date) -> float:
        """Perfil temporal 0..1: sobe rápido e decai devagar."""
        t = (ref.year - self.start.year) * 12 + ref.month - self.start.month
        if t < 0 or t >= self.months:
            return 0.0
        peak = max(1, self.months // 4)
        return (t + 1) / peak if t < peak else max(0.0, 1 - (t - peak) / max(1, self.months - peak) * 0.85)


class World:
    """Estado incremental do mundo de uma semente."""

    def __init__(self, seed: int):
        self.seed = seed
        self.months: list[date] = [EPOCH]
        self.crises: list[Crisis] = []
        self.profile: dict[str, dict] = {}
        for code, c in cr.COUNTRIES.items():
            g, risk, haven = PROFILE[code]
            u = lambda tag: hash01("wprof", seed, code, tag)                    # noqa: E731
            self.profile[code] = {
                "infl_t": c.infl * (0.70 + 0.60 * u("i")), "g_t": g * (0.70 + 0.60 * u("g")), "vol": c.vol * (0.75 + 0.50 * u("v")),
                "risk": risk * (0.70 + 0.60 * u("r")), "haven": haven}
        self.state: dict[date, dict[str, dict]] = {EPOCH: {code: self._initial(code) for code in cr.COUNTRIES}}

    def _initial(self, code: str) -> dict:
        p, c = self.profile[code], cr.COUNTRIES[code]
        return {"infl": p["infl_t"], "growth": p["g_t"], "rate": p["infl_t"] + 2.0, "pl": 1.0, "fx": float(c.fx0), "demand": 1.0, "crisis": None,
                "confidence": 55.0}

    def _roll_crises(self, m: date) -> None:
        s = self.seed
        if hash01("wglob", s, m.isoformat()) < P_GLOBAL:
            kind = list(GLOBAL_TYPES)[int(hash01("wgk", s, m.isoformat()) * len(GLOBAL_TYPES))]
            self.crises.append(Crisis("*", kind, GLOBAL_TYPES[kind], m, 8 + int(10 * hash01("wgd", s, m.isoformat())), 0.6 + hash01("wgi", s, m.isoformat())))
        kinds = list(CRISIS_TYPES)
        for code in cr.COUNTRIES:
            p = self.profile[code]
            if any(x.code == code and x.active(m) and x.kind != "BOOM" for x in self.crises) and hash01("wcl", s, code, m.isoformat()) < 0.7:
                continue                                                          # país já em crise: menos chance de outra ao mesmo tempo
            if hash01("wloc", s, code, m.isoformat()) < P_LOCAL * (0.6 + 2.2 * p["risk"]):
                kind = kinds[int(hash01("wlk", s, code, m.isoformat()) * len(kinds))]
                if kind == "CURRENCY" and code == "CH":                             # franco suíço quase não tem crise cambial
                    kind = "ENERGY"
                lab, lo, hi = CRISIS_TYPES[kind]
                self.crises.append(Crisis(code, kind, f"{lab}: {cr.COUNTRIES[code].name}", m, lo + int((hi - lo) * hash01("wld", s, code, m.isoformat())),
                                          0.5 + 1.1 * hash01("wli", s, code, m.isoformat())))

    def _shock(self, code: str, m: date) -> dict:
        """Efeitos somados das crises ativas no mês: inflação (pontos), crescimento (pontos), câmbio (variação mensal), nível de preços, demanda."""
        out = {"infl": 0.0, "growth": 0.0, "fx": 0.0, "pl": 0.0, "demand": 0.0, "label": None, "conf": 0.0}
        risk, haven = self.profile[code]["risk"], self.profile[code]["haven"]
        for c in self.crises:
            if not c.active(m):
                continue
            ph = c.phase(m) * c.intensity
            if c.code == "*":
                beta = 0.5 + risk
                if c.kind == "GLOBAL_RECESSION":
                    out["growth"] -= 3.5 * ph * beta; out["demand"] -= 0.18 * ph * beta; out["fx"] += (-0.012 * (1 - haven) + 0.006 * haven) * ph * beta
                elif c.kind == "FINANCIAL_PANIC":
                    out["growth"] -= 2.5 * ph * beta; out["demand"] -= 0.12 * ph * beta; out["fx"] += (-0.03 * risk + 0.007 * haven) * ph; out["conf"] -= 14 * ph
                elif c.kind == "PANDEMIC":
                    out["growth"] -= 4.5 * ph * (0.7 + 0.3 * beta); out["demand"] -= 0.25 * ph; out["infl"] += 0.6 * ph; out["conf"] -= 16 * ph
                else:                                                             # boom de commodities: bom para emergentes
                    out["growth"] += 1.2 * ph * risk; out["fx"] += 0.007 * ph * risk; out["demand"] += 0.05 * ph
                out["label"] = out["label"] or c.label
                continue
            if c.code != code:
                continue
            out["label"] = c.label
            if c.kind == "CURRENCY":
                out["fx"] -= 0.055 * ph; out["infl"] += 4.0 * ph; out["growth"] -= 1.5 * ph; out["conf"] -= 12 * ph
            elif c.kind == "RECESSION":
                out["growth"] -= 4.0 * ph; out["demand"] -= 0.20 * ph; out["fx"] -= 0.008 * ph; out["conf"] -= 10 * ph
            elif c.kind == "BANKING":
                out["growth"] -= 2.5 * ph; out["fx"] -= 0.02 * ph; out["demand"] -= 0.14 * ph; out["conf"] -= 15 * ph
            elif c.kind == "INFLATION":
                out["infl"] += 9.0 * ph; out["pl"] += 0.004 * ph; out["fx"] -= 0.012 * ph; out["growth"] -= 0.8 * ph
            elif c.kind == "ENERGY":
                out["infl"] += 3.5 * ph; out["pl"] += 0.003 * ph; out["growth"] -= 1.0 * ph; out["demand"] -= 0.06 * ph
            elif c.kind == "BOOM":
                out["growth"] += 2.5 * ph; out["demand"] += 0.14 * ph; out["fx"] += 0.01 * ph; out["conf"] += 10 * ph
        return out

    def step(self) -> None:
        prev_m = self.months[-1]
        m = shift_month(prev_m, 1)
        self._roll_crises(m)
        prev, new = self.state[prev_m], {}
        for code in cr.COUNTRIES:
            p, s, pv = self.profile[code], self._shock(code, m), prev[code]
            n = lambda tag: (hash01("wn", self.seed, code, m.isoformat(), tag) - 0.5) * 2         # noqa: E731
            infl = max(-1.0, pv["infl"] + 0.12 * (p["infl_t"] - pv["infl"]) + s["infl"] * 0.35 + n("i") * 0.35 * (1 + p["risk"]))
            growth = pv["growth"] + 0.18 * (p["g_t"] - pv["growth"]) + s["growth"] * 0.22 + n("g") * 0.35
            rate = max(0.0, infl + 2.0 + 0.6 * (infl - p["infl_t"]) + 0.3 * (p["g_t"] - growth) + (2.0 if s["label"] and p["risk"] > 0.5 else 0.0))
            pl = pv["pl"] * (1 + infl / 1200 + s["pl"])
            demand = max(0.45, min(1.45, 1 + 0.45 * (growth - p["g_t"]) / 4 + s["demand"] + 0.06 * n("d")))
            new[code] = {"infl": infl, "growth": growth, "rate": rate, "pl": pl, "demand": demand, "crisis": s["label"],
                         "confidence": max(5.0, min(95.0, pv["confidence"] + 0.1 * (55 - pv["confidence"]) + s["conf"] * 0.3 + n("c") * 2)), "_fxshock": s["fx"]}
        bri = new["BR"]["infl"]
        for code, c in cr.COUNTRIES.items():
            if code == "BR":
                new[code]["fx"] = 1.0
                continue
            p, pv = self.profile[code], prev[code]
            ppp = (bri - new[code]["infl"]) / 1200 * 0.8                         # paridade de poder de compra: inflação maior desvaloriza a moeda
            carry = (new[code]["rate"] - new["BR"]["rate"]) / 1200 * 0.25         # juros maiores atraem capital
            noise = (hash01("wfx", self.seed, code, m.isoformat()) - 0.5) * 2 * p["vol"]
            fx = pv["fx"] * math.exp(ppp + carry + new[code]["_fxshock"] + noise - new["BR"]["_fxshock"] * 0.6)
            new[code]["fx"] = min(c.fx0 * 8, max(c.fx0 / 8, fx))
        self.months.append(m)
        self.state[m] = new

    def at(self, ref: date) -> dict[str, dict]:
        ref = max(ref, EPOCH)
        steps = 0
        while self.months[-1] < ref and steps < MAX_STEPS:
            self.step()
            steps += 1
        return self.state[min(ref, self.months[-1])]


_WORLDS: dict[int, World] = {}


def world(seed: int) -> World:
    w = _WORLDS.get(seed)
    if w is None:
        if len(_WORLDS) > 64:
            _WORLDS.clear()
        w = _WORLDS[seed] = World(seed)
    return w


def state(seed: int, code: str, ref: date) -> dict:
    return world(seed).at(ref)[code.upper()]


def fx(seed: int, code: str, ref: date) -> float:
    return state(seed, code, ref)["fx"]


def price_level(seed: int, code: str, ref: date) -> float:
    return state(seed, code, ref)["pl"]


def demand(seed: int, code: str, ref: date) -> float:
    return state(seed, code, ref)["demand"]


def crises(seed: int, ref: date) -> list[Crisis]:
    w = world(seed)
    w.at(ref)
    return [c for c in w.crises if c.start <= ref]


def series(seed: int, code: str, ref: date, n: int = 24, key: str = "fx") -> list[dict]:
    w = world(seed)
    w.at(ref)
    out = []
    for i in range(n - 1, -1, -1):
        m = shift_month(ref, -i)
        if m < EPOCH:
            m = EPOCH
        out.append({"month": m.isoformat(), key: round(w.state[m][code][key], 6)})
    return out
