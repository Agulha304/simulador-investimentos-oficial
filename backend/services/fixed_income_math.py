"""Contas de renda fixa: funções PURAS (sem banco, sem rede), sempre em Decimal.

Convenções (mercado brasileiro):
  * prefixado e spread: (1 + taxa)^(dias úteis / 252);
  * % do CDI/Selic: produto diário de (1 + taxa_dia × %), nos dias úteis;
  * IPCA/IGP-M: correção mensal rateada por dias corridos × taxa real em dias úteis/252;
  * o dia da aplicação não rende; o dia final conta.

Simplificações assumidas e isoladas aqui (o simulador é educacional):
  * marcação a mercado = valor do resgate descontado pela taxa de mercado atual do mesmo título
    (só prefixado e IPCA+ sem cupom; demais produtos usam a curva contratada);
  * produtos com juros periódicos pagam, a cada data, os juros do período sobre o valor-base
    (a parte de inflação capitaliza no valor-base) e devolvem o principal no vencimento.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.core.calendar_br import add_months, business_days_between, next_business_day
from backend.core.money import quantize_money
from backend.models import Indexer, PaymentFrequency, RateMode, TaxRegime
from backend.services import tax_service
from backend.services.index_data import IndexData

D = Decimal
DAYS_PER_YEAR = D(252)
STEP_MONTHS = {PaymentFrequency.MONTHLY: 1, PaymentFrequency.SEMIANNUAL: 6, PaymentFrequency.ANNUAL: 12}
INDEX_OF = {Indexer.CDI: "CDI", Indexer.SELIC: "SELIC", Indexer.IPCA: "IPCA", Indexer.IGPM: "IGPM"}


@dataclass(frozen=True)
class Terms:
    indexer: Indexer
    rate_mode: RateMode
    rate: Decimal                       # em %
    maturity_date: date
    payment_frequency: PaymentFrequency
    tax_regime: TaxRegime
    uses_mtm: bool = False


@dataclass(frozen=True)
class Valuation:
    gross: Decimal
    method: str                         # CURVE | MTM


def _compound(rate_pct: Decimal, start: date, end: date) -> Decimal:
    """(1 + taxa)^(du/252) com du = dias úteis em (start, end]."""
    du = business_days_between(start, end)
    return (1 + rate_pct / 100) ** (D(du) / DAYS_PER_YEAR) if du else D(1)


def accrual_factors(t: Terms, idx: IndexData, start: date, end: date) -> tuple[Decimal, Decimal]:
    """(fator de inflação que capitaliza no valor-base, fator de juros). Produto = fator total."""
    from backend.models import IndexName
    if end <= start:
        return D(1), D(1)
    if t.indexer == Indexer.PRE:
        return D(1), _compound(t.rate, start, end)
    if t.indexer in (Indexer.CDI, Indexer.SELIC):
        name = IndexName[INDEX_OF[t.indexer]]
        if t.rate_mode == RateMode.PERCENT_OF_INDEX:
            return D(1), idx.daily_factor(name, start, end, t.rate / 100)
        return D(1), idx.daily_factor(name, start, end) * _compound(t.rate, start, end)
    if t.indexer in (Indexer.IPCA, Indexer.IGPM):
        if t.rate_mode != RateMode.SPREAD:
            raise ValueError("IPCA/IGP-M só aceitam taxa real (índice + taxa)")
        name = IndexName[INDEX_OF[t.indexer]]
        return idx.monthly_factor(name, start, end), _compound(t.rate, start, end)
    raise ValueError(f"indexador não suportado: {t.indexer}")


def value_as_of(t: Terms, base: Decimal, last_settlement: date, idx: IndexData, as_of: date,
                market_rate: Decimal | None = None) -> Valuation:
    """Valor bruto da aplicação em `as_of` (limitado ao vencimento)."""
    as_of = min(as_of, t.maturity_date)
    infl, rate = accrual_factors(t, idx, last_settlement, as_of)
    curve = Valuation(base * infl * rate, "CURVE")

    mtm_ok = (t.uses_mtm and market_rate is not None and as_of < t.maturity_date
              and t.payment_frequency == PaymentFrequency.AT_MATURITY
              and t.indexer in (Indexer.PRE, Indexer.IPCA, Indexer.IGPM))
    if not mtm_ok:
        return curve
    du_total = business_days_between(last_settlement, t.maturity_date)
    du_left = business_days_between(as_of, t.maturity_date)
    face = (1 + t.rate / 100) ** (D(du_total) / DAYS_PER_YEAR)             # valor de resgate (sem a inflação futura)
    discount = (1 + market_rate / 100) ** (D(du_left) / DAYS_PER_YEAR)
    return Valuation(base * infl * face / discount, "MTM")


def coupon_dates(applied_on: date, maturity: date, frequency: PaymentFrequency) -> list[date]:
    """Datas de pagamento de juros (antes do vencimento), em dias úteis."""
    step = STEP_MONTHS.get(frequency)
    if not step:
        return []
    dates: set[date] = set()
    k = 1
    while True:
        d = add_months(maturity, -k * step)
        if d <= applied_on:
            break
        d = next_business_day(d)
        if applied_on < d < maturity:
            dates.add(d)
        k += 1
    return sorted(dates)


def coupon_interest(t: Terms, base: Decimal, last_settlement: date, idx: IndexData, on: date) -> tuple[Decimal, Decimal]:
    """(juros brutos pagos, novo valor-base). A inflação do período capitaliza no valor-base."""
    infl, rate = accrual_factors(t, idx, last_settlement, on)
    new_base = base * infl
    return new_base * (rate - 1), new_base


@dataclass(frozen=True)
class Flow:
    on: date
    kind: str                            # COUPON | MATURITY
    gross: Decimal
    tax: Decimal
    net: Decimal


def simulate_cashflows(t: Terms, principal: Decimal, applied_on: date, idx: IndexData) -> list[Flow]:
    """Fluxo completo da aplicação mantida até o vencimento, com os índices atuais (e projeções)."""
    flows: list[Flow] = []
    base, last = principal, applied_on
    for c in coupon_dates(applied_on, t.maturity_date, t.payment_frequency):
        interest, base = coupon_interest(t, base, last, idx, c)
        gross = quantize_money(interest)
        tax = tax_service.redemption_tax(t.tax_regime, applied_on, c, gross).total_brl
        flows.append(Flow(c, "COUPON", gross, tax, gross - tax))
        last = c
    final = quantize_money(value_as_of(t, base, last, idx, t.maturity_date).gross)
    tax = tax_service.redemption_tax(t.tax_regime, applied_on, t.maturity_date, final - principal).total_brl
    flows.append(Flow(t.maturity_date, "MATURITY", final, tax, final - tax))
    return flows
