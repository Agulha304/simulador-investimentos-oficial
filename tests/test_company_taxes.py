"""Impostos reais das empresas (fase 3b): `backend/services/company_taxes.py` (funções puras, sem banco)."""
from decimal import Decimal

import pytest

from backend.services import company_taxes as t

D = Decimal


def eff(anexo, rbt12):
    return t.effective_rate(anexo, D(rbt12))


# ---------------------------------------------------------------- Simples: alíquota efetiva (contas à mão)
@pytest.mark.parametrize("anexo,rbt12,esperado", [
    ("I", 100_000, "0.04"),                     # faixa 1: nominal
    ("I", 360_000, "0.0565"),                   # (360000*7,3% - 5940) / 360000
    ("I", 500_000, "0.06728"),                  # (500000*9,5% - 13860) / 500000
    ("I", 1_000_000, "0.0845"),                 # (1M*10,7% - 22500) / 1M
    ("I", 2_000_000, "0.09935"),                # (2M*14,3% - 87300) / 2M
    ("I", 4_800_000, "0.11125"),                # (4,8M*19% - 378000) / 4,8M
    ("II", 150_000, "0.045"),
    ("II", 2_000_000, "0.10425"),               # (2M*14,7% - 85500) / 2M
    ("II", 4_000_000, "0.12"),                  # (4M*30% - 720000) / 4M
    ("III", 240_000, "0.073"),                  # (240000*11,2% - 9360) / 240000
    ("III", 4_000_000, "0.168"),                # (4M*33% - 648000) / 4M
    ("IV", 800_000, "0.090275"),                # (800000*14% - 39780) / 800000
    ("IV", 200_000, "0.0495"),                  # (200000*9% - 8100) / 200000
    ("V", 100_000, "0.155"),
    ("V", 2_400_000, "0.204125"),               # (2,4M*23% - 62100) / 2,4M
])
def test_simples_effective_rate_by_hand(anexo, rbt12, esperado):
    assert eff(anexo, rbt12) == D(esperado)


@pytest.mark.parametrize("anexo", ["I", "II", "III", "IV", "V"])
def test_simples_every_band_formula_and_continuity(anexo):
    """No limite superior de cada faixa vale a fórmula e a faixa seguinte começa logo acima."""
    for i, (lim, aliq, ded) in enumerate(t.SIMPLES_FAIXAS[anexo], start=1):
        assert t.simples_faixa(anexo, lim)[0] == i
        assert t.simples_faixa(anexo, lim + D("0.01"))[0] == i + 1 if i < 6 else True
        e = eff(anexo, lim)
        assert e == (lim * aliq - ded) / lim
    with pytest.raises(ValueError):
        t.simples_faixa(anexo, D("4800000.01"))


def test_das_is_revenue_times_effective_rate():
    r = t.compute_taxes("RESTAURANT", t.SIMPLES, D(500_000), D(40_000), D(150_000), 5)
    assert r.regime == t.SIMPLES and r.annex == "I" and r.effective_pct == D("6.7280")
    assert [ln.name for ln in r.lines] == ["DAS"] and r.total == D("2691.20")           # 40000 x 6,728%
    assert r.lines[0].base == D("40000.00") and r.lines[0].rate_pct == D("6.7280")


def test_anexo_by_segment():
    esperado = {"RESTAURANT": "I", "CAFE": "I", "CLOTHING": "I", "SUPERMARKET": "I", "ECOMMERCE": "I", "INDUSTRY": "II",
                "WORKSHOP": "III", "TRANSPORT": "III", "REAL_ESTATE_AGENCY": "III", "CONSTRUCTION": "IV"}
    for seg, anexo in esperado.items():
        r = t.compute_taxes(seg, t.SIMPLES, D(500_000), D(40_000), D(200_000), 4)
        assert r.annex == anexo, seg


# ---------------------------------------------------------------- Fator R
def test_fator_r_switches_between_anexo_iii_and_v():
    com = t.compute_taxes("TECH", t.SIMPLES, D(480_000), D(40_000), D(144_000), 4)          # 30% >= 28%
    assert com.annex == "III" and com.fator_r == D("0.3000") and com.effective_pct == D("9.8250")
    sem = t.compute_taxes("AGENCY", t.SIMPLES, D(480_000), D(40_000), D(100_000), 4)        # 20,8% < 28%
    assert sem.annex == "V" and sem.effective_pct == D("17.4375") and sem.total > com.total
    limite = t.compute_taxes("TECH", t.SIMPLES, D(480_000), D(40_000), D(134_400), 4)       # exatamente 28%
    assert limite.annex == "III"
    assert t.simples_annex("TECH", D(0), D(0)) == ("V", D(0))


# ---------------------------------------------------------------- MEI
def test_mei_fixed_das_by_activity_and_even_without_revenue():
    com = t.compute_taxes("CAFE", None, D(60_000), D(5_000), D(0), 1)
    assert com.regime == t.MEI and com.total == D("82.05") and com.lines[0].name == "DAS-MEI"
    srv = t.compute_taxes("WORKSHOP", None, D(60_000), D(5_000), D(0), 0)
    assert srv.regime == t.MEI and srv.total == D("86.05")
    zero = t.compute_taxes("TECH", None, D(0), D(0), D(0), 0)
    assert zero.regime == t.MEI and zero.total == D("86.05")                                # fixo mesmo sem faturamento
    assert t.compute_taxes("TRANSPORT", None, D(200_000), D(16_000), D(0), 1).total == D("195.52")   # MEI Caminhoneiro


def test_mei_restrictions_move_company_to_simples():
    assert t.compute_taxes("CAFE", None, D(81_000), D(6_750), D(0), 1).regime == t.MEI             # limite inclusivo
    assert t.compute_taxes("CAFE", None, D(81_001), D(6_750), D(0), 1).regime == t.SIMPLES         # > R$ 81 mil/ano
    assert t.compute_taxes("CAFE", None, D(10_000), D(800), D(0), 2).regime == t.SIMPLES           # > 1 empregado
    for seg in ("SUPERMARKET", "INDUSTRY", "CONSTRUCTION", "REAL_ESTATE_AGENCY"):                 # atividades fora do MEI
        assert t.compute_taxes(seg, None, D(10_000), D(800), D(0), 0).regime == t.SIMPLES, seg
    assert t.compute_taxes("CAFE", t.SIMPLES, D(10_000), D(800), D(0), 0).regime == t.SIMPLES     # nunca rebaixa para MEI
    assert t.compute_taxes("CAFE", t.MEI, D(10_000), D(800), D(0), 0).regime == t.MEI              # já era MEI e continua elegível
    assert t.compute_taxes("CAFE", t.LUCRO_PRESUMIDO, D(10_000), D(800), D(0), 0).regime == t.SIMPLES


# ---------------------------------------------------------------- Lucro Presumido
def test_automatic_switch_to_lucro_presumido_above_4_8m():
    assert t.compute_taxes("RESTAURANT", t.SIMPLES, D(4_800_000), D(400_000), D(0), 9).regime == t.SIMPLES
    assert t.compute_taxes("RESTAURANT", t.SIMPLES, D("4800000.01"), D(400_000), D(0), 9).regime == t.LUCRO_PRESUMIDO
    assert t.compute_taxes("CAFE", t.MEI, D(5_000_000), D(400_000), D(0), 0).regime == t.LUCRO_PRESUMIDO


def test_lucro_presumido_commerce_by_hand():
    r = t.compute_taxes("RESTAURANT", t.SIMPLES, D(4_900_000), D(400_000), D(0), 9, purchases=D(100_000))
    by = {ln.name: ln for ln in r.lines}
    assert by["IRPJ"].amount == D("4800.00") and by["IRPJ"].base == D("32000.00")           # 400000 x 8% x 15%
    assert by["Adicional de IRPJ"].amount == D("1200.00")                                   # (32000 - 20000) x 10%
    assert by["CSLL"].amount == D("4320.00")                                                # 400000 x 12% x 9%
    assert by["PIS"].amount == D("2600.00") and by["COFINS"].amount == D("12000.00")        # 0,65% e 3%
    assert by["ICMS"].amount == D("54000.00") and by["ICMS"].base == D("300000.00")         # 18% x (receita - compras)
    assert "ISS" not in by and "IPI" not in by
    assert r.total == D("78920.00") == sum((ln.amount for ln in r.lines), D(0))


def test_irpj_additional_only_above_20k_month_of_presumed_profit():
    # serviços: presunção 32%. Receita de 62.500 => base 20.000 (sem adicional); 100.000 => base 32.000 (adicional de 1.200)
    abaixo = t.compute_taxes("TECH", t.SIMPLES, D(5_000_000), D(62_500), D(0), 9)
    assert "Adicional de IRPJ" not in {ln.name for ln in abaixo.lines}
    acima = t.compute_taxes("TECH", t.SIMPLES, D(5_000_000), D(100_000), D(0), 9)
    adic = {ln.name: ln for ln in acima.lines}["Adicional de IRPJ"]
    assert adic.base == D("12000.00") and adic.amount == D("1200.00")
    assert {ln.name: ln for ln in acima.lines}["CSLL"].amount == D("2880.00")               # 100000 x 32% x 9%


def test_lc224_presumption_increase_only_on_revenue_above_5m():
    r = t.compute_taxes("RESTAURANT", t.SIMPLES, D(6_000_000), D(500_000), D(0), 9)
    by = {ln.name: ln for ln in r.lines}
    assert by["IRPJ"].base == D("40666.67")             # 500000 x 8% x (1 + 10% x 1/6)
    assert by["Adicional de IRPJ"].base == D("20666.67")
    assert r.notes
    sem = t.compute_taxes("RESTAURANT", t.SIMPLES, D(5_000_000), D(500_000), D(0), 9)
    assert {ln.name: ln for ln in sem.lines}["IRPJ"].base == D("40000.00") and not sem.notes


def test_iss_icms_ipi_by_segment_type():
    def names(seg):
        return {ln.name: ln for ln in t.compute_taxes(seg, t.SIMPLES, D(5_000_000), D(400_000), D(0), 9, purchases=D(100_000)).lines}
    for seg in ("TECH", "AGENCY", "WORKSHOP", "CONSTRUCTION"):                              # serviços: ISS (3%), sem ICMS/IPI
        n = names(seg)
        assert n["ISS"].amount > 0 and "ICMS" not in n and "IPI" not in n, seg
    assert names("TECH")["ISS"].amount == D("12000.00") and names("REAL_ESTATE_AGENCY")["ISS"].amount == D("16000.00")   # 3% e 4%
    for seg in ("RESTAURANT", "CAFE", "CLOTHING", "SUPERMARKET", "ECOMMERCE"):              # comércio: ICMS, sem ISS/IPI
        n = names(seg)
        assert "ICMS" in n and "ISS" not in n and "IPI" not in n, seg
    ind = names("INDUSTRY")
    assert ind["ICMS"].amount == D("54000.00") and ind["IPI"].amount == D("30000.00") and "ISS" not in ind   # 18% / 10% de 300 mil
    tr = names("TRANSPORT")
    assert tr["ICMS"].amount == D("27000.00") and tr["ISS"].amount == D("6000.00")          # metade intermunicipal (ICMS) e metade ISS 3%
    assert all(t.ISS_MIN <= t.ISS_TIPICO[s] <= t.ISS_MAX for s in t.ISS_TIPICO)             # ISS entre 2% e 5%


def test_annualize_prorating_rules():
    assert t.annualize([], D(1000)) == D(12000)                                  # 1º mês: receita do mês x 12
    assert t.annualize([D(100), D(300)], D(9999)) == D(2400)                     # média dos meses anteriores x 12
    assert t.annualize([D(i) for i in range(1, 15)], D(0)) == D(sum(range(3, 15)))      # 12 ou mais: soma dos últimos 12


def test_deterministic_and_breakdown_json():
    a = t.compute_taxes("CLOTHING", t.SIMPLES, D(720_000), D(60_000), D(0), 3)
    assert a == t.compute_taxes("CLOTHING", t.SIMPLES, D(720_000), D(60_000), D(0), 3)
    assert a.breakdown() == [{"name": "DAS", "base": "60000.00", "rate_pct": str(a.lines[0].rate_pct), "amount": str(a.total)}]
    info = t.segment_tax_info("RESTAURANT")
    assert info["annex"] == "I" and info["mei_allowed"] and info["effective_min_pct"] == D("4.0000")
    assert t.segment_tax_info("TECH")["annex"] == "III/V" and not t.segment_tax_info("INDUSTRY")["mei_allowed"]
