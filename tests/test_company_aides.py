"""Marketeiro e gerente opcionais (baixo/médio/alto nível, briefing), prazos de abertura/obra e limite de 50 unidades."""
import datetime as dt
from decimal import Decimal

from backend.services import company_aides as aides
from backend.services import company_rules as rules
from backend.models import CompanySize
from tests.test_companies import C, close, create_ok, detail, key, rich  # noqa: F401

D = Decimal
NEW_RULES = True            # roda com a dificuldade e os prazos reais (ver conftest._legacy_economy)
REF = dt.date(2026, 11, 1)


def test_marketer_tiers_are_ordered_and_campaign_is_deterministic():
    chances = []
    for lv in aides.LEVELS:
        res = aides.campaign(lv, budget=D(5000), reference=D(5000), seed=1, company_id=1, ref=REF)
        assert res == aides.campaign(lv, budget=D(5000), reference=D(5000), seed=1, company_id=1, ref=REF)
        chances.append(res.chance)
    assert chances[0] < chances[1] < chances[2]
    low_budget = aides.campaign("HIGH", budget=D(250), reference=D(5000), seed=1, company_id=1, ref=REF)
    assert low_budget.chance < chances[2]
    assert aides.campaign("HIGH", budget=D(0), reference=D(5000), seed=1, company_id=1, ref=REF).outcome == "NONE"


def test_marketer_hit_rate_grows_with_level():
    def rate(lv):
        ok = sum(aides.campaign(lv, budget=D(5000), reference=D(5000), seed=7, company_id=i, ref=REF).outcome != "NONE" for i in range(400))
        return ok / 400
    assert rate("LOW") < rate("MID") < rate("HIGH")


def test_manager_rigor_drives_productivity_and_quits():
    assert aides.productivity_boost("HIGH", 100) > aides.productivity_boost("LOW", 100) > aides.productivity_boost("LOW", 0) > 1.0
    assert aides.quit_probability("LOW", 0) == 0
    assert aides.quit_probability("LOW", 100) > aides.quit_probability("LOW", 50) > 0
    assert aides.quit_probability("HIGH", 100) < aides.quit_probability("LOW", 100)


def test_briefing_validation():
    assert aides.build_briefing("MARKETER", {"monthly_budget": "1500"}) == {"monthly_budget": "1500.00"}
    assert aides.build_briefing("MANAGER", {"rigor": 80}) == {"rigor": 80}
    for kind, raw in (("MARKETER", {"monthly_budget": "-1"}), ("MANAGER", {"rigor": 101}), ("MANAGER", {"rigor": True})):
        try:
            aides.build_briefing(kind, raw)
        except ValueError:
            continue
        raise AssertionError(raw)


def test_opening_and_build_delays_and_unit_cap():
    assert rules.MAX_BRANCHES == 50 and rules.MAX_UNITS == 51
    assert rules.OPEN_MONTHS and rules.opening_months(CompanySize.SMALL, None) == 1 and rules.opening_months(CompanySize.LARGE, None) == 2
    assert rules.opening_months(CompanySize.SMALL, "BUY") == rules.BUILD_MONTHS == 3
    assert rules.unit_build_months(None, "RENT") == 1 and rules.unit_build_months(None, "BUY") == 3


def test_aide_api_hire_briefing_and_dismiss(client, rich):
    cid = create_ok(client, rich, staff=False, extra="300000")["company"]["id"]
    d = detail(client, rich, cid)
    assert d["opens_month"] is not None and set(d["aide_options"]) == {"marketer", "manager"}
    r = client.post(f"{C}/{cid}/aides/MARKETER", headers=rich, json={"level": "MID"})
    assert r.status_code == 200 and r.json()["aides"]["marketer"]["level"] == "MID"
    assert client.post(f"{C}/{cid}/aides/MARKETER", headers=rich, json={"level": "XX"}).status_code == 400
    r = client.put(f"{C}/{cid}/aides/MARKETER/briefing", headers=rich, json={"monthly_budget": "2500"})
    assert r.status_code == 200 and r.json()["aides"]["marketer"]["settings"]["monthly_budget"] == "2500.00"
    r = client.post(f"{C}/{cid}/aides/MANAGER", headers=rich, json={"level": "HIGH"})
    assert r.status_code == 200
    r = client.put(f"{C}/{cid}/aides/MANAGER/briefing", headers=rich, json={"rigor": 85})
    assert r.json()["aides"]["manager"]["productivity_pct"] > 0 and r.json()["aides"]["manager"]["quit_chance_pct"] > 0
    assert client.delete(f"{C}/{cid}/aides/MARKETER", headers=rich).json()["aides"]["marketer"] is None
    assert client.delete(f"{C}/{cid}/aides/MARKETER", headers=rich).status_code == 409
