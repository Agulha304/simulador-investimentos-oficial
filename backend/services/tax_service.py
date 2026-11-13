"""Regras tributárias, isoladas do resto do sistema para poderem mudar sem mexer nos fluxos.

Simplificações (simulador educacional, não orientação fiscal):
  * dividendos e rendimentos de FIIs no Brasil: isentos para pessoa física;
  * JCP: 15% retido na fonte;
  * proventos de ativos dos EUA (ações, REITs, ETFs): 30% retidos na fonte;
  * a fonte de dados não distingue dividendo de JCP, então tudo vira DIVIDEND (isento).
"""
from dataclasses import dataclass
from decimal import Decimal

from backend.core.money import quantize_money
from backend.models import Asset, DistributionKind

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
