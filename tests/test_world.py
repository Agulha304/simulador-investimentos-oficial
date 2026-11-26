"""Mundo: países e câmbio, faculdades reais, intercâmbio, vagas no exterior, empresas e equipes internacionais, compra de empresas."""
from datetime import date
from decimal import Decimal

from backend.services import company_acquisition as acq
from backend.services import company_world as cw
from backend.services import country_rules as cr
from backend.services import exchange_rules as xr
from backend.services import university_rules as ur
from backend.services import world_service as ws
from tests.test_companies import C, close, create_ok, detail, key, rich  # noqa: F401

NEW_RULES = True
D = Decimal
REF = date(2026, 11, 1)


# ------------------------------------------------------------------ países e câmbio
def test_world_economy_is_simulated_deterministic_and_has_crises():
    from backend.services import world_economy as we
    assert len(cr.COUNTRIES) >= 19 and cr.COUNTRIES["BR"].currency == "BRL"
    for c in cr.COUNTRIES.values():
        assert c.fx0 > 0 and c.cost_index > 0 and cr.living_local(c.code)["total"] > 0
    far = date(2031, 11, 1)
    assert we.fx(5, "AR", far) == we.fx(5, "AR", far) and we.fx(5, "AR", far) < cr.COUNTRIES["AR"].fx0 * 0.6       # inflação alta: moeda perde valor
    assert we.fx(5, "US", far) != we.fx(6, "US", far)                                                              # cada partida tem o seu mundo
    assert we.state(5, "AR", far)["infl"] != we.state(6, "AR", far)["infl"]
    assert we.state(5, "BR", date(2026, 11, 1))["fx"] == 1.0 and we.state(5, "US", date(2026, 11, 1))["fx"] == cr.COUNTRIES["US"].fx0
    crises = [c for sd in range(1, 9) for c in we.crises(sd, date(2034, 11, 1))]
    assert len(crises) >= 20 and {c.kind for c in crises} >= {"CURRENCY", "RECESSION", "INFLATION"}
    assert any(c.code == "*" for c in crises)                                                                      # há crises globais
    pl = [we.price_level(5, "AR", date(2026 + (10 + m) // 12, (10 + m) % 12 + 1, 1)) for m in (0, 12, 36)]
    assert pl[0] == 1.0 and pl[1] > 1.2 and pl[2] > pl[1] > pl[0]                                                  # preços sobem com a inflação simulada


def test_global_panic_hits_emerging_markets_harder_than_safe_havens():
    from backend.services import world_economy as we
    drops_em, drops_haven, n = [], [], 0
    for sd in range(1, 40):
        w = we.world(sd)
        w.at(date(2034, 11, 1))
        for c in w.crises:
            if c.kind == "FINANCIAL_PANIC" and c.code == "*" and c.end <= date(2034, 11, 1):
                a, b = c.start, c.end
                for code, bucket in (("MX", drops_em), ("AR", drops_em), ("CH", drops_haven), ("JP", drops_haven)):
                    bucket.append(w.state[b][code]["fx"] / w.state[a][code]["fx"] - 1)
                n += 1
    assert n >= 2 and sum(drops_em) / len(drops_em) < sum(drops_haven) / len(drops_haven)


def test_economy_countries_tab(client, auth_headers):
    r = client.get("/api/economy/countries", headers=auth_headers)
    assert r.status_code == 200, r.text
    rows = {x["code"]: x for x in r.json()["countries"]}
    assert {"BR", "US", "PT", "JP", "AR"} <= set(rows) and D(rows["US"]["rate"]) > 1
    assert len(rows["US"]["history"]) == 24 and rows["BR"]["history"] == []
    assert rows["US"]["vat"] == 7.0 and rows["PT"]["corp_tax"] == 21.0
    assert {"growth", "interest", "price_level", "demand", "crisis", "confidence"} <= set(rows["AR"])
    assert isinstance(r.json()["events"], list)


# ------------------------------------------------------------------ faculdades
def test_universities_catalog_is_real_and_offers_only_real_courses():
    assert {"usp", "unicamp", "ufrgs", "ufmg", "ufrj", "unesp", "ufsc", "unb", "ufpr", "ufscar", "ita", "ime", "fgv", "insper", "puc-rio", "pucrs", "mackenzie"} <= set(ur.UNIVERSITIES)
    ita, usp, fgv = ur.UNIVERSITIES["ita"], ur.UNIVERSITIES["usp"], ur.UNIVERSITIES["fgv"]
    assert not ur.offers_field(ita, "saude") and not ur.offers_field(ita, "direito") and ur.offers_field(usp, "saude")
    assert not ur.offers_field(fgv, "saude") and ur.offers_field(fgv, "direito")
    assert ur.monthly_cost(usp, "tecnologia", 1100) < 600 < ur.monthly_cost(fgv, "financas", 1000)       # pública ~só custos; FGV ~R$ 7,9 mil
    assert ur.admission_chance(ita, 40) < ur.admission_chance(ur.UNIVERSITIES["mackenzie"], 40) < ur.admission_chance(ur.UNIVERSITIES[ur.OPEN_KEY], 40) == 1.0
    assert ur.points_for(usp, 35) > 35 > ur.points_for(ur.UNIVERSITIES["mackenzie"], 30) - 10
    assert ur.months_for(usp, "saude", 60) == 72


def test_university_api_and_vestibular(client, rich):
    r = client.get("/api/life/universities?field=tecnologia", headers=rich)
    assert r.status_code == 200, r.text
    unis = {u["key"]: u for u in r.json()["universities"]}
    assert "usp" in unis and "ita" in unis and unis["usp"]["fields"][0]["chance"] < 1 and unis[ur.OPEN_KEY]["fields"][0]["chance"] == 1.0
    assert "mackenzie" in unis and "saude" not in {f["field"] for f in unis["ita"]["fields"]}
    assert client.post("/api/life/degree", headers=rich, json={"field": "saude", "uni": "ita"}).status_code == 400          # ITA não tem Medicina
    first = client.post("/api/life/degree", headers=rich, json={"field": "tecnologia", "uni": "ita"})
    assert first.status_code == 200, first.text
    adm = first.json()["admission"]
    if adm["admitted"]:
        assert first.json()["career"]["studying"]["uni"] == "ita"
    else:                                                                  # reprovado: o vestibular é anual
        again = client.post("/api/life/degree", headers=rich, json={"field": "tecnologia", "uni": "ita"})
        assert again.status_code == 409 and "reprovado" in again.json()["detail"]
        ok = client.post("/api/life/degree", headers=rich, json={"field": "tecnologia", "uni": ur.OPEN_KEY})
        assert ok.status_code == 200 and ok.json()["admission"]["admitted"] is True


# ------------------------------------------------------------------ intercâmbio e morar fora
def test_exchange_catalog_matches_countries_and_costs_scale_with_fx():
    assert all(p.country in cr.COUNTRIES for p in xr.PROGRAMS.values()) and len({p.country for p in xr.PROGRAMS.values()}) >= 15
    assert xr.PROGRAMS["ch-eth"].months == 6 and cr.COUNTRIES["CH"].cost_index > cr.COUNTRIES["PT"].cost_index


def test_exchange_flow_costs_and_resume_points(client, rich):
    r = client.get("/api/life/abroad", headers=rich)
    assert r.status_code == 200, r.text
    ab = r.json()
    assert ab["country"] == "BR" and ab["exchange"] is None and len(ab["programs"]) == len(xr.PROGRAMS)
    es = next(p for p in ab["programs"] if p["key"] == "es-espanhol")
    assert D(es["cost"]["upfront"]["total"]) > 0 and D(es["cost"]["living_month"]["total"]) > 0 and es["cost"]["currency"] == "EUR"
    r = client.post("/api/life/exchange", headers=rich, json={"program_key": "es-espanhol"})
    assert r.status_code == 200, r.text
    assert r.json()["country"] == "ES" and r.json()["exchange"]["months"] == 3
    assert client.post("/api/life/exchange", headers=rich, json={"program_key": "fr-francais"}).status_code == 409
    assert client.post("/api/life/move-abroad", headers=rich, json={"country": "PT"}).status_code in (400, 409)
    for _ in range(3):
        assert close(client, rich).status_code == 200
    back = client.get("/api/life/abroad", headers=rich).json()
    assert back["country"] == "BR" and back["exchange"] is None and back["done"][0]["status"] == "DONE"


def test_move_abroad_and_return(client, rich):
    r = client.post("/api/life/move-abroad", headers=rich, json={"country": "PT"})
    assert r.status_code == 200, r.text
    assert r.json()["country"] == "PT" and D(r.json()["result"]["upfront"]["total"]) > 0
    assert client.post("/api/life/move-abroad", headers=rich, json={"country": "DE"}).status_code == 409
    assert client.post("/api/life/degree", headers=rich, json={"field": "tecnologia"}).status_code == 409       # faculdade brasileira exige morar no Brasil
    assert client.post("/api/life/return-home", headers=rich).json()["country"] == "BR"
    assert client.post("/api/life/return-home", headers=rich).status_code == 409


# ------------------------------------------------------------------ vagas por país e remoto
def test_jobs_abroad_are_paid_in_local_currency_and_onsite_requires_moving(client, rich):
    r = client.get("/api/career/offers?field=tecnologia&country=US", headers=rich)
    assert r.status_code == 200, r.text
    offers = r.json()["offers"]
    assert offers and all(o["country"] == "US" and o["intl"]["currency"] == "USD" for o in offers)
    assert all((o["work_mode"] == "REMOTE") != o["needs_move"] for o in offers)
    br = client.get("/api/career/offers?field=tecnologia&country=BR", headers=rich).json()["offers"]
    assert all(o["work_mode"] in ("REMOTE", "ONSITE") and "intl" not in o for o in br)
    assert client.get("/api/career/offers?field=tecnologia&country=XX", headers=rich).status_code in (400, 422)


# ------------------------------------------------------------------ empresas e equipes internacionais
def test_company_abroad_quote_taxes_and_factor(client, rich):
    base = client.post(f"{C}/quote", headers=rich, json={"segment": "TECH", "size": "SMALL"}).json()
    us = client.post(f"{C}/quote", headers=rich, json={"segment": "TECH", "size": "SMALL", "country": "US"}).json()
    pt = client.post(f"{C}/quote", headers=rich, json={"segment": "TECH", "size": "SMALL", "country": "PT"}).json()
    assert D(us["minimum_capital"]) > D(pt["minimum_capital"]) > D(base["minimum_capital"])
    assert us["currency"] == "USD" and us["vat"] == 7.0 and us["corp_tax"] == 25.0 and us["open_months"] == base["open_months"] + 1
    assert client.post(f"{C}/quote", headers=rich, json={"segment": "TECH", "country": "XX"}).status_code == 400
    ft = cw.foreign_taxes("PT", D(100000), D(20000))
    assert ft.total > 0 and any("lucro" in ln[0] for ln in ft.lines)


def test_remote_roles_and_foreign_staff_rules():
    assert cw.can_be_remote("dev") and cw.can_be_remote("accountant")
    assert not cw.can_be_remote("waiter") and not cw.can_be_remote("broker") and not cw.can_be_remote("cook")
    assert cw.REMOTE_FACTOR["dev"] > 1 > cw.REMOTE_FACTOR["seller"]

    class C_:
        country = "BR"
    assert cw.validate_hire(C_, "dev", "REMOTE", "US") == ("REMOTE", "US")
    for role, mode, ctry in (("waiter", "REMOTE", "BR"), ("dev", "ONSITE", "US")):
        try:
            cw.validate_hire(C_, role, mode, ctry)
        except ValueError:
            continue
        raise AssertionError((role, mode, ctry))
    assert cw.wage_scale("US") > 1 > cw.wage_scale("AR")


def test_hire_remote_foreign_employee_via_api(client, rich):
    cid = create_ok(client, rich, staff=False, extra="500000", segment="TECH")["company"]["id"]
    loc = client.post(f"{C}/{cid}/candidates", headers=rich, json={"role": "dev", "regime": "PJ"}).json()["candidates"][0]
    us = client.post(f"{C}/{cid}/candidates", headers=rich, json={"role": "dev", "regime": "PJ", "country": "US"}).json()["candidates"][0]
    assert us["can_remote"] and us["remote_effect_pct"] > 0 and D(us["asking_salary"]) > D(loc["asking_salary"]) * 2          # salário de mercado dos EUA
    body = {"salary": us["asking_salary"], "hours_week": us["hours_week"], "schedule": us["schedule"], "regime": "PJ", "idempotency_key": key(),
            "candidate_id": us["id"], "confirm_risk": True}
    bad = client.post(f"{C}/{cid}/hire", headers=rich, json={**body, "work_mode": "ONSITE", "country": "US"})
    assert bad.status_code == 400 and "presencial" in bad.json()["detail"]
    ok = client.post(f"{C}/{cid}/hire", headers=rich, json={**body, "idempotency_key": key(), "work_mode": "REMOTE", "country": "US"})
    assert ok.status_code == 200, ok.text
    emp = [e for e in detail(client, rich, cid)["employees"] if e["country"] == "US"]
    assert emp and emp[0]["work_mode"] == "REMOTE" and emp[0]["country_name"] == "Estados Unidos"
    waiter_cid = create_ok(client, rich, staff=False, extra="300000", segment="RESTAURANT", name="Cantina do Mundo")["company"]["id"]
    w = client.post(f"{C}/{waiter_cid}/candidates", headers=rich, json={"role": "waiter", "regime": "CLT"}).json()["candidates"][0]
    assert w["can_remote"] is False
    r = client.post(f"{C}/{waiter_cid}/hire", headers=rich, json={"salary": w["asking_salary"], "hours_week": w["hours_week"], "schedule": w["schedule"],
                    "regime": "CLT", "idempotency_key": key(), "candidate_id": w["id"], "work_mode": "REMOTE", "confirm_risk": True})
    assert r.status_code == 400 and "remoto" in r.json()["detail"]


# ------------------------------------------------------------------ compra de empresas
def test_acquisition_negotiation_rules_are_pure_and_fair():
    ask, reserve = 1_000_000.0, 880_000.0
    assert acq.evaluate(ask, ask, reserve, 0, 0, 0.9)["status"] == "ACCEPT"
    assert acq.evaluate(reserve, ask, reserve, 0, 0, 0.9)["status"] == "ACCEPT"
    assert acq.evaluate(reserve * 0.95, ask, reserve, 0, 0, 0.9)["status"] == "COUNTER"
    assert acq.evaluate(reserve * 0.7, ask, reserve, 0, 0, 0.9)["status"] == "REFUSE"
    assert acq.evaluate(reserve * 0.3, ask, reserve, 0, 0, 0.9)["status"] == "REFUSE"
    assert acq.evaluate(reserve * 0.3, ask, reserve, 1, 1, 0.9)["status"] == "WALK"                       # 2ª oferta ofensiva
    assert acq.evaluate(reserve * 0.8, ask, reserve, 0, 0, 0.01)["status"] == "WALK"                      # outro comprador
    t = acq.make_target(7, REF, 0)
    assert t == acq.make_target(7, REF, 0) and t["valuation"] > 0 and t["ask"] > t["valuation"] > t["_reserve"] * 0.9


def test_acquisition_sizes_cover_small_medium_and_large():
    sizes = {acq.make_target(3, REF, i)["size"] for i in range(60)}
    assert sizes == {"SMALL", "MEDIUM", "LARGE"}


def test_acquisition_api_negotiate_and_keep(client, rich):
    r = client.get(f"{C}/acquisitions", headers=rich)
    assert r.status_code == 200, r.text
    ls = r.json()["listings"]
    assert len(ls) == acq.LISTINGS and all("_reserve" not in x for x in ls)
    small = next(x for x in ls if x["size"] == "SMALL" and float(x["ask_now"]) < 3_000_000)
    k = small["key"]
    low = client.post(f"{C}/acquisitions/negotiate", headers=rich, json={"target_key": k, "offer": "1000", "mode": "KEEP"})
    assert low.status_code == 200 and low.json()["status"] == "REFUSE"
    low2 = client.post(f"{C}/acquisitions/negotiate", headers=rich, json={"target_key": k, "offer": "1000", "mode": "KEEP"})
    assert low2.json()["status"] == "WALKED"
    again = client.post(f"{C}/acquisitions/negotiate", headers=rich, json={"target_key": k, "offer": "9999999", "mode": "KEEP"})
    assert again.status_code == 409
    other = next(x for x in ls if x["key"] != k and x["size"] == "SMALL" and float(x["ask_now"]) < 3_000_000)
    ok = client.post(f"{C}/acquisitions/negotiate", headers=rich, json={"target_key": other["key"], "offer": other["ask_now"], "mode": "KEEP"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "ACCEPTED" and ok.json()["company_id"]
    d = detail(client, rich, ok.json()["company_id"])
    assert d["company"]["country"] == other["country"] and d["employees"] and float(d["company"]["relevance"]) > 0


def test_acquisition_merge_requires_same_segment_and_country(client, rich):
    mine = create_ok(client, rich, staff=False, extra="300000", segment="CAFE")["company"]
    ls = client.get(f"{C}/acquisitions", headers=rich).json()["listings"]
    other = next(x for x in ls if x["segment"] != "CAFE" or x["country"] != "BR")
    r = client.post(f"{C}/acquisitions/negotiate", headers=rich, json={"target_key": other["key"], "offer": "100000", "mode": "MERGE", "buyer_company_id": mine["id"]})
    assert r.status_code == 400 and "mesmo segmento" in r.json()["detail"]
    assert client.post(f"{C}/acquisitions/negotiate", headers=rich, json={"target_key": other["key"], "offer": "100000", "mode": "MERGE"}).status_code == 400
