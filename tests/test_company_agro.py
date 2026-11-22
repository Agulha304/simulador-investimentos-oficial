"""Segmento AGRIBUSINESS (Agronegócio): catálogo, canal só físico, cargos, fornecimento, sazonalidade, impostos, crises, expansão,
balanceamento e contratador."""
import datetime as dt
from decimal import Decimal

import pytest

from backend.services import company_balance as bal
from backend.services import company_expansion_data as xdata
from backend.services import company_rules as rules
from backend.services import company_taxes as taxes
from backend.services.engine import crises
from tests.test_companies import C, close, create, create_ok, detail, key, rich  # noqa: F401  (fixtures e helpers compartilhados)
from tests.test_company_recruiter import hire_rec, post

D = Decimal
AGRO = rules.CompanySegment.AGRIBUSINESS
SEG = rules.SEGMENTS[AGRO]


def test_catalog_has_agribusiness_physical_only_with_own_roles_supply_and_locations(client, rich):
    by = {s["key"]: s for s in client.get(f"{C}/catalog", headers=rich).json()["segments"]}
    a = by["AGRIBUSINESS"]
    assert a["label"] == "Agronegócio" and a["channels"] == ["PHYSICAL"] and a["metrics_kind"] == "PRODUCTION"
    specific = {r["key"] for r in a["roles"]} - {"accountant", "lawyer", "cleaner"}
    assert specific >= {"agronomist", "machine_operator", "farm_worker", "agri_technician", "zootechnician", "farm_manager"} and len(specific) >= 5
    cats = {c["key"]: c for c in a["supply_categories"]}
    assert set(cats) == {"sementes", "fertilizantes", "combustivel_maquinas", "racao"} and sum(D(c["weight"]) for c in cats.values()) == 1
    assert {l["label"] for l in a["locations"]} >= {"Zona rural (cerrado)", "Zona rural (sul)", "Polo agroindustrial", "Região de cooperativas"}
    assert a["default_location"] == "cerrado" and D(a["minimum_capital"]) > 0
    assert a["tax"]["annex"] == "I" and a["tax"]["mei_allowed"] is False


def test_online_agribusiness_is_rejected(client, rich):
    r = create(client, rich, name="Fazenda online", segment="AGRIBUSINESS", channel="ONLINE")
    assert r.status_code == 400 and "canal não permitido" in r.json()["detail"]
    assert client.post(f"{C}/quote", headers=rich, json={"segment": "AGRIBUSINESS", "channel": "ONLINE"}).status_code == 400
    assert create(client, rich, name="Fazenda", segment="AGRIBUSINESS", channel="PHYSICAL", location="cerrado").status_code == 201


def test_roles_salaries_and_supply_categories_are_consistent():
    assert all(r.salary > 0 and r.units > 0 for r in SEG.roles if r.key not in ("accountant", "lawyer", "cleaner"))
    assert set(SEG.initial_staff) <= {r.key for r in SEG.roles}
    assert SEG.needs_suppliers and SEG.has_stock and len(SEG.stock) == len(SEG.supply_categories) == 4
    assert all(c.ref_price > 0 and c.per_sale > 0 for c in SEG.supply_categories)
    cost = rules.supply_cost_per_sale(SEG)
    assert D("0.3") * SEG.price < cost < D("0.7") * SEG.price                   # insumos pesam, mas a venda a preço de mercado dá margem


def test_harvest_seasonality_is_strong_and_averages_one():
    curve = rules.SEASON_CURVE["AGRIBUSINESS"]
    assert len(curve) == 12 and abs(sum(curve) / 12 - 1) < 1e-9
    assert max(curve) / min(curve) >= 1.8                                         # pico de safra vs entressafra
    cur = lambda m: rules.season_curve(SEG, dt.date(2027, m, 1))                  # noqa: E731
    assert cur(4) > 1.3 > 1.0 > cur(11) and cur(4) > cur(11) * 1.8
    avg = lambda m: sum(rules.season_factor(SEG, cid, dt.date(2027, m, 1)) for cid in range(1, 80)) / 79   # noqa: E731
    assert avg(4) > avg(11) * 1.5                                                  # com o sorteio mensal por cima da curva
    other = rules.SEGMENTS[rules.CompanySegment.CAFE]
    assert rules.season_curve(other, dt.date(2027, 4, 1)) == 1.0                  # outros segmentos não mudam


def test_taxes_follow_the_documented_simplification():
    assert taxes.ANEXO_SEGMENTO["AGRIBUSINESS"] == "I" and not taxes.mei_allowed("AGRIBUSINESS")
    r = taxes.compute_taxes("AGRIBUSINESS", None, D("600000"), D("50000"), D("100000"), 3)
    assert r.regime == taxes.SIMPLES and r.annex == "I" and r.total > 0
    lp = taxes.compute_taxes("AGRIBUSINESS", taxes.LUCRO_PRESUMIDO, D("6000000"), D("500000"), D("1000000"), 20, purchases=D("200000"))
    names = [ln.name for ln in lp.lines]
    assert "ICMS" in names and "ISS" not in names and "IPI" not in names
    assert any("Agronegócio" in x for x in taxes.SIMPLIFICACOES)
    assert taxes.segment_tax_info("AGRIBUSINESS")["annex"] == "I"


def test_crises_hit_agribusiness_coherently():
    for t in ("SUPPLY", "INFLATION", "RECESSION", "DEBT"):
        assert crises.TYPES[t][4]["AGRIBUSINESS"] < 0, t
    assert crises.TYPES["SUPPLY"][4]["AGRIBUSINESS"] <= -10                       # a crise de oferta (fertilizantes/combustível) é a pior
    assert crises.TYPES["CURRENCY"][4]["AGRIBUSINESS"] > 0                        # dólar alto: exportação paga melhor


def test_expansion_pools_are_specific_to_agribusiness():
    for kind in ("CAPACITY", "NEW_UNIT", "QUALITY"):
        own = xdata.pool(kind, family="PRODUCTION", segment="AGRIBUSINESS")
        assert len(own) >= 8 and own != xdata.pool(kind, family="PRODUCTION", segment="CAFE"), kind
        assert len({o.key for o in own}) == len(own)
    camp = xdata.pool("MARKETING", family="PRODUCTION", segment="AGRIBUSINESS")
    assert len(camp) >= 6 and len({o.key for o in camp}) == len(camp)
    assert xdata.pool("LARGER_PREMISES", family="PRODUCTION", segment="AGRIBUSINESS") == xdata.LARGER


def test_balance_agribusiness_turns_profit_between_month_12_and_16_at_list_price():
    r = bal.simulate(AGRO, months=36)
    assert 12 <= r.turn_month <= 16, r.turn_month
    assert r.rows[0].profit < 0 and r.rows[-1].profit > 0 and r.min_cash > 0
    assert r.rows[11].tax_regime == "SIMPLES"
    slow = bal.simulate(AGRO, months=36, supplier_mult=1.07)                       # fornecedor 7% acima da referência atrasa a virada, sem quebrar
    assert slow.turn_month is not None and slow.turn_month >= r.turn_month and slow.min_cash > 0


def test_recruiter_contracts_mandatory_and_agribusiness_suppliers(client, rich):
    cid = create_ok(client, rich, staff=False, name="Fazenda Boa Safra", segment="AGRIBUSINESS", extra="500000")["company"]["id"]
    hire_rec(client, rich, cid, "ELITE", max_salary="20000")
    m = post(client, rich, cid, "hire-mandatory").json()
    assert m["hired"] and {h["role"] for h in m["hired"]} <= {"accountant", "lawyer", "cleaner"}
    out = post(client, rich, cid, "contract-suppliers").json()                    # sem nenhum critério: contrata o melhor custo-benefício
    assert {x["category"] for x in out["contracted"]} == {"sementes", "fertilizantes", "combustivel_maquinas", "racao"} and out["skipped"] == []
    d = detail(client, rich, cid)
    assert d["supply"]["required"] and all(x["present"] for x in d["supply"]["checklist"])
    assert {x["unit"] for x in out["contracted"]} == {"kg", "litro"}
