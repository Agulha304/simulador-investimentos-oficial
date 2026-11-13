"""Regras tributárias, isoladas do resto do sistema para poderem mudar sem mexer nos fluxos.

Simplificações (simulador educacional, não orientação fiscal):
  * dividendos e rendimentos de FIIs no Brasil: isentos para pessoa física;
  * JCP: 15% retido na fonte;
  * proventos de ativos dos EUA (ações, REITs, ETFs): 30% retidos na fonte;
  * a fonte de dados não distingue dividendo de JCP, então tudo vira DIVIDEND (isento).
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.core.money import quantize_money
from backend.models import Asset, DistributionKind, TaxRegime

US_WITHHOLDING = Decimal("0.30")
JCP_WITHHOLDING = Decimal("0.15")


@dataclass(frozen=True)
class TaxResult:
    tax_brl: Decimal
    rate: Decimal
    description: str


def distribution_tax(asset: Asset, kind: DistributionKind, gross_brl: Decimal) -> TaxResult:
    if asset.country == "US":
        rate, why = US_WITHHOLDING, "Retenção de 30% na fonte (EUA)"
    elif kind == DistributionKind.JCP:
        rate, why = JCP_WITHHOLDING, "IR de 15% retido na fonte (JCP)"
    else:
        rate, why = Decimal("0"), "Isento para pessoa física"
    return TaxResult(quantize_money(gross_brl * rate), rate, why)


# ------------------------------------------------------------------ renda fixa
# IR regressivo sobre o rendimento, pelo prazo desde a aplicação (dias corridos).
IR_BRACKETS = [(180, Decimal("0.225")), (360, Decimal("0.20")), (720, Decimal("0.175"))]
IR_LONG_TERM = Decimal("0.15")
# IOF regressivo (% do rendimento) para resgates com menos de 30 dias: dia 1..29.
IOF_TABLE = [96, 93, 90, 86, 83, 80, 76, 73, 70, 66, 63, 60, 56, 53, 50, 46, 43, 40, 36, 33, 30, 26, 23, 20, 16, 13, 10, 6, 3]


@dataclass(frozen=True)
class RedemptionTax:
    ir_brl: Decimal
    iof_brl: Decimal
    ir_rate: Decimal
    iof_rate: Decimal            # fração (0.96 = 96%)

    @property
    def total_brl(self) -> Decimal:
        return self.ir_brl + self.iof_brl


def ir_rate_for(days_held: int) -> Decimal:
    for limit, rate in IR_BRACKETS:
        if days_held <= limit:
            return rate
    return IR_LONG_TERM


def iof_rate_for(days_held: int) -> Decimal:
    if days_held >= 30:
        return Decimal("0")
    return Decimal(IOF_TABLE[max(days_held, 1) - 1]) / 100


def redemption_tax(regime: TaxRegime, applied_on: date, on_date: date, gain_brl: Decimal) -> RedemptionTax:
    """IOF (sobre o rendimento, só < 30 dias) e depois IR sobre o rendimento já descontado do IOF.
    Isento (LCI, LCA, CRI, CRA, debêntures incentivadas) ou sem ganho: zero."""
    zero = Decimal("0.00")
    if regime == TaxRegime.EXEMPT or gain_brl <= 0:
        return RedemptionTax(zero, zero, Decimal("0"), Decimal("0"))
    days = (on_date - applied_on).days
    iof_rate, ir_rate = iof_rate_for(days), ir_rate_for(days)
    iof = quantize_money(gain_brl * iof_rate)
    ir = quantize_money((gain_brl - iof) * ir_rate)
    return RedemptionTax(ir, iof, ir_rate, iof_rate)
