"""Empresas e equipes no exterior: fator de preços/câmbio do país, custo de funcionários em moeda local, trabalho remoto x presencial e
tributos estrangeiros.

* `company_factor`: multiplica receita, insumos, aluguel e custos fixos de uma empresa fora do Brasil = índice de custo do país x
  (câmbio do mês / câmbio inicial). Preços e custos acompanham a economia local e a moeda.
* Funcionários: `country` + `work_mode`. Quem mora em outro país recebe em MOEDA LOCAL (o custo em reais varia com o câmbio) e só pode
  ser contratado remotamente (a menos que a empresa esteja no país dele). Só alguns cargos aceitam trabalho remoto (garçom, corretor,
  cozinheiro etc. não); o efeito na capacidade (vendas) varia por cargo.
* Tributos de empresas estrangeiras: IVA/imposto sobre vendas (líquido de créditos) + imposto sobre o lucro, com as alíquotas do país;
  encargos patronais entram no custo do funcionário.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from backend.core.money import quantize_money
from backend.services import country_rules as cr
from backend.services import world_service as ws

D = Decimal
ZERO = D("0.00")
HOME = cr.HOME
VAT_NET_SHARE = 0.45             # parte do IVA que sobra como custo depois dos créditos de insumos
FOREIGN_TZ_PENALTY = 0.97        # fuso horário e comunicação: remoto no exterior rende 3% menos
FOREIGN_OPEN_EXTRA_MONTHS = 1    # abrir empresa em outro país leva mais um mês (burocracia)

# cargo -> efeito do trabalho REMOTO na capacidade (>1 melhora, <1 piora). Cargos ausentes NÃO podem ser remotos.
REMOTE_FACTOR: dict[str, float] = {
    "dev": 1.10, "devops": 1.08, "qa": 1.05, "pm": 1.04, "designer": 1.06, "copywriter": 1.06, "digital_marketing": 1.05, "social": 1.05,
    "strategist": 1.04, "accountant": 1.04, "account": 1.02, "lawyer": 1.03, "catalog": 1.03, "architect": 1.00, "support": 0.97,
    "sales_support": 0.96, "seller": 0.90, "logistics": 0.98,
}


def can_be_remote(role_key: str) -> bool:
    return role_key in REMOTE_FACTOR


def company_factor(db, c, ref: date) -> D:
    """Fator de preços/custos da empresa em reais (1,00 no Brasil)."""
    if c.country == HOME:
        return D(1)
    cc = cr.get(c.country)
    return D(str(round(cc.cost_index * float(ws.fx(db, c.user_id, c.country, ref) * ws.price_level(db, c.user_id, c.country, ref)) / cc.fx0, 6)))


def market_mult(db, c, ref: date) -> float:
    """Tamanho relativo do mercado do país x o momento da economia dele (recessão derruba, boom aumenta a demanda)."""
    if c.country == HOME:
        return 1.0
    return cr.get(c.country).market * ws.demand(db, c.user_id, c.country, ref)


def emp_cost(db, c, e, ref: date) -> D:
    """Custo mensal REAL do funcionário em reais. Brasileiros: regras do Brasil (CLT 2x, PJ 1x). No exterior: salário em moeda local
    (salário de referência x índice de salários do país, convertido pelo câmbio do mês) x encargo patronal do país (CLT) ou 1,0 (autônomo)."""
    from backend.models import EmployeeRegime
    from backend.services import company_rules as rules
    if e.country == HOME:
        return rules.payroll_cost(e.salary, e.regime)
    cc = cr.get(e.country)
    pl = ws.price_level(db, c.user_id, e.country, ref) / ws.price_level(db, c.user_id, e.country, max(e.hired_on, ws.EPOCH))   # salários acompanham a inflação do país
    ratio = D(str(round(float(ws.fx(db, c.user_id, e.country, ref) * pl) / cc.fx0, 6)))
    burden = D(str(cc.burden)) if e.regime == EmployeeRegime.CLT else D(1)
    return quantize_money(e.salary * ratio * burden)


def staff_productivity(e) -> D:
    """Multiplicador do trabalho remoto sobre a produtividade do funcionário."""
    if e.work_mode != "REMOTE":
        return D(1)
    f = REMOTE_FACTOR.get(e.role, 0.95)
    if e.country != HOME:
        f *= FOREIGN_TZ_PENALTY
    return D(str(round(f, 4)))


def validate_hire(c, role_key: str, work_mode: str, country: str) -> tuple[str, str]:
    work_mode, country = work_mode.upper(), country.upper()
    if work_mode not in ("ONSITE", "REMOTE"):
        raise ValueError("modalidade deve ser ONSITE ou REMOTE")
    try:
        cr.get(country)
    except ValueError:
        raise ValueError("país desconhecido") from None
    if work_mode == "REMOTE" and not can_be_remote(role_key):
        raise ValueError("este cargo não pode ser remoto (exige presença): contrate presencial")
    if work_mode == "ONSITE" and country != c.country:
        raise ValueError(f"funcionário presencial precisa morar no país da empresa ({cr.get(c.country).name}); contrate remoto")
    return work_mode, country


def wage_scale(country: str) -> D:
    return D(str(cr.get(country).wage_index)) if country != HOME else D(1)


# ------------------------------------------------------------------ tributos de empresas estrangeiras
@dataclass
class ForeignTax:
    total: Decimal
    regime: str = "EXT"
    lines: list = field(default_factory=list)
    annex: str | None = None

    def breakdown(self) -> list[dict]:
        return [{"name": n, "base": str(b), "rate_pct": str(r), "amount": str(a)} for n, b, r, a in self.lines]


def foreign_taxes(country: str, revenue: Decimal, operating_before_tax: Decimal) -> ForeignTax:
    cc = cr.get(country)
    vat = quantize_money(revenue * D(str(cc.vat / 100)) / (1 + D(str(cc.vat / 100))) * D(str(VAT_NET_SHARE)))
    corp = quantize_money(max(operating_before_tax - vat, ZERO) * D(str(cc.corp_tax / 100)))
    lines = []
    if vat > 0:
        lines.append((f"IVA/imposto sobre vendas ({cc.name}, líquido de créditos)", quantize_money(revenue), D(str(cc.vat)), vat))
    if corp > 0:
        lines.append((f"Imposto sobre o lucro ({cc.name})", max(operating_before_tax - vat, ZERO), D(str(cc.corp_tax)), corp))
    return ForeignTax(total=quantize_money(vat + corp), lines=lines)
