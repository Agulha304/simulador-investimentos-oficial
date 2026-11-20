"""Aleatoriedade controlada: cada sorteio é uma função de (semente, nome, mês). Sem estado global, sem repetição entre
mundos com sementes diferentes, e o mesmo mês sempre gera o mesmo resultado (auditável)."""
import math

from backend.services.life_rules import hash01


class Rng:
    def __init__(self, seed: int, ref: str):
        self.seed, self.ref = seed, ref

    def u(self, *name) -> float:
        return min(max(hash01(self.seed, self.ref, *name), 1e-12), 1 - 1e-12)

    def z(self, *name) -> float:
        """Normal padrão (Box-Muller)."""
        u1, u2 = self.u(*name, "a"), self.u(*name, "b")
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2 * math.pi * u2)

    def t(self, df: float, *name) -> float:
        """t de Student padronizada (caudas gordas): z / sqrt(chi2/df), reescalada para variância 1."""
        n = max(3, int(df))
        chi = sum(self.z(*name, "c", i) ** 2 for i in range(n))
        return self.z(*name, "n") / math.sqrt(chi / n) * math.sqrt((df - 2) / df)
