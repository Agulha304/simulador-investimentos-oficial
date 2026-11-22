"""Simulação de balanceamento das empresas (sem banco): usa as MESMAS funções puras do fechamento mensal
(`company_rules.sales_month`, `next_relevance`, `next_reputation`) e a mesma conta de custos, para provar que um jogador razoável
(preço de mercado, equipe sugerida, cargos obrigatórios em meio período, estoque em dia) sai do prejuízo e chega ao lucro.

Usada por `tools/balance_companies.py` (tabela por segmento) e pelo teste de balanceamento.
"""
import math
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from backend.core.money import quantize_money
from backend.models import CompanyChannel, CompanySize, EmployeeRegime
from backend.services import company_incidents as incidents
from backend.services import company_rules as rules
from backend.services import company_taxes as ctax

D = Decimal
HIRE_FACTOR = D("1.05")          # o jogador paga ~5% acima do salário-base (nível pleno)
PJ_ASKING = D("1.10")            # PJ pede ~10% a mais, mas custa 1x (sem encargos)
SIM_START = date(2026, 1, 1)
SIM_SEED = 1


@dataclass
class SimMonth:
    month: int
    relevance: float
    reputation: float
    demand: float
    sold: float
    revenue: float
    variable: float          # custo das mercadorias + custos variáveis + impostos (tributos reais, ver company_taxes)
    fixed: float             # aluguel + custos fixos
    payroll: float
    profit: float
    cash: float
    zero_prob: float
    taxes: float = 0.0
    tax_regime: str = ""
    incidents: float = 0.0     # custo ESPERADO dos imprevistos do mês (fase 5; já dentro de `fixed`)


@dataclass
class SimResult:
    segment: str
    rows: list[SimMonth] = field(default_factory=list)
    minimum_capital: float = 0.0
    start_cash: float = 0.0
    monthly_cost: float = 0.0        # folha + fixos (sem variáveis)

    @property
    def turn_month(self) -> int | None:
        """Mês de virada: primeiro mês com lucro seguido de lucro nos 3 meses seguintes (None se não chegou)."""
        p = [r.profit for r in self.rows]
        for i, v in enumerate(p):
            if v > 0 and all(x > 0 for x in p[i:i + 4]):
                return self.rows[i].month
        return None

    @property
    def min_cash(self) -> float:
        return min(r.cash for r in self.rows)


def _add_month(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def simulate(segment, *, months: int = 36, size: CompanySize = CompanySize.SMALL, location: str | None = None,
             regime: EmployeeRegime = EmployeeRegime.CLT, price: Decimal | None = None, marketing: bool = False,
             expected: bool = True, seed: int = SIM_SEED, company_id: int = 1, season: bool = False,
             econ_mult: float = 1.0, supplier_mult: float = 1.0, incidents_on: bool = True) -> SimResult:
    """Simula `months` meses de uma empresa nova (porte e local padrão, equipe sugerida + obrigatórios).

    `expected=True`: usa o VALOR ESPERADO dos meses zerados (vendas x (1 - p)), sem sorteio: curva suave para calibrar.
    `expected=False`: sorteia os meses zerados com `hash01` (semente `seed`), como no jogo.
    `incidents_on` (fase 5): soma ao custo fixo o valor ESPERADO dos imprevistos (despejo, quebra de equipamento e processo trabalhista:
    probabilidade mensal x custo da decisão típica, ver `company_incidents`).
    `supplier_mult` (fase 4): preço CONTRATADO dos fornecedores / preço de referência (1.0 = contratos a ~preço de lista; o jogador
    que negocia bem fica abaixo de 1.0). Estoque: entra no custo das mercadorias; serviços com fornecedor: no custo variável."""
    seg = rules.SEGMENTS[segment]
    channel = rules.PHYSICAL if rules.PHYSICAL in seg.channels else rules.ONLINE
    loc = location or (seg.default_location if channel == rules.PHYSICAL else rules.ONLINE_LOCATION_KEY)
    site_mode = rules.SiteMode.RENT if channel == rules.PHYSICAL else None
    price = price if price is not None else seg.price
    mult = HIRE_FACTOR * (PJ_ASKING if regime == EmployeeRegime.PJ else D(1))
    team = rules.initial_staff(seg, size)
    staff = [(r, D(1)) for r in team]
    payroll = sum((rules.payroll_cost(seg.role(r).salary * mult, regime) for r in team), D(0))
    for r in rules.mandatory_roles(channel):
        role = seg.role_for(r, size)
        payroll += rules.payroll_cost(role.salary * rules.wage_hours_factor(role.hours or rules.FULL_TIME_HOURS) * mult, regime)
    fixed = float(rules.monthly_fixed(seg, loc, size, channel=channel, site_mode=site_mode))
    unit_supply = float(rules.supply_cost_per_sale(seg, D(str(supplier_mult)))) if seg.needs_suppliers else 0.0
    service_supply = seg.needs_suppliers and not seg.has_stock                       # oficina e transporte: sem estoque
    unit_cogs = unit_supply if seg.has_stock else 0.0
    minimum = rules.minimum_capital(seg, loc, size, channel, site_mode)
    stock0 = sum((q * s.unit_cost for s, q in rules.initial_stock_quantities(seg, loc, size)), D(0)) * D(str(supplier_mult))   # 1ª compra
    hiring = sum((seg.role(r).salary * mult * rules.HIRING_COST_MONTHS for r in team), D(0)) \
        + sum((seg.role_for(r, size).salary * rules.wage_hours_factor(seg.role_for(r, size).hours or 36) * mult * rules.HIRING_COST_MONTHS
               for r in rules.mandatory_roles(channel)), D(0))
    cash = float(minimum - rules.setup_cost(seg, size, channel) - stock0 - rules.land_value(seg, channel, site_mode, loc, size) - hiring)
    out = SimResult(seg.key.value, minimum_capital=float(minimum), start_cash=cash, monthly_cost=float(payroll) + fixed)
    rel, rep = 0.0, 50.0
    clt = (len(team) + len(rules.mandatory_roles(channel))) if regime == EmployeeRegime.CLT else 0
    history: list[D] = []                                # receita mensal anterior (RBT12 proporcionalizado, como no jogo)
    hint: str | None = None
    ratio = float(price) / float(seg.price)
    for n in range(1, months + 1):
        ref = _add_month(SIM_START, n)
        mk = marketing
        s = rules.sales_month(seg, location=loc, size=size, units=1, capacity_level=0, relevance=rel, reputation=int(round(rep)),
                              price=price, company_id=company_id, ref=ref, seed=seed, marketing=mk, staff=staff,
                              econ_mult=econ_mult, season=season)
        p0 = rules.zero_month_prob(rel, ratio)
        if expected:                                     # valor esperado: sem sorteio, vendas x (1 - p)
            base = rules.sales_month(seg, location=loc, size=size, units=1, capacity_level=0, relevance=rel,
                                     reputation=int(round(rep)), price=price, company_id=company_id, ref=ref, seed=seed + 10**6,
                                     marketing=mk, staff=staff, econ_mult=econ_mult, season=season)
            sold_ok = (base.potential if not base.zero_month else min(base.demand, base.capacity))
            sold_ok = math.floor(sold_ok) if not seg.fractional else round(sold_ok, 2)
            sold = sold_ok * (1 - p0)
            demand = base.demand
        else:
            sold, demand = s.sold, s.demand
        inc_cost = 0.0
        if incidents_on:
            inc_cost = incidents.expected_monthly_cost(seg, size, channel, rent=rules.monthly_rent(seg, loc, size, channel=channel, site_mode=site_mode),
                                                       relevance=rel, lease_age=n, payroll=payroll)
        revenue = sold * float(price)
        rev_d = D(str(round(revenue, 2)))
        tax = ctax.compute_taxes(seg.key.value, hint, ctax.annualize(history, rev_d), rev_d, ctax.annualize([payroll] * len(history), payroll),
                                 clt, purchases=D(str(round(sold * unit_cogs, 2))))
        history.append(rev_d)
        hint = tax.regime
        variable = (sold * unit_supply if service_supply else sold * unit_cogs + revenue * float(seg.variable_pct) / 100) + float(tax.total)
        profit = revenue - variable - fixed - float(payroll) - inc_cost
        cash += profit
        out.rows.append(SimMonth(n, rel, rep, demand, sold, revenue, variable, fixed + inc_cost, float(payroll), profit, cash, p0,
                                 taxes=float(tax.total), tax_regime=tax.regime, incidents=inc_cost))
        served_full = sold_ok >= math.floor(min(demand, s.capacity)) if expected else (s.sold >= math.floor(min(s.demand, s.capacity)))
        new_rel_ok = rules.next_relevance(rel, sold=max(sold_ok if expected else s.sold, 0), demand=demand, reputation=int(round(rep)),
                                          marketing=mk, stockout=False, price_ratio=ratio, irregular=False)
        if expected:
            new_rel_zero = rules.next_relevance(rel, sold=0, demand=demand, reputation=int(round(rep)), marketing=mk, stockout=False,
                                                price_ratio=ratio, irregular=False)
            rel = (1 - p0) * new_rel_ok + p0 * new_rel_zero
            rep = (1 - p0) * rules.next_reputation(int(round(rep)), served=served_full, stockout=False, irregular=False) \
                + p0 * rules.next_reputation(int(round(rep)), served=False, stockout=False, irregular=False)
        else:
            rel = rules.next_relevance(rel, sold=s.sold, demand=demand, reputation=int(round(rep)), marketing=mk, stockout=False,
                                       price_ratio=ratio, irregular=False)
            rep = rules.next_reputation(int(round(rep)), served=(s.sold >= math.floor(min(s.demand, s.capacity))) and not s.zero_month,
                                        stockout=False, irregular=False)
    return out


def table(months: int = 36, **kw) -> list[SimResult]:
    return [simulate(k, months=months, **kw) for k in rules.SEGMENTS]


def brl(v: float) -> str:
    return f"{quantize_money(D(str(round(v, 2)))):,.0f}".replace(",", ".")
