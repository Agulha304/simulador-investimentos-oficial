"""Regimes de mercado (cadeia de Markov com durações variáveis), influenciados pelas condições econômicas.

Cada regime define a tendência (m, %/mês do fator de mercado) e um multiplicador de volatilidade. A saída de um regime
é probabilística (duração média por regime); o destino depende do ESTRESSE econômico (crescimento fraco, juros altos,
confiança baixa, desemprego alto, pouca liquidez) e de crises ativas (que forçam o regime de crise).
"""
REGIMES = {                     # m (%/mês), vol (x), duração média (meses)
    "BULL": (1.30, 0.85, 22), "SIDEWAYS": (0.25, 1.00, 10), "BEAR": (-0.90, 1.30, 10),
    "HIGH_VOL": (0.00, 1.80, 6), "LOW_VOL": (0.55, 0.60, 14), "RECOVERY": (2.00, 1.20, 9), "CRISIS": (-2.60, 2.00, 6),
}
# pesos de destino quando o regime acaba (antes do ajuste por estresse)
NEXT = {
    "BULL": {"SIDEWAYS": 4, "LOW_VOL": 2, "HIGH_VOL": 2, "BEAR": 2},
    "SIDEWAYS": {"BULL": 4, "BEAR": 3, "LOW_VOL": 2, "HIGH_VOL": 2},
    "BEAR": {"SIDEWAYS": 4, "RECOVERY": 3, "HIGH_VOL": 2, "CRISIS": 0.3},
    "HIGH_VOL": {"BEAR": 3, "SIDEWAYS": 3, "BULL": 2, "RECOVERY": 1},
    "LOW_VOL": {"BULL": 4, "SIDEWAYS": 3, "HIGH_VOL": 1.5, "BEAR": 1},
    "RECOVERY": {"BULL": 6, "SIDEWAYS": 3, "HIGH_VOL": 1},
    "CRISIS": {"RECOVERY": 6, "BEAR": 3},
}


def stress_score(m: dict) -> float:
    """0 (economia saudável) a 1 (muito estressada)."""
    s = (max(0.0, -m["gap"]) / 4.0 + max(0.0, m["policy"] - 12.0) / 6.0 + max(0.0, 50.0 - m["consumer_conf"]) / 25.0
         + max(0.0, m["unemployment"] - 9.0) / 6.0 + max(0.0, 55.0 - m["liquidity"]) / 30.0 + max(0.0, m["default_rate"] - 5.0) / 8.0)
    return min(1.0, s / 2.5)


def step_regime(regime: str, age: int, macro: dict, crisis_intensity: float, rng) -> tuple[str, int]:
    """Devolve (novo regime, idade em meses). Uma crise relevante força o regime de CRISE; ao terminar, vem a RECUPERAÇÃO."""
    if crisis_intensity >= 0.50:
        return ("CRISIS", age + 1 if regime == "CRISIS" else 0)
    if regime == "CRISIS":
        return "RECOVERY", 0
    stress = stress_score(macro)
    mean = REGIMES[regime][2]
    # a duração fica variável: probabilidade de sair cresce com a idade; estresse encurta regimes bons e alonga os ruins
    p_leave = min(0.6, (1.0 / mean) * (1 + 0.5 * min(age, mean) / mean))
    if regime in ("BULL", "LOW_VOL", "SIDEWAYS"):
        p_leave *= 1 + 1.5 * stress
    elif regime in ("BEAR", "HIGH_VOL"):
        p_leave *= 1 - 0.5 * stress
    if rng.u("regime", "leave") >= p_leave:
        return regime, age + 1
    w = dict(NEXT[regime])
    for dest in w:
        if dest in ("BEAR", "HIGH_VOL", "CRISIS"):
            w[dest] *= 1 + 3.0 * stress
        if dest in ("BULL", "LOW_VOL", "RECOVERY"):
            w[dest] *= 1 + 1.2 * (1 - stress)
    total = sum(w.values())
    r, acc = rng.u("regime", "dest") * total, 0.0
    for dest, wt in w.items():
        acc += wt
        if r <= acc:
            return dest, 0
    return regime, age + 1
