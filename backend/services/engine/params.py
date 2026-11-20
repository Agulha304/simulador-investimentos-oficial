"""Parâmetros configuráveis da simulação (por partida, sem mexer na lógica)."""
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class SimParams:
    volatility: float = 1.0          # multiplica a volatilidade dos ativos e do câmbio
    event_frequency: float = 1.0     # multiplica a chance de eventos aleatórios
    crisis_frequency: float = 1.0    # multiplica a chance de crises
    crisis_severity: float = 1.0     # multiplica a intensidade das crises
    shock_scale: float = 1.0         # multiplica os ruídos macroeconômicos

    @classmethod
    def from_dict(cls, d: dict | None) -> "SimParams":
        d = d or {}
        names = {f.name for f in fields(cls)}
        out = {k: float(v) for k, v in d.items() if k in names}
        for k, v in out.items():
            if not 0.0 <= v <= 5.0:
                raise ValueError(f"parâmetro {k} deve estar entre 0 e 5")
        return cls(**out)


TARGET_INFLATION = 4.0       # meta de inflação (% a.a.)
NEUTRAL_REAL_RATE = 5.0      # juro real neutro (% a.a.)
NAIRU = 8.0                  # desemprego de equilíbrio (%)
TREND_GROWTH = 2.0           # crescimento potencial (% a.a.)
INITIAL_MACRO = {
    "inflation": 4.5, "policy": 10.5, "unemployment": 8.0, "growth": 2.0, "gap": 0.0, "fx": 5.2,
    "consumer_conf": 55.0, "business_conf": 55.0, "credit": 55.0, "liquidity": 65.0, "risk_appetite": 55.0,
    "household_debt": 45.0, "firm_debt": 60.0, "default_rate": 3.0, "wage_growth": 5.0, "commodity": 100.0, "demand": 100.0,
}
