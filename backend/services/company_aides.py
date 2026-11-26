"""Profissionais de apoio OPCIONAIS da empresa: MARKETEIRO e GERENTE (baixo/médio/alto nível), cada um com um briefing.

Regras PURAS (sem banco); a orquestração está em `company_aides_service`.

Marketeiro: cobra uma taxa mensal por nível e gasta o ORÇAMENTO MENSAL definido no briefing em campanhas. Quanto melhor o nível e mais
perto do orçamento de referência do negócio, maior a chance da campanha dar certo (nunca garantido: pode não dar nenhum resultado ou
ser viral).
Gerente: cobra uma taxa mensal e eleva a produtividade (capacidade) da empresa. O briefing define a RIGIDEZ (0 a 100): quanto mais
rígido, mais produtividade, porém os funcionários podem pedir demissão (chance mensal por funcionário que cresce com a rigidez e é
menor com gerentes de nível alto).
"""
from dataclasses import dataclass
from decimal import Decimal

from backend.core.money import quantize_money
from backend.models import CompanySize
from backend.services.goods_rules import hash01

D = Decimal
KINDS = ("MARKETER", "MANAGER", "CEO")
KIND_LABEL = {"MARKETER": "Marketeiro", "MANAGER": "Gerente", "CEO": "CEO"}
LEVELS = ("LOW", "MID", "HIGH")
LEVEL_LABEL = {"LOW": "Baixo nível", "MID": "Médio nível", "HIGH": "Alto nível"}
FEE_SIZE_MULT = {CompanySize.SMALL: D(1), CompanySize.MEDIUM: D("1.6"), CompanySize.LARGE: D("2.6")}
MAX_BUDGET = D(5_000_000)


@dataclass(frozen=True)
class MarketerTier:
    fee: Decimal            # taxa mensal (porte pequeno)
    skill: float            # qualidade do trabalho: multiplica a chance de dar certo e o tamanho do efeito
    fail_floor: float       # chance mínima de a campanha não surtir efeito, mesmo com orçamento bom
    viral: float            # chance de efeito viral, quando dá certo


@dataclass(frozen=True)
class ManagerTier:
    fee: Decimal
    boost: float            # ganho máximo de produtividade (capacidade) com rigidez 100 e o gerente certo
    quit_mult: float        # gerentes melhores seguram a equipe: multiplicam a chance de demissão


@dataclass(frozen=True)
class CeoTier:
    fee: Decimal
    success: float          # chance de a melhoria do mês dar certo
    scale: float            # tamanho das melhorias


CEOS = {"LOW": CeoTier(D(12000), 0.55, 0.6), "MID": CeoTier(D(26000), 0.75, 1.0), "HIGH": CeoTier(D(58000), 0.90, 1.5)}
CEO_FOCUS = {"GROWTH": "Crescimento (marca e relevância)", "SAVINGS": "Economia (cortar custos)", "QUALITY": "Qualidade e eficiência"}
MARKETERS = {
    "LOW": MarketerTier(D(1200), 0.45, 0.35, 0.04),
    "MID": MarketerTier(D(3200), 0.70, 0.20, 0.10),
    "HIGH": MarketerTier(D(8500), 0.92, 0.08, 0.20),
}
MANAGERS = {
    "LOW": ManagerTier(D(3500), 0.06, 1.00),
    "MID": ManagerTier(D(8500), 0.12, 0.70),
    "HIGH": ManagerTier(D(19000), 0.20, 0.45),
}
QUIT_BASE = 0.07            # chance mensal de saída por funcionário com rigidez 100 e gerente de baixo nível
QUIT_SHAPE = 2.0            # a chance cresce com a rigidez ao quadrado (rigidez baixa quase não demite)
BRIEFING_DEFAULT = {"MARKETER": {"monthly_budget": "0"}, "MANAGER": {"rigor": 40}, "CEO": {"focus": "GROWTH", "monthly_budget": "0", "reports": []}}


def check_level(level: str) -> str:
    if level not in LEVELS:
        raise ValueError("nível inexistente (LOW, MID ou HIGH)")
    return level


def monthly_fee(kind: str, level: str, size: CompanySize) -> Decimal:
    tier = {"MARKETER": MARKETERS, "MANAGER": MANAGERS, "CEO": CEOS}[kind][check_level(level)]
    return quantize_money(tier.fee * FEE_SIZE_MULT[size])


def build_briefing(kind: str, raw: dict) -> dict:
    """Valida o briefing (dict JSON) e devolve a forma persistida."""
    if kind == "MARKETER":
        try:
            budget = D(str(raw.get("monthly_budget", "0")))
        except Exception:
            raise ValueError("orçamento mensal inválido") from None
        if budget < 0 or budget > MAX_BUDGET:
            raise ValueError(f"o orçamento mensal de marketing vai de 0 a {MAX_BUDGET}")
        return {"monthly_budget": str(quantize_money(budget))}
    if kind == "CEO":
        focus = raw.get("focus", "GROWTH")
        if focus not in CEO_FOCUS:
            raise ValueError("foco do CEO inválido (GROWTH, SAVINGS ou QUALITY)")
        try:
            budget = D(str(raw.get("monthly_budget", "0")))
        except Exception:
            raise ValueError("orçamento mensal inválido") from None
        if budget < 0 or budget > MAX_BUDGET:
            raise ValueError(f"o orçamento mensal de melhorias vai de 0 a {MAX_BUDGET}")
        return {"focus": focus, "monthly_budget": str(quantize_money(budget))}
    rigor = raw.get("rigor", 40)
    if not isinstance(rigor, int) or isinstance(rigor, bool) or not 0 <= rigor <= 100:
        raise ValueError("a rigidez do gerente vai de 0 a 100")
    return {"rigor": rigor}


# ------------------------------------------------------------------ marketeiro

@dataclass(frozen=True)
class CampaignResult:
    outcome: str            # NONE | OK | VIRAL
    boost: float            # alta de demanda do mês
    relevance: float        # pontos de relevância ganhos
    effort: float           # orçamento / orçamento de referência
    chance: float


def campaign(level: str, *, budget: Decimal, reference: Decimal, seed, company_id: int, ref) -> CampaignResult:
    """Sorteio determinístico da campanha do mês. `reference` = orçamento mensal que uma campanha de nível médio exigiria (custo base de
    marketing do negócio). Orçamento muito abaixo do de referência quase não funciona; acima dele rende pouco a mais (satura em 1,5x)."""
    t = MARKETERS[check_level(level)]
    if budget <= 0:
        return CampaignResult("NONE", 0.0, 0.0, 0.0, 0.0)
    effort = min(1.5, float(budget / reference)) if reference > 0 else 1.0
    chance = max(0.05, min(0.95, (1 - t.fail_floor) * t.skill * min(1.0, 0.25 + 0.75 * effort) + 0.10 * min(effort, 1.0)))
    roll = hash01(seed, "mkt-roll", company_id, ref.isoformat())
    if roll >= chance:
        return CampaignResult("NONE", 0.0, 0.0, effort, chance)
    viral = hash01(seed, "mkt-viral", company_id, ref.isoformat()) < t.viral
    scale = (0.35 + 0.65 * min(effort, 1.5) / 1.5) * (0.6 + 0.4 * t.skill)
    boost = 0.20 * scale * (1.8 if viral else 1.0)
    rel = 2.5 * scale * (2.0 if viral else 1.0)
    return CampaignResult("VIRAL" if viral else "OK", round(boost, 3), round(rel, 2), effort, chance)


# ------------------------------------------------------------------ gerente

def productivity_boost(level: str, rigor: int) -> float:
    """Multiplicador adicional da capacidade (1 + ganho). Rigidez 0 rende 40% do ganho máximo; 100 rende 100%."""
    t = MANAGERS[check_level(level)]
    return 1.0 + t.boost * (0.4 + 0.6 * rigor / 100)


def quit_probability(level: str, rigor: int) -> float:
    return QUIT_BASE * MANAGERS[check_level(level)].quit_mult * (rigor / 100) ** QUIT_SHAPE


def quits(level: str, rigor: int, *, seed, company_id: int, employee_id: int, ref) -> bool:
    return hash01(seed, "mgr-quit", company_id, employee_id, ref.isoformat()) < quit_probability(level, rigor)


# ------------------------------------------------------------------ CEO
def ceo_improvement(level: str, focus: str, *, seed, company_id: int, ref, budget: Decimal, reference: Decimal) -> dict:
    """Melhoria do mês do CEO. Foco e orçamento direcionam o tipo; o nível define a chance de dar certo e o tamanho do efeito."""
    t = CEOS[check_level(level)]
    effort = min(1.5, 0.8 + float(budget / reference)) if reference > 0 and budget > 0 else 0.8
    weights = {"GROWTH": {"brand": 0.5, "process": 0.2, "quality": 0.15, "contracts": 0.15}, "SAVINGS": {"contracts": 0.55, "process": 0.25, "quality": 0.1, "brand": 0.1},
               "QUALITY": {"quality": 0.5, "process": 0.3, "contracts": 0.1, "brand": 0.1}}[focus]
    roll, acc, kind = hash01("ceo-kind", seed, company_id, ref.isoformat()), 0.0, "process"
    for k, w in weights.items():
        acc += w
        if roll < acc:
            kind = k
            break
    ok = hash01("ceo-ok", seed, company_id, ref.isoformat()) < min(0.97, t.success * (0.9 + 0.1 * effort))
    mag = t.scale * effort * (0.7 + 0.6 * hash01("ceo-mag", seed, company_id, ref.isoformat()))
    return {"kind": kind, "ok": ok, "mag": round(mag, 3)}
