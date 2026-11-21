"""Orçamento da carteira de investimentos: valor recomendado, perfil de investidor (teste), carteira-alvo editável e progresso por tipo."""
from decimal import Decimal

import pytest

from tests.conftest import credit
from tests.test_budget import B, second_user
from tests.test_engine import _mk_world
from tests.test_life_v3 import _free_world

D = Decimal
P = "/api/invest-plan"


def plan(client, h):
    r = client.get(P, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_default_plan_has_a_balanced_target_portfolio_and_a_recommended_amount(client, auth_headers):
    g, h = _mk_world(client, auth_headers, scenario="young_pro")
    j = plan(client, h)
    assert j["profile"] == "MODERATE" and [r["key"] for r in j["rows"]] == ["FIXED", "STOCKS", "ETF", "FII", "CRYPTO"]
    assert sum(r["target_pct"] for r in j["rows"]) == pytest.approx(100.0)
    rec = j["recommended"]
    assert D(rec["amount"]) > 0 and D(rec["surplus"]) > D(rec["amount"]) and rec["reason"]
    assert sum(D(r["month_amount"]) for r in j["rows"]) == pytest.approx(float(D(rec["amount"])), abs=0.05)
    assert D(j["goal_total"]) > 0


def test_investor_quiz_defines_the_profile_and_reshapes_the_portfolio(client, auth_headers):
    g, h = _mk_world(client, auth_headers)
    q = client.get(f"{P}/quiz", headers=h).json()["questions"]
    assert len(q) == 8 and all(len(x["options"]) == 4 for x in q)
    cons = client.post(f"{P}/quiz", headers=h, json={"answers": [0] * 8}).json()
    assert cons["profile"] == "CONSERVATIVE" and cons["quiz_score"] == 8 and {r["key"]: r["target_pct"] for r in cons["rows"]}["FIXED"] == 70
    aggr = client.post(f"{P}/quiz", headers=h, json={"answers": [3] * 8}).json()
    assert aggr["profile"] == "AGGRESSIVE" and {r["key"]: r["target_pct"] for r in aggr["rows"]}["STOCKS"] == 45
    mid = client.post(f"{P}/quiz", headers=h, json={"answers": [2] * 8}).json()
    assert mid["profile"] == "MODERATE"
    assert D(aggr["recommended"]["amount"]) > D(cons["recommended"]["amount"])                    # perfil arrojado investe mais da sobra
    assert client.post(f"{P}/quiz", headers=h, json={"answers": [0] * 3}).status_code == 400
    assert client.post(f"{P}/quiz", headers=h, json={"answers": [9] * 8}).status_code == 400


def test_what_you_want_to_invest_in_changes_the_allocation(client, auth_headers):
    g, h = _mk_world(client, auth_headers)
    j = client.put(P, headers=h, json={"wanted": ["STOCKS"]}).json()
    alloc = {r["key"]: r["target_pct"] for r in j["rows"]}
    assert alloc["CRYPTO"] == alloc["FII"] == alloc["ETF"] == 0 and alloc["FIXED"] + alloc["STOCKS"] == pytest.approx(100.0) and alloc["STOCKS"] > 0
    j = client.put(P, headers=h, json={"wanted": ["STOCKS", "FII", "ETF", "CRYPTO"], "profile": "CONSERVATIVE"}).json()
    assert {r["key"]: r["target_pct"] for r in j["rows"]}["FIXED"] == 70 and j["profile"] == "CONSERVATIVE"
    assert client.put(P, headers=h, json={"wanted": ["OURO"]}).status_code == 400
    assert client.put(P, headers=h, json={"profile": "LOUCO"}).status_code == 400


def test_portfolio_is_editable_and_must_sum_to_one_hundred(client, auth_headers):
    g, h = _mk_world(client, auth_headers)
    r = client.put(P, headers=h, json={"alloc": {"FIXED": 50, "STOCKS": 30, "ETF": 10, "FII": 5, "CRYPTO": 5}})
    assert r.status_code == 200 and r.json()["customized"] is True and {x["key"]: x["target_pct"] for x in r.json()["rows"]}["STOCKS"] == 30
    assert client.put(P, headers=h, json={"alloc": {"FIXED": 50, "STOCKS": 30}}).status_code == 400            # soma 80
    assert client.put(P, headers=h, json={"alloc": {"FIXED": 150, "STOCKS": -50}}).status_code == 400
    assert plan(client, h)["customized"] is True
    assert client.put(P, headers=h, json={"profile": "AGGRESSIVE"}).json()["customized"] is False            # mudar o perfil refaz a carteira


def test_progress_by_type_shows_what_is_missing_and_prioritises_the_lagging_class(client, auth_headers, assets):
    credit(client, auth_headers, "300000")
    g, h = _mk_world(client, auth_headers, scenario="young_pro")
    client.put(P, headers=h, json={"goal_total": "200000", "wanted": ["STOCKS", "ETF", "FII", "CRYPTO"], "profile": "AGGRESSIVE"})
    r = client.post("/api/trades/buy", headers=h, json={"asset_id": assets["PETR4"].id, "quantity": "200"})
    assert r.status_code == 201, r.text
    j = plan(client, h)
    rows = {x["key"]: x for x in j["rows"]}
    assert D(j["goal_total"]) == D("200000.00") and j["goal_is_custom"] is True
    assert D(rows["STOCKS"]["target_amount"]) == D("90000.00")                                                 # 45% de 200 mil
    assert D(rows["STOCKS"]["current"]) > 0 and D(rows["STOCKS"]["missing"]) == D(rows["STOCKS"]["target_amount"]) - D(rows["STOCKS"]["current"])
    assert 0 < rows["STOCKS"]["filled_pct"] < 100 and D(rows["FIXED"]["current"]) == 0 and rows["FIXED"]["filled_pct"] == 0
    if not j["recommended"]["reserve_mode"]:
        assert rows["FIXED"]["month_pct"] > rows["STOCKS"]["month_pct"] * 0.2                                    # o que está mais atrasado recebe mais


def test_reserve_comes_first_and_budget_without_surplus_recommends_nothing(client, auth_headers):
    g, h = _free_world(client, auth_headers, cash=3000, income=3500, expenses=2600, rent=0, name="Reserva baixa")
    j = plan(client, h)
    assert j["recommended"]["reserve_mode"] is True and "reserva" in j["recommended"]["reason"]
    assert {r["key"]: r["month_pct"] for r in j["rows"]}["FIXED"] == 100.0
    assert D(j["recommended"]["amount"]) == (D(j["recommended"]["surplus"]) * D("0.70")).quantize(D("0.01"))
    g2, h2 = _free_world(client, auth_headers, cash=40000, income=2000, expenses=1900, rent=0, name="Sem sobra", seed=2)
    client.post(f"{B}/items", headers=h2, json={"name": "Gasto fixo", "kind": "EXPENSE", "category_id": next(c["id"] for c in client.get(f"{B}/categories", headers=h2).json() if c["name"] == "Outros"),
                                                 "planned_amount": "500", "recurring": True})
    k = plan(client, h2)
    assert D(k["recommended"]["amount"]) == 0 and "sobra" in k["recommended"]["reason"]


def test_apply_recommendation_sets_the_months_planned_investment(client, auth_headers):
    g, h = _mk_world(client, auth_headers, scenario="young_pro")
    before = client.get(f"{B}/overview", headers=h).json()["month"]["planned_investment"]
    j = client.post(f"{P}/apply", headers=h).json()
    assert D(j["planned_investment"]) == D(j["recommended"]["amount"]) > 0
    after = client.get(f"{B}/overview", headers=h).json()["month"]["planned_investment"]
    assert D(after) == D(j["recommended"]["amount"]) and D(after) != D(before)


def test_invest_plan_is_private_to_each_game(client, auth_headers):
    g, h = _mk_world(client, auth_headers)
    client.post(f"{P}/quiz", headers=h, json={"answers": [3] * 8})
    g2, h2 = _mk_world(client, auth_headers, seed=9)
    assert plan(client, h2)["profile"] == "MODERATE" and plan(client, h)["profile"] == "AGGRESSIVE"
    assert client.get(P).status_code in (401, 403)


def test_career_can_start_at_eighteen(client, auth_headers):
    g = client.post("/api/games", headers=auth_headers, json={"kind": "LIFE", "name": "Jovem"}).json()
    h = {**auth_headers, "X-Game-Id": str(g["id"])}
    r = client.post("/api/game/start", headers=h, json={"mode": "CAREER", "scenario": "investor", "seed": 1, "age": 18})
    assert r.status_code == 200, r.text
    j = client.get("/api/life", headers=h).json()
    assert j["character"]["age_years"] == 18
    fam = {x["role"]: x for x in j["relationships"] if x["role"]}
    assert fam["MOTHER"]["age"] >= 18 + 22 and fam["FATHER"]["age"] >= 18 + 24                                      # pais coerentes com a idade
    g2 = client.post("/api/games", headers=auth_headers, json={"kind": "LIFE", "name": "Inválido"}).json()
    assert client.post("/api/game/start", headers={**auth_headers, "X-Game-Id": str(g2["id"])}, json={"mode": "CAREER", "scenario": "investor", "age": 17}).status_code == 422


# ---------------------------------------------------------------- renda passiva desejada e acompanhamento do mês
def _buy(client, db, h, symbol, qty):
    from sqlalchemy import select

    from backend.models import Asset
    a = db.scalar(select(Asset).where(Asset.symbol == symbol))
    r = client.post("/api/trades/buy", headers=h, json={"asset_id": a.id, "quantity": str(qty)})
    assert r.status_code == 201, r.text


def test_passive_income_goal_defines_the_capital_needed_and_an_estimate(client, auth_headers):
    g, h = _mk_world(client, auth_headers, scenario="young_pro")
    base = plan(client, h)
    assert base["goal_from_passive"] is False and base["passive"]["required_capital"] is None
    j = client.put(P, headers=h, json={"passive_goal": "1000"}).json()
    # carteira moderada: 40% renda fixa (10%), 15% FII (9%), 15% ETF (4%), 25% ações (5%), 5% cripto (0%) = 7,2% a.a. de renda
    assert j["passive"]["yield_pct"] == pytest.approx(7.2) and j["goal_from_passive"] is True
    assert D(j["passive"]["required_capital"]) == D("166666.67") == D(j["goal_total"])
    assert j["passive"]["months_to_goal"] is None or j["passive"]["months_to_goal"] > 0
    assert D(j["passive"]["income_now"]) >= 0
    assert client.put(P, headers=h, json={"passive_goal": "0"}).json()["goal_from_passive"] is False     # 0 limpa
    assert client.put(P, headers=h, json={"passive_goal": "-5"}).status_code == 422


def test_conservative_profile_needs_more_capital_than_aggressive_for_the_same_income(client, auth_headers):
    g, h = _mk_world(client, auth_headers)
    # a renda por classe é a mesma premissa; o que muda é a carteira-alvo do perfil
    cons = client.put(P, headers=h, json={"profile": "CONSERVATIVE", "passive_goal": "1000"}).json()["passive"]
    aggr = client.put(P, headers=h, json={"profile": "AGGRESSIVE", "passive_goal": "1000"}).json()["passive"]
    assert cons["yield_pct"] > aggr["yield_pct"] and D(cons["required_capital"]) < D(aggr["required_capital"])


def test_monthly_nudge_shrinks_as_you_invest_and_the_budget_adapts(client, auth_headers, db):
    g, h = _mk_world(client, auth_headers, scenario="young_pro")
    assert client.patch(f"{B}/months/current", headers=h, json={"planned_investment": "1000.00"}).status_code == 200
    n = plan(client, h)["nudge"]
    assert n["active"] is True and n["done"] is False and D(n["remaining"]) == D("1000.00") and D(n["invested"]) == 0
    m0 = client.get(f"{B}/overview", headers=h).json()["month"]
    assert D(m0["invest_remaining"]) == D("1000.00") and m0["invest_done"] is False
    assert D(m0["free_after_investment"]) == D(m0["projected_closing_balance"]) - D("1000.00")

    _buy(client, db, h, "PETR4", 10)                                   # R$ 400 em ações
    n = plan(client, h)["nudge"]
    assert D(n["invested"]) == D("400.00") and D(n["remaining"]) == D("600.00") and n["active"] is True
    m1 = client.get(f"{B}/overview", headers=h).json()["month"]
    assert D(m1["invest_remaining"]) == D("600.00")
    assert D(m1["free_after_investment"]) == D(m1["projected_closing_balance"]) - D("600.00")    # só desconta o que falta

    client.patch(f"{B}/months/current", headers=h, json={"planned_investment": "300.00"})          # já passou do planejado
    n = plan(client, h)["nudge"]
    assert n["done"] is True and n["active"] is False and D(n["remaining"]) == 0
    m2 = client.get(f"{B}/overview", headers=h).json()["month"]
    assert m2["invest_done"] is True and D(m2["invest_remaining"]) == 0
    assert D(m2["free_after_investment"]) == D(m2["projected_closing_balance"])


def test_nudge_splits_the_month_by_class(client, auth_headers, db):
    g, h = _mk_world(client, auth_headers, scenario="young_pro")
    client.put(P, headers=h, json={"profile": "AGGRESSIVE"})
    client.patch(f"{B}/months/current", headers=h, json={"planned_investment": "2000.00"})
    n = plan(client, h)["nudge"]
    rows = {r["key"]: r for r in n["rows"]}
    assert sum(D(r["target"]) for r in n["rows"]) == pytest.approx(2000.0, abs=0.06)
    if not n["reserve_mode"]:
        _buy(client, db, h, "PETR4", 10)
        after = {r["key"]: r for r in plan(client, h)["nudge"]["rows"]}
        assert D(after["STOCKS"]["invested"]) == D("400.00")
        assert D(after["STOCKS"]["remaining"]) == max(D(rows["STOCKS"]["target"]) - D("400.00"), D(0))
        assert D(after["FIXED"]["invested"]) == 0
