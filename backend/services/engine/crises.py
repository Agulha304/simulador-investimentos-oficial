"""Crises econômicas e financeiras: tipos, gatilhos por vulnerabilidade, dinâmica de vários meses e propagação.

Uma crise NÃO é um aviso na tela: a cada mês ela injeta CHOQUES nas equações macro (crédito, liquidez, demanda, câmbio,
inflação, juros...) e nos ativos. O resto da propagação (desemprego, queda do consumo, inadimplência, aperto de crédito,
recessão) acontece sozinho pelas relações do modelo macro, sem sequência fixa de eventos.
"""
from dataclasses import asdict, dataclass, field

from backend.services.engine.params import SimParams

# tipo: (rótulo, prob. base/mês, pesos das vulnerabilidades, efeitos por mês a intensidade 1, setores (segmentos) %demanda, classes de ativo %/mês)
TYPES = {
    "FINANCIAL": ("Crise financeira", 0.0020, {"credit_boom": 1.0, "valuation": 1.2, "debt": 0.8},
                  {"liq": -9, "credit": -6, "conf": -5, "demand": -0.45, "risk": -8, "fx": 1.2, "policy": -0.35, "default": 0.6, "equity": -3.5, "house": -0.4},
                  {"TECH": -10, "AGENCY": -8, "REAL_ESTATE_AGENCY": -15, "CONSTRUCTION": -12, "AGRIBUSINESS": -6},
                  {"FII": -3.0, "REIT": -3.0, "CRYPTO": -7.0, "ETF": -3.0, "STOCK": -3.5, "BDR": -3.0}),
    "BANKING": ("Crise bancária", 0.0008, {"debt": 1.0, "bank": 1.5, "credit_boom": 0.6},
                {"liq": -12, "credit": -9, "conf": -4, "demand": -0.5, "risk": -7, "default": 0.9, "policy": -0.4, "equity": -2.5},
                {"TECH": -6, "AGENCY": -6, "REAL_ESTATE_AGENCY": -10, "CONSTRUCTION": -10, "AGRIBUSINESS": -5},
                {"FII": -2.0, "CRYPTO": -4.0, "STOCK": -2.8, "ETF": -2.5, "BDR": -2.0}),
    "INFLATION": ("Crise inflacionária", 0.0018, {"inflation": 1.6, "fx": 0.4},
                  {"supply": 0.7, "policy": 0.8, "conf": -2.0, "demand": -0.15, "equity": -1.0, "risk": -2},
                  {"RESTAURANT": -8, "CLOTHING": -8, "ECOMMERCE": -5, "AGRIBUSINESS": -7},
                  {"FII": -1.5, "STOCK": -1.0, "CRYPTO": -2.0}),
    "DEBT": ("Crise de dívida", 0.0020, {"debt": 1.6, "recession": 0.5},
             {"default": 1.0, "credit": -5, "demand": -0.30, "conf": -3, "liq": -4, "equity": -1.8, "risk": -4},
             {"CONSTRUCTION": -10, "CLOTHING": -8, "TECH": -4, "AGRIBUSINESS": -9}, {"STOCK": -2.0, "FII": -2.0, "CRYPTO": -3.0}),
    "HOUSING": ("Crise imobiliária", 0.0020, {"housing": 1.6, "credit_boom": 0.6, "valuation": 0.4},
                {"house": -1.2, "credit": -3, "demand": -0.20, "conf": -2, "equity": -1.0, "vacancy": 1.0},
                {"REAL_ESTATE_AGENCY": -25, "CONSTRUCTION": -20}, {"FII": -3.5, "REIT": -3.0}),
    "SUPPLY": ("Crise de oferta", 0.0020, {"fx": 0.8, "import": 1.0},
               {"supply": 1.0, "comm": 4.0, "demand": -0.15, "conf": -2, "equity": -1.0, "prod": -0.4},
               {"INDUSTRY": -10, "RESTAURANT": -8, "TRANSPORT": -10, "CONSTRUCTION": -8, "AGRIBUSINESS": -12}, {"STOCK": -1.5, "FII": -0.8}),
    "CURRENCY": ("Crise cambial", 0.0016, {"fx": 1.4, "import": 0.8, "inflation": 0.5},
                 {"fx": 6.0, "supply": 0.4, "policy": 0.6, "conf": -3, "risk": -6, "demand": -0.20, "equity": -1.5},
                 {"ECOMMERCE": -8, "INDUSTRY": -6, "TECH": -6, "AGRIBUSINESS": 6}, {"STOCK": -2.0, "CRYPTO": 2.0, "REIT": 3.0, "BDR": 3.0}),
    "RECESSION": ("Recessão econômica", 0.0024, {"recession": 1.4, "debt": 0.5, "policy": 0.8},
                  {"demand": -0.60, "unemp": 0.10, "conf": -4, "equity": -2.0, "credit": -2, "default": 0.3},
                  {"RESTAURANT": -14, "CLOTHING": -14, "CAFE": -12, "TECH": -10, "AGENCY": -12, "CONSTRUCTION": -14, "WORKSHOP": -8,
                   "INDUSTRY": -12, "TRANSPORT": -10, "ECOMMERCE": -8, "SUPERMARKET": -4, "REAL_ESTATE_AGENCY": -14, "AGRIBUSINESS": -7},
                  {"STOCK": -2.2, "FII": -1.5, "CRYPTO": -3.0}),
    "GLOBAL": ("Crise global", 0.0010, {},
               {"demand": -0.50, "liq": -7, "risk": -10, "comm": -5, "fx": 3, "equity": -4.5, "conf": -4, "credit": -3},
               {"TECH": -8, "AGENCY": -8, "TRANSPORT": -10, "INDUSTRY": -10, "RESTAURANT": -10, "CLOTHING": -10, "AGRIBUSINESS": -8},
               {"STOCK": -4.0, "CRYPTO": -8.0, "FII": -3.0, "ETF": -4.0, "BDR": -3.5, "REIT": -3.0}),
}
MAX_CONCURRENT = 2
COOLDOWN = 36          # meses até a mesma crise poder voltar
PHASES = ("ONSET", "PEAK", "RECOVERY")


@dataclass
class Crisis:
    type: str
    start: str                    # "YYYY-MM"
    phase: str = "ONSET"
    intensity: float = 0.2
    peak: float = 0.6
    hold: int = 3                 # meses no pico
    age: int = 0
    triggers: dict = field(default_factory=dict)
    path: list = field(default_factory=list)     # histórico [{m, i, phase}]
    ended: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Crisis":
        return Crisis(**d)


def vulnerabilities(m: dict, ctx: dict) -> dict[str, float]:
    """Vulnerabilidades acumuladas (0..~1.5) usadas como gatilho."""
    c = lambda v: max(0.0, min(1.5, v))                                         # noqa: E731
    return {
        "debt": c((m["household_debt"] - 45.0) / 30.0 + (m["firm_debt"] - 60.0) / 50.0),
        "credit_boom": c((m["credit"] - 62.0) / 25.0),
        "valuation": c(ctx.get("bubble", 0.0) / 25.0),                           # alta acumulada acima da tendência
        "inflation": c((m["inflation"] - 6.5) / 5.0 + ctx.get("months_high_infl", 0) / 24.0),
        "fx": c(abs(ctx.get("fx_dev", 0.0)) / 0.35),
        "import": c(ctx.get("fx_dev", 0.0) / 0.40),
        "recession": c(-m["gap"] / 2.5 + ctx.get("months_neg_gap", 0) / 18.0),
        "housing": c(ctx.get("house_growth_36", 0.0) / 40.0),
        "bank": c((m["default_rate"] - 5.0) / 6.0 + (55.0 - m["liquidity"]) / 40.0),
        "policy": c((m["policy"] - 12.5) / 6.0),
    }


def maybe_start(m: dict, ctx: dict, active: list[Crisis], history_last: dict, ref: str, rng, params: SimParams) -> Crisis | None:
    """No máximo uma crise nova por mês, com probabilidade = base × (piso + Σ pesos×vulnerabilidades)."""
    if len(active) >= MAX_CONCURRENT:
        return None
    vul = vulnerabilities(m, ctx)
    for key, (label, base, weights, *_rest) in TYPES.items():
        if any(c.type == key for c in active):
            continue
        last = history_last.get(key)
        if last is not None and last < COOLDOWN:
            continue
        score = 0.30 + sum(w * vul.get(k, 0.0) for k, w in weights.items())
        p = min(0.12, base * params.crisis_frequency * score)
        if rng.u("crisis", key) < p:
            mag = rng.u("crisis", key, "mag")
            peak = min(1.0, (0.45 + 0.45 * mag + 0.10 * min(1.0, score / 2.0)) * params.crisis_severity)
            return Crisis(type=key, start=ref, intensity=0.20 * peak, peak=peak,
                          hold=2 + int(rng.u("crisis", key, "hold") * 5), triggers={k: round(v, 3) for k, v in vul.items() if v > 0.05})
    return None


def step_crisis(c: Crisis, m: dict, ref: str) -> Crisis:
    """Evolução de um mês: sobe até o pico, permanece, e se recupera — mais devagar com crédito escasso e desemprego alto."""
    c.age += 1
    stress = max(0.0, (50.0 - m["credit"]) / 50.0) + max(0.0, (m["unemployment"] - 10.0) / 10.0) + max(0.0, (50.0 - m["liquidity"]) / 60.0)
    if c.phase == "ONSET":
        c.intensity = min(c.peak, c.intensity + 0.18 * c.peak)
        if c.intensity >= c.peak - 1e-9:
            c.phase, c.hold = "PEAK", c.hold
    elif c.phase == "PEAK":
        c.hold -= 1
        if c.hold <= 0:
            c.phase = "RECOVERY"
    else:
        decay = max(0.70, min(0.97, 0.86 + 0.06 * min(1.0, stress) - 0.02 * max(0.0, (m["credit"] - 55.0) / 40.0)))
        c.intensity *= decay
        if c.intensity < 0.08:
            c.ended, c.intensity = ref, 0.0
    c.path.append({"m": ref, "i": round(c.intensity, 3), "phase": c.phase})
    return c


def effects(active: list[Crisis]) -> dict:
    """Soma dos choques de todas as crises ativas, já multiplicados pela intensidade de cada uma."""
    out: dict = {"class_ret": {}, "sector": {}}
    for c in active:
        if c.ended:
            continue
        _, _, _, eff, sectors, classes = TYPES[c.type]
        i = c.intensity
        for k, v in eff.items():
            out[k] = out.get(k, 0.0) + v * i
        for seg, pct in sectors.items():
            out["sector"][seg] = out["sector"].get(seg, 0.0) + pct * i
        for cl, pct in classes.items():
            out["class_ret"][cl] = out["class_ret"].get(cl, 0.0) + pct * i
    return out
