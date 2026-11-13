from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.core import calendar_br as cal
from backend.models import IndexName, Indexer, PaymentFrequency, RateMode, TaxRegime
from backend.services import fixed_income_math as fm
from backend.services import tax_service as tax
from backend.services.index_data import IndexData

D = Decimal
CLOSE = D("1e-9")


def terms(indexer=Indexer.PRE, mode=RateMode.FIXED, rate="12", maturity=date(2028, 1, 3),
          freq=PaymentFrequency.AT_MATURITY, regime=TaxRegime.REGRESSIVE, mtm=False):
    return fm.Terms(indexer, mode, D(rate), maturity, freq, regime, mtm)


def flat_index(cdi="0.05", ipca="0.5", until=date(2027, 12, 31)) -> IndexData:
    days = list(cal.iter_business_days(date(2025, 12, 31), until))
    months = {date(y, m, 1): D(ipca) for y in (2025, 2026, 2027) for m in range(1, 13)}
    return IndexData(daily={IndexName.CDI: {d: D(cdi) for d in days}, IndexName.SELIC: {d: D(cdi) for d in days}},
                     monthly={IndexName.IPCA: months},
                     fallback_daily={IndexName.CDI: D("0.05"), IndexName.SELIC: D("0.05")},
                     fallback_monthly={IndexName.IPCA: D("0.5"), IndexName.IGPM: D("0.5")})


def date_after_business_days(start: date, n: int) -> date:
    d = start
    for d in cal.iter_business_days(start, start + timedelta(days=int(n * 1.6) + 15)):
        n -= 1
        if n == 0:
            return d
    raise AssertionError


# ------------------------------------------------------------------ calendário

def test_calendar_known_dates():
    assert cal.easter(2026) == date(2026, 4, 5)
    h = cal.holidays(2026)
    assert {date(2026, 2, 16), date(2026, 2, 17), date(2026, 4, 3), date(2026, 6, 4), date(2026, 11, 20)} <= h
    assert not cal.is_business_day(date(2026, 11, 14)) and cal.is_business_day(date(2026, 11, 13))
    assert cal.next_business_day(date(2026, 11, 15)) == date(2026, 11, 16)
    assert cal.add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)
    for s, e in [(date(2025, 1, 2), date(2026, 1, 2)), (date(2026, 11, 13), date(2031, 3, 1))]:
        assert cal.business_days_between(s, e) == len(list(cal.iter_business_days(s, e)))


# ------------------------------------------------------------------ prefixado / CDI / IPCA

def test_prefixed_252_business_days_is_exactly_the_rate():
    start = date(2026, 1, 5)
    end = date_after_business_days(start, 252)
    assert cal.business_days_between(start, end) == 252
    t = terms(maturity=end)
    v = fm.value_as_of(t, D(1000), start, flat_index(), end)
    assert abs(v.gross - D(1120)) < D("1e-6") and v.method == "CURVE"


def test_percent_of_cdi_and_cdi_plus_spread():
    idx = flat_index()
    start, end = date(2026, 1, 5), date(2026, 4, 1)
    n = cal.business_days_between(start, end)
    full = fm.value_as_of(terms(Indexer.CDI, RateMode.PERCENT_OF_INDEX, "100", end), D(1000), start, idx, end).gross
    assert abs(full - 1000 * D("1.0005") ** n) < CLOSE
    pct110 = fm.value_as_of(terms(Indexer.CDI, RateMode.PERCENT_OF_INDEX, "110", end), D(1000), start, idx, end).gross
    assert abs(pct110 - 1000 * D("1.00055") ** n) < CLOSE
    spread = fm.value_as_of(terms(Indexer.CDI, RateMode.SPREAD, "2", end), D(1000), start, idx, end).gross
    assert abs(spread - 1000 * D("1.0005") ** n * D("1.02") ** (D(n) / 252)) < CLOSE


def test_cdi_projection_after_last_known_day_keeps_last_rate():
    idx = flat_index(until=date(2026, 3, 2))               # dados só até março
    start, end = date(2026, 1, 5), date(2026, 6, 1)
    n = cal.business_days_between(start, end)
    v = fm.value_as_of(terms(Indexer.CDI, RateMode.PERCENT_OF_INDEX, "100", end), D(1000), start, idx, end).gross
    assert abs(v - 1000 * D("1.0005") ** n) < CLOSE        # dado + projeção = mesma taxa constante
    assert abs(idx.annual_rate(IndexName.CDI) - ((D("1.0005") ** 252 - 1) * 100)) < D("1e-6")


def test_ipca_full_months_and_real_rate():
    idx = flat_index()
    assert abs(idx.monthly_factor(IndexName.IPCA, date(2026, 1, 31), date(2026, 2, 28)) - D("1.005")) < CLOSE
    assert abs(idx.monthly_factor(IndexName.IPCA, date(2026, 1, 31), date(2026, 3, 31)) - D("1.005") ** 2) < CLOSE
    # 2026-01-01 -> 2026-03-01: 30 dias de jan (2..31), 28 de fev, 1 de mar
    expected = D("1.005") ** (D(30) / 31) * D("1.005") * D("1.005") ** (D(1) / 31)
    assert abs(idx.monthly_factor(IndexName.IPCA, date(2026, 1, 1), date(2026, 3, 1)) - expected) < CLOSE

    start, end = date(2026, 1, 5), date(2026, 9, 1)
    t = terms(Indexer.IPCA, RateMode.SPREAD, "6", end)
    infl, rate = fm.accrual_factors(t, idx, start, end)
    assert abs(rate - D("1.06") ** (D(cal.business_days_between(start, end)) / 252)) < CLOSE
    assert infl > 1 and abs(fm.value_as_of(t, D(1000), start, idx, end).gross - 1000 * infl * rate) < CLOSE


def test_ipca_rejects_percent_of_index():
    with pytest.raises(ValueError):
        fm.accrual_factors(terms(Indexer.IPCA, RateMode.PERCENT_OF_INDEX, "100"), flat_index(), date(2026, 1, 5), date(2026, 6, 1))


# ------------------------------------------------------------------ marcação a mercado

def test_mtm_prefixed_follows_market_rate():
    idx, start, mid, end = flat_index(), date(2026, 1, 5), date(2026, 7, 1), date(2027, 7, 1)
    t = terms(maturity=end, mtm=True)
    curve = fm.value_as_of(t, D(1000), start, idx, mid)                       # sem taxa de mercado -> curva
    assert curve.method == "CURVE"
    same = fm.value_as_of(t, D(1000), start, idx, mid, market_rate=D("12"))   # mesma taxa -> mesma conta
    assert same.method == "MTM" and abs(same.gross - curve.gross) < D("1e-6")
    up = fm.value_as_of(t, D(1000), start, idx, mid, market_rate=D("15"))
    down = fm.value_as_of(t, D(1000), start, idx, mid, market_rate=D("9"))
    assert up.gross < curve.gross < down.gross                                # juros sobem -> preço cai
    at_maturity = fm.value_as_of(t, D(1000), start, idx, end, market_rate=D("20"))
    assert at_maturity.method == "CURVE"                                      # no vencimento vale a curva


def test_mtm_ipca_and_no_mtm_for_coupon_bonds():
    idx, start, mid, end = flat_index(), date(2026, 1, 5), date(2026, 7, 1), date(2027, 12, 1)
    t = terms(Indexer.IPCA, RateMode.SPREAD, "6", end, mtm=True)
    curve = fm.value_as_of(t, D(1000), start, idx, mid)
    same = fm.value_as_of(t, D(1000), start, idx, mid, market_rate=D("6"))
    assert abs(same.gross - curve.gross) < D("1e-6")
    assert fm.value_as_of(t, D(1000), start, idx, mid, market_rate=D("8")).gross < curve.gross
    paying = terms(Indexer.IPCA, RateMode.SPREAD, "6", end, freq=PaymentFrequency.SEMIANNUAL, mtm=True)
    assert fm.value_as_of(paying, D(1000), start, idx, mid, market_rate=D("9")).method == "CURVE"


# ------------------------------------------------------------------ cupons

def test_coupon_dates_are_business_days_inside_the_period():
    applied, maturity = date(2026, 11, 13), date(2029, 5, 15)
    ds = fm.coupon_dates(applied, maturity, PaymentFrequency.SEMIANNUAL)
    assert len(ds) == 5 and ds == sorted(set(ds)) and all(cal.is_business_day(d) for d in ds)
    assert all(applied < d < maturity for d in ds) and ds[0] == date(2026, 11, 16)    # 15/11 é domingo
    assert fm.coupon_dates(applied, maturity, PaymentFrequency.AT_MATURITY) == []
    monthly = fm.coupon_dates(date(2026, 1, 5), date(2026, 7, 6), PaymentFrequency.MONTHLY)
    assert len(monthly) == 6 and monthly[0] == date(2026, 1, 6) and monthly[-1] == date(2026, 6, 8)   # 06/06 é sábado


def test_cashflow_conservation_for_paying_prefixed():
    idx = flat_index()
    applied, maturity = date(2026, 1, 5), date(2027, 7, 1)
    t = terms(rate="10", maturity=maturity, freq=PaymentFrequency.SEMIANNUAL, regime=TaxRegime.EXEMPT)
    flows = fm.simulate_cashflows(t, D(1000), applied, idx)
    assert [f.kind for f in flows] == ["COUPON", "MATURITY"] + [] if len(flows) == 2 else True
    dates = [applied] + fm.coupon_dates(applied, maturity, t.payment_frequency) + [maturity]
    expected = sum(1000 * ((D("1.10") ** (D(cal.business_days_between(a, b)) / 252)) - 1) for a, b in zip(dates, dates[1:]))
    total_interest = sum(f.gross for f in flows[:-1]) + (flows[-1].gross - 1000)
    assert abs(total_interest - expected) < D("0.02")                         # só arredondamento de centavos
    assert all(f.tax == 0 and f.net == f.gross for f in flows)               # isento


def test_inflation_capitalizes_into_base_when_paying_coupons():
    idx = flat_index()
    applied, maturity = date(2026, 1, 5), date(2027, 7, 1)
    t = terms(Indexer.IPCA, RateMode.SPREAD, "6", maturity, PaymentFrequency.SEMIANNUAL, TaxRegime.EXEMPT)
    flows = fm.simulate_cashflows(t, D(1000), applied, idx)
    assert flows[-1].gross > 1000                      # principal devolvido corrigido pela inflação
    assert flows[0].gross < D(1000) * (D("1.06") ** (D(1) / 2) - 1) * D("1.05")  # cupom só traz a taxa real


# ------------------------------------------------------------------ impostos

@pytest.mark.parametrize("days,rate", [(1, "0.225"), (180, "0.225"), (181, "0.20"), (360, "0.20"),
                                       (361, "0.175"), (720, "0.175"), (721, "0.15"), (3000, "0.15")])
def test_ir_brackets(days, rate):
    assert tax.ir_rate_for(days) == D(rate)


def test_iof_table_and_combined_tax():
    assert tax.iof_rate_for(1) == D("0.96") and tax.iof_rate_for(29) == D("0.03") and tax.iof_rate_for(30) == 0
    a = date(2026, 1, 1)
    r = tax.redemption_tax(TaxRegime.REGRESSIVE, a, a + timedelta(days=10), D("100"))
    assert (r.iof_brl, r.ir_brl, r.total_brl) == (D("66.00"), D("7.65"), D("73.65"))     # IOF 66%; IR 22,5% de 34
    r = tax.redemption_tax(TaxRegime.REGRESSIVE, a, a + timedelta(days=400), D("100"))
    assert (r.iof_brl, r.ir_brl) == (D("0.00"), D("17.50"))
    assert tax.redemption_tax(TaxRegime.EXEMPT, a, a + timedelta(days=5), D("100")).total_brl == 0
    assert tax.redemption_tax(TaxRegime.REGRESSIVE, a, a + timedelta(days=5), D("-10")).total_brl == 0
