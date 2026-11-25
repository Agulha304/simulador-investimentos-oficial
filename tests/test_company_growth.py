"""Franquias, abertura de capital, obras/escritura de imóveis, prazos e mais conteúdo (carreira e decisões)."""
import uuid
from decimal import Decimal

from backend.models import CompanySize
from backend.services import career_hub_rules as hub
from backend.services import career_rules, company_franchise as fr, company_ipo as ipo
from backend.services import company_rules as rules
from backend.services import economy_events as ev
from backend.services import goods_rules as grules
from tests.test_companies import C, close, create_ok, detail, key, rich  # noqa: F401
from tests.test_goods import G, cash

NEW_RULES = True
D = Decimal


# ------------------------------------------------------------------ franquias
def test_franchise_is_hard_and_only_for_known_brands():
    assert fr.interest_probability(100, 20, 90) == 0.0                 # marca pouco relevante: ninguém procura
    assert fr.interest_probability(0, 80, 60) < 0.02                    # sem publicidade quase nunca
    best = fr.interest_probability(100, 100, 100)
    assert best <= 0.12 and best > fr.interest_probability(40, 80, 60) > fr.interest_probability(0, 80, 60)


def test_franchise_pays_much_less_than_a_branch():
    sold, price = 1000.0, D(100)
    assert fr.royalty(sold, price, 1.0) < D(100000) * D("0.08")        # royalty ~6% do faturamento da franquia, bem abaixo do lucro de uma filial


def test_franchise_ad_requires_relevant_brand(client, rich):
    cid = create_ok(client, rich, staff=False, extra="300000")["company"]["id"]
    r = client.post(f"{C}/{cid}/franchise/advertise", headers=rich, json={"tier": "MEDIO", "idempotency_key": key()})
    assert r.status_code == 409 and "desconhecida" in r.json()["detail"] or r.status_code == 409
    d = detail(client, rich, cid)
    assert d["franchise"]["open"] == 0 and d["franchise"]["units_cap"] == rules.MAX_UNITS


# ------------------------------------------------------------------ IPO
def test_ipo_math_and_gates(client, rich):
    assert ipo.pe_multiple(100) > ipo.pe_multiple(0) == 8.0
    price = ipo.next_price(D(10), D(20), noise_u=0.5, sentiment=0.0)
    assert D(10) < price < D(20)                                          # puxa para o valor justo sem chegar de uma vez
    assert ipo.next_price(D("0.02"), D(0), noise_u=0.0, sentiment=-1.0) >= D("0.01")
    cid = create_ok(client, rich, staff=False, extra="300000")["company"]["id"]
    d = detail(client, rich, cid)
    assert d["ipo"]["eligibility"]["ok"] is False and d["ipo"]["listing"] is None
    r = client.post(f"{C}/{cid}/ipo", headers=rich, json={"float_pct": "25", "idempotency_key": key()})
    assert r.status_code == 409 and "ainda não pode abrir capital" in r.json()["detail"]
    assert client.post(f"{C}/{cid}/ipo", headers=rich, json={"float_pct": "60", "idempotency_key": key()}).status_code in (400, 422)


# ------------------------------------------------------------------ obras e escritura
def test_build_catalog_and_construction_delay(client, rich):
    cat = client.get(f"{G}/build/catalog", headers=rich).json()
    assert {p["key"] for p in cat["plans"]} == set(grules.BUILD_PLANS) and cat["closing_months"] == {"cash": 1, "financed": 2}
    assert all(3 <= p["months"] <= 6 for p in cat["plans"])
    before = cash(client, rich)
    r = client.post(f"{G}/build", headers=rich, json={"plan_key": "casa-media", "city_key": "bh", "idempotency_key": uuid.uuid4().hex})
    assert r.status_code == 201, r.text
    g = r.json()["good"]
    assert g["construction_plan"] == "casa-media" and g["available_month"] is not None
    assert before - cash(client, rich) >= grules.build_quote("casa-media", "bh")["total"]
    # em obra: não pode vender nem alugar
    assert client.post(f"{G}/{g['id']}/sell", headers=rich, json={}).status_code == 409
    assert client.post(f"{G}/{g['id']}/occupancy", headers=rich, json={"mode": "RENTED", "monthly_rent": "2000"}).status_code in (409, 422)


def test_building_is_slower_than_buying_and_pricier_plans_take_longer():
    assert grules.BUILD_PLANS["mansao"].months > grules.BUILD_PLANS["casa-popular"].months >= 3
    assert grules.CLOSING_MONTHS_FINANCED > grules.CLOSING_MONTHS_CASH >= 1


# ------------------------------------------------------------------ mercado mais difícil e prazos
def test_market_is_harder_and_company_waits_to_open(client, rich):
    assert rules.MARKET_DIFFICULTY < 1
    d0 = create_ok(client, rich, staff=False, extra="300000")
    assert detail(client, rich, d0["company"]["id"])["opens_month"] is not None


# ------------------------------------------------------------------ conteúdo
def test_more_fields_courses_and_decisions():
    assert len(career_rules.FIELDS) >= 14
    assert set(career_rules.FIELDS) == set(hub.LADDER) == set(hub.GIG_TITLES) - {"geral"}
    assert all(v[1] == "geral" or v[1] in career_rules.FIELDS for v in hub.COURSES.values())
    assert len(ev.MONTHLY) >= 40 and len({d.key for d in ev.MONTHLY}) == len(ev.MONTHLY)
    for d in ev.MONTHLY:
        for o in d.options:
            assert abs(sum(x.prob for x in o.outcomes) - 1) < 1e-6, (d.key, o.key)
