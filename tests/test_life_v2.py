"""Vida pessoal v2: nomes e profissões variados, sexo, compatibilidade por convivência, carreira/faculdade e decisões mensais."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import BudgetItem, LifeProfile, RecurringItem, RecurringItemVersion, Relationship, SimMonth, WorldEvent
from backend.services import career_rules, economy_events as E, life_rules as R, life_service
from tests.conftest import credit
from tests.test_budget import B
from tests.test_engine import _advance, _mk_world
from tests.test_life import arrange_partner, life, uid

D = Decimal
L = "/api/life"
EC = "/api/economy"


def _profile(client, h):
    u = uid(client, h)
    with SessionLocal() as s:
        return s.scalar(select(LifeProfile).where(LifeProfile.user_id == u))


# ------------------------------------------------------------------ nomes, sexo e profissões

def test_people_have_varied_names_both_genders_and_many_professions(client, auth_headers):
    client.put(f"{L}/character", headers=auth_headers, json={"name": "Eu", "age_years": 30})
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        p = s.scalar(select(LifeProfile).where(LifeProfile.user_id == u))
        people = [life_service._generate_person(s, p, date(2026, 1, 1), i, None) for i in range(1, 121)]
        names = [x.name for x in people]
        assert len(set(names)) > 105 and all(" " in n for n in names)                      # nome e sobrenome, quase sem repetição
        assert {x.gender for x in people} == {"M", "F"} and 0.35 < sum(1 for x in people if x.gender == "F") / len(people) < 0.65
        assert len({x.occupation for x in people}) >= 30
        fem = [x for x in people if x.gender == "F"]
        assert any(x.occupation in ("Professora", "Médica", "Engenheira civil", "Advogada") for x in fem)
        assert not any(x.occupation == "Professor" for x in fem)                          # profissão no feminino para elas
        assert len({n.split()[0] for n in names}) > 60
        s.rollback()


def test_user_chooses_gender_and_who_to_meet(client, auth_headers):
    r = client.put(f"{L}/character", headers=auth_headers, json={"name": "Ana", "age_years": 28, "gender": "F", "interested_in": "M"})
    assert r.status_code == 200 and r.json()["character"]["gender"] == "F" and r.json()["character"]["interested_in"] == "M"
    assert client.put(f"{L}/character", headers=auth_headers, json={"name": "A", "gender": "Z"}).status_code == 400
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        p = s.scalar(select(LifeProfile).where(LifeProfile.user_id == u))
        assert {life_service._generate_person(s, p, date(2026, 1, 1), i, None).gender for i in range(1, 40)} == {"M"}
        p.interested_in = "ANY"
        assert {life_service._generate_person(s, p, date(2026, 1, 1), i, None).gender for i in range(100, 140)} == {"M", "F"}
        s.rollback()


def test_career_start_sets_gender_and_field(client, auth_headers):
    g, h = _mk_world(client, auth_headers)
    # o fluxo normal já cria o mundo; refaz com sexo e área escolhidos
    g2 = client.post("/api/games", headers=auth_headers, json={"kind": "LIFE", "name": "Escolhas"}).json()
    h2 = {**auth_headers, "X-Game-Id": str(g2["id"])}
    r = client.post("/api/game/start", headers=h2, json={"mode": "CAREER", "scenario": "young_pro", "seed": 1, "gender": "F",
                                                         "interested_in": "M", "career_field": "tecnologia"})
    assert r.status_code == 200, r.text
    j = life(client, h2)
    assert j["character"]["gender"] == "F" and j["career"]["field"] == "tecnologia" and len(j["career"]["fields"]) == 17
    assert client.post("/api/game/start", headers={**auth_headers, "X-Game-Id": str(client.post("/api/games", headers=auth_headers, json={"kind": "LIFE", "name": "x"}).json()["id"])},
                       json={"mode": "CAREER", "scenario": "young_pro", "career_field": "nao_existe"}).status_code == 400


# ------------------------------------------------------------------ atividades e compatibilidade

def test_there_are_many_more_social_activities(client, auth_headers):
    acts = life(client, auth_headers)["activities"]
    keys = {a["key"] for a in acts}
    assert len(acts) >= 24 and {"cinema", "book_club", "dance_class", "team_sport", "hiking", "charity_event", "board_games", "concert"} <= keys
    assert len({R.ACTIVITIES[k]["interest"] for k in R.ACTIVITIES}) >= 8


def test_compatibility_grows_with_activities_done_together(client, auth_headers):
    credit(client, auth_headers, "300000")
    pid = arrange_partner(client, auth_headers, stage="FRIEND", affinity=40, trust=40)
    base = next(x for x in life(client, auth_headers)["relationships"] if x["person_id"] == pid)
    assert base["compat_bonus"] == 0
    seen = [base["compatibility"]]
    for _ in range(4):
        r = client.post(f"{L}/people/{pid}/interact", headers=auth_headers, json={"key": "chat"})
        assert r.status_code == 200, r.text
        seen.append(next(x for x in r.json()["relationships"] if x["person_id"] == pid)["compatibility"])
    assert seen[-1] > seen[0] and seen == sorted(seen)
    assert next(x for x in life(client, auth_headers)["relationships"] if x["person_id"] == pid)["compat_bonus"] == 4
    # atividade ligada a um interesse dela(e) rende mais (Camila gosta de "viagens" e "cultura")
    r = client.post(f"{L}/people/{pid}/interact", headers=auth_headers, json={"key": "movie"})
    assert next(x for x in r.json()["relationships"] if x["person_id"] == pid)["compat_bonus"] == 6


def test_compatibility_bonus_is_capped(client, auth_headers):
    pid = arrange_partner(client, auth_headers, stage="FRIEND")
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        rel = s.scalar(select(Relationship).where(Relationship.person_id == pid))
        rel.compat_bonus = R.COMPAT_BONUS_CAP - 1
        s.commit()
    credit(client, auth_headers, "100000")
    client.post(f"{L}/people/{pid}/interact", headers=auth_headers, json={"key": "movie"})
    assert next(x for x in life(client, auth_headers)["relationships"] if x["person_id"] == pid)["compat_bonus"] == R.COMPAT_BONUS_CAP


# ------------------------------------------------------------------ decisão do mês (antes do resumo do fechamento)

def _decisions(client, h):
    r = client.get(f"{EC}/decisions", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["pending"]


def test_every_month_has_one_decision_before_closing_with_hidden_outcomes(client, auth_headers):
    g, h = _mk_world(client, auth_headers, seed=8)
    pend = _decisions(client, h)
    assert pend and pend[0]["key"] in E.MONTHLY_BY_KEY and pend[0]["options"] and "effects" not in pend[0]
    assert all(set(o) == {"key", "label", "hint", "cost"} for o in pend[0]["options"])          # resultados não são revelados
    assert _decisions(client, h) == pend                                                       # consultar de novo não cria outra
    seen, cats = [pend[0]["key"]], [pend[0]["category"]]
    for _ in range(5):
        _advance(client, h, 1)                                                                 # sem responder: vale a opção padrão
        p = _decisions(client, h)
        assert p and p[0]["key"] in E.MONTHLY_BY_KEY
        seen.append(p[0]["key"]); cats.append(p[0]["category"])
    assert len(set(seen)) == len(seen), "não repete decisão em meses seguidos"
    assert set(cats) == {"FINANCIAL", "PERSONAL"} and all(cats[i] != cats[i + 1] for i in range(len(cats) - 1))


def test_deciding_applies_cost_and_outcome_to_the_budget(client, auth_headers):
    g, h = _mk_world(client, auth_headers, seed=8)
    dec = _decisions(client, h)[0]
    costly = next((o for o in dec["options"] if o["cost"] > 0), dec["options"][0])
    r = client.post(f"{EC}/events/{dec['id']}/decide", headers=h, json={"option": costly["key"]})
    assert r.status_code == 200 and r.json()["event"]["outcome"] and r.json()["event"]["status"] in ("ACTIVE", "ENDED")
    assert _decisions(client, h) == []                                                         # nada mais pendente: segue para o resumo
    u = uid(client, h)
    with SessionLocal() as s:
        items = list(s.scalars(select(BudgetItem).where(BudgetItem.user_id == u, BudgetItem.source_key.like(f"econ:{dec['id']}:%"))))
        if costly["cost"] > 0:
            assert items, "o custo da escolha entra no orçamento do mês"
    ov = client.get(f"{B}/overview", headers=h).json()
    assert ov["close"]["can_close"] in (True, False)
    assert client.post(f"{EC}/events/{dec['id']}/decide", headers=h, json={"option": costly["key"]}).status_code == 409


def test_monthly_decision_catalog_is_consistent():
    assert len(E.MONTHLY) >= 18 and {d.category for d in E.MONTHLY} == {"FINANCIAL", "PERSONAL"}
    for d in E.MONTHLY:
        assert len(d.options) >= 2 and sum(1 for o in d.options if o.default) == 1, d.key
        for o in d.options:
            assert abs(sum(x.prob for x in o.outcomes) - 1) < 1e-9 and all(x.text for x in o.outcomes), (d.key, o.key)


def test_personal_decision_can_improve_relationships(client, auth_headers):
    g, h = _mk_world(client, auth_headers, seed=8)
    pid = arrange_partner(client, h, stage="FRIEND", affinity=40, trust=40)
    u = uid(client, h)
    with SessionLocal() as s:
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        d = E.MONTHLY_BY_KEY["d_turma"]
        from backend.services import economy_service
        ev = economy_service._make_event(s, u, d, month.ref_month.replace(month=month.ref_month.month), 1, economy_service._context(s, u, month.ref_month))
        s.commit()
        eid = ev.id if ev else None
    if eid is None:
        pytest.skip("evento não criado")
    r = client.post(f"{EC}/events/{eid}/decide", headers=h, json={"option": "chamar"})
    assert r.status_code == 200
    assert next(x for x in life(client, h)["relationships"] if x["person_id"] == pid)["affinity"] >= 41


# ------------------------------------------------------------------ carreira e faculdade

def _salary(client, h):
    u = uid(client, h)
    with SessionLocal() as s:
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        from backend.services import item_sync
        return item_sync.salary_total(s, u, month.ref_month)


def _start(client, auth_headers, field, seed=3):
    g = client.post("/api/games", headers=auth_headers, json={"kind": "LIFE", "name": field}).json()
    h = {**auth_headers, "X-Game-Id": str(g["id"])}
    r = client.post("/api/game/start", headers=h, json={"mode": "CAREER", "scenario": "young_pro", "seed": seed, "career_field": field})
    assert r.status_code == 200, r.text
    return h


def test_all_fields_start_with_about_the_same_salary_but_different_outlooks(client, auth_headers):
    salaries = {}
    for f in career_rules.FIELDS:
        salaries[f] = _salary(client, _start(client, auth_headers, f))
    lo, hi = min(salaries.values()), max(salaries.values())
    assert hi / lo < D("1.06"), salaries                                                       # todas ganham mais ou menos o mesmo
    growth = {f: v["growth"] for f, v in career_rules.FIELDS.items()}
    assert max(growth.values()) - min(growth.values()) >= 2.5 and max(v["premium"] for v in career_rules.FIELDS.values()) >= 40


def test_annual_raise_follows_the_fields_outlook(client, auth_headers):
    credit(client, auth_headers, "800000")
    hs = {f: _start(client, auth_headers, f) for f in ("tecnologia", "educacao")}
    start = {f: _salary(client, h) for f, h in hs.items()}
    for h in hs.values():
        _advance(client, h, 12)
    end = {f: _salary(client, h) for f, h in hs.items()}
    tech, edu = end["tecnologia"] / start["tecnologia"], end["educacao"] / start["educacao"]
    assert tech > edu and D("1.04") < tech < D("1.10") and D("1.01") < edu < D("1.07")
    j = life(client, hs["tecnologia"])
    assert any(x["kind"] == "RAISE" for x in j["history"])


def test_degree_costs_money_and_time_then_allows_a_better_paid_career(client, auth_headers):
    credit(client, auth_headers, "800000")
    h = _start(client, auth_headers, "comercio")
    base_salary = _salary(client, h)
    free_before = life(client, h)["attributes"]["free_hours_total"]
    r = client.post(f"{L}/degree", headers=h, json={"field": "tecnologia"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["career"]["studying"]["field"] == "tecnologia" and j["career"]["studying"]["total"] == 48
    assert j["attributes"]["free_hours_total"] == free_before - career_rules.FIELDS["tecnologia"]["hours"]       # a faculdade toma tempo
    assert any(e["key"] == "life:tuition" and D(e["amount"]) >= D("1100") for e in j["expenses"])                  # e dinheiro
    assert client.post(f"{L}/degree", headers=h, json={"field": "saude"}).status_code == 409                       # uma de cada vez
    # sem diploma, mudar de área é recomeçar por baixo
    nodeg = client.post(f"{L}/career/change", headers=h, json={"field": "saude"})
    assert nodeg.status_code == 200 and nodeg.json()["career"]["pending"]["degree"] is False
    assert nodeg.json()["career"]["pending"]["factor"] < 1.0
    # formatura (acelera a faculdade no banco) e mudança para a área mais bem paga
    u = uid(client, h)
    with SessionLocal() as s:
        p = s.scalar(select(LifeProfile).where(LifeProfile.user_id == u))
        p.degree_progress = p.degree_total - 1
        p.pending_career = None
        s.commit()
    _advance(client, h, 1)
    j = life(client, h)
    assert j["career"]["degrees"] == ["tecnologia"] and j["career"]["studying"] is None
    assert any(x["kind"] == "GRADUATED" for x in j["history"])
    sal_before = _salary(client, h)
    r = client.post(f"{L}/career/change", headers=h, json={"field": "tecnologia"})
    assert r.status_code == 200 and r.json()["career"]["pending"]["degree"] is True
    _advance(client, h, 1)
    sal_after = _salary(client, h)
    assert sal_after / sal_before > D("1.30")                                                  # diploma na área nova: salário bem maior
    assert life(client, h)["career"]["field"] == "tecnologia"
    assert sal_after > base_salary * D("1.25")
    assert client.post(f"{L}/career/change", headers=h, json={"field": "tecnologia"}).status_code == 409
    assert client.delete(f"{L}/degree", headers=h).status_code == 409                          # não há faculdade em andamento


def test_dropping_a_degree_stops_tuition(client, auth_headers):
    credit(client, auth_headers, "800000")
    h = _start(client, auth_headers, "comercio")
    client.post(f"{L}/degree", headers=h, json={"field": "educacao"})
    r = client.delete(f"{L}/degree", headers=h)
    assert r.status_code == 200 and r.json()["career"]["studying"] is None
    assert not any(e["key"] == "life:tuition" for e in r.json()["expenses"])


def test_life_api_no_longer_exposes_a_decisions_tab(client, auth_headers):
    assert "pending_decisions" not in life(client, auth_headers)


def test_simulation_settings_live_in_account_settings_per_game(client, auth_headers):
    g, h = _mk_world(client, auth_headers, sim={"volatility": 1.5})
    r = client.get(f"/api/games/{g['id']}/sim-params", headers=auth_headers)           # sem X-Game-Id: é uma configuração da CONTA
    assert r.status_code == 200 and r.json()["params"]["volatility"] == 1.5
    r = client.put(f"/api/games/{g['id']}/sim-params", headers=auth_headers, json={"crisis_frequency": 0.0})
    assert r.status_code == 200 and r.json()["params"]["crisis_frequency"] == 0.0 and r.json()["params"]["volatility"] == 1.5
    assert client.get(f"{EC}", headers=h).json()["params"]["crisis_frequency"] == 0.0
    assert client.put(f"/api/games/{g['id']}/sim-params", headers=auth_headers, json={"volatility": 99}).status_code == 400
    t = client.post("/api/games", headers=auth_headers, json={"kind": "TRAINING", "name": "t", "start_date": "2024-01-01"}).json()
    assert client.get(f"/api/games/{t['id']}/sim-params", headers=auth_headers).status_code == 409
    from tests.test_budget import second_user
    assert client.get(f"/api/games/{g['id']}/sim-params", headers=second_user(client)).status_code == 404
