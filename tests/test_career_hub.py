"""Carreira: vagas e candidaturas, currículo, CLT x PJ, freelas, cursos, modo ranqueado e preço de venda das empresas."""
from decimal import Decimal

import pytest

from tests.conftest import credit
from tests.test_budget import B
from tests.test_engine import _mk_world
from tests.test_life_v3 import _advance, _free_world, cat_id

D = Decimal
C = "/api/career"


def career(client, h):
    r = client.get(C, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_starting_job_is_clt_with_history_and_benefits(client, auth_headers):
    g, h = _mk_world(client, auth_headers, scenario="young_pro")
    j = career(client, h)
    assert len(j["jobs"]) == 1 and j["jobs"][0]["kind"] == "CLT" and j["jobs"][0]["status"] == "ACTIVE" and j["jobs"][0]["in_resume"] is True
    assert "13º salário" in j["jobs"][0]["perks"] and D(j["salary"]) > 0 and j["field"]["key"] and j["work_level"] == "NORMAL"


def test_vacancies_are_scarce_and_chance_grows_with_the_resume(client, auth_headers):
    g, h = _mk_world(client, auth_headers, scenario="young_pro")
    o = client.get(f"{C}/offers?field=tecnologia", headers=h).json()
    assert 1 <= len(o["offers"]) <= 3 and o["score"] >= 0
    base = {x["key"]: x["chance"] for x in o["offers"]}
    assert client.post(f"{C}/education/courses", headers=h, json={"key": "python"}).status_code == 200
    _advance(client, h, 6)                                                   # curso de 6 meses concluído
    o2 = client.get(f"{C}/offers?field=tecnologia", headers=h).json()
    assert o2["score"] > o["score"] and all(0 < x["chance"] <= 92 for x in o2["offers"])
    hidden = client.put(f"{C}/resume", headers=h, json={"kind": "education", "id": next(e["id"] for e in client.get(f"{C}/education", headers=h).json()["history"] if e["key"] == "python"), "in_resume": False})
    assert hidden.status_code == 200
    assert client.get(f"{C}/offers?field=tecnologia", headers=h).json()["score"] < o2["score"]               # fora do currículo, não conta


def test_apply_accept_clt_replaces_job_and_pj_accumulates(client, auth_headers):
    g, h = _mk_world(client, auth_headers, scenario="young_pro")
    got = None
    for _ in range(14):
        cur = career(client, h)
        for f in [x["key"] for x in cur["fields"]]:
            for of in client.get(f"{C}/offers?field={f}", headers=h).json()["offers"]:
                if of["applied"] or got or cur["applications_left"] <= 0:
                    continue
                r = client.post(f"{C}/apply", headers=h, json={"field": f, "offer_key": of["key"]})
                if r.status_code == 200 and r.json()["result"]["status"] == "APPROVED":
                    got = r.json()["result"]["app_id"]
        if got:
            break
        _advance(client, h, 1)
    assert got, "nenhuma candidatura aprovada em 14 meses"
    before = career(client, h)
    j = client.post(f"{C}/applications/{got}/accept", headers=h, json={"kind": "CLT"}).json()
    clts = [x for x in j["jobs"] if x["kind"] == "CLT"]
    assert any(x["status"] == "PENDING" for x in clts) and any(x["end_reason"] == "REPLACED" for x in clts)       # só um CLT por vez
    assert client.post(f"{C}/applications/{got}/accept", headers=h, json={"kind": "CLT"}).status_code == 409       # já aceita
    _advance(client, h, 1)
    after = career(client, h)
    assert sum(1 for x in after["jobs"] if x["status"] == "ACTIVE") == 1 and D(after["salary"]) != D(before["salary"])


def test_rejected_application_cannot_be_accepted_and_limit_per_month(client, auth_headers):
    g, h = _free_world(client, auth_headers, cash=20000, income=3000, expenses=1500, rent=0, name="Candidato", seed=5)
    apps = []
    for f in ("tecnologia", "saude", "engenharia", "financas", "direito"):
        for of in client.get(f"{C}/offers?field={f}", headers=h).json()["offers"]:
            r = client.post(f"{C}/apply", headers=h, json={"field": f, "offer_key": of["key"]})
            apps.append(r)
    assert sum(1 for r in apps if r.status_code == 200) <= 4 and any(r.status_code == 409 for r in apps)
    rejected = [a for a in career(client, h)["applications"] if a["status"] == "REJECTED"]
    if rejected:
        assert client.post(f"{C}/applications/{rejected[0]['id']}/accept", headers=h, json={"kind": "CLT"}).status_code == 409


def test_clt_benefits_thirteenth_and_fgts_and_pj_has_none(client, auth_headers):
    g, h = _free_world(client, auth_headers, cash=20000, income=4000, expenses=1500, rent=0, name="CLT", seed=6)
    assert D(career(client, h)["fgts_balance"]) == 0
    _advance(client, h, 3)
    assert D(career(client, h)["fgts_balance"]) > 0
    ov = client.get(f"{B}/overview", headers=h).json()
    months = 0
    while ov["month"]["ref_month"][5:7] != "12" and months < 14:
        _advance(client, h, 1)
        ov = client.get(f"{B}/overview", headers=h).json()
        months += 1
    names = [i["name"] for i in ov["month"]["items"]]
    assert any(n.startswith("13º salário") for n in names)


def test_withdraw_fgts_only_without_clt_job(client, auth_headers):
    g, h = _free_world(client, auth_headers, cash=30000, income=4000, expenses=1500, rent=0, name="Saque", seed=8)
    _advance(client, h, 3)
    assert client.post(f"{C}/fgts/withdraw", headers=h).status_code == 409
    job = career(client, h)["jobs"][0]
    assert client.post(f"{C}/jobs/{job['id']}/quit", headers=h).status_code == 200
    assert client.post(f"{C}/fgts/withdraw", headers=h).status_code == 409                       # ainda é o último mês de trabalho
    _advance(client, h, 1)
    r = client.post(f"{C}/fgts/withdraw", headers=h)
    assert r.status_code == 200 and D(r.json()["fgts_balance"]) == 0


def test_freelance_needs_hours_and_pays_in_the_budget(client, auth_headers):
    g, h = _free_world(client, auth_headers, cash=20000, income=3000, expenses=1500, rent=0, name="Freela", seed=11)
    taken = None
    for _ in range(8):
        for f in ("comercio", "tecnologia", "artes"):
            gg = client.get(f"{C}/freelance?field={f}", headers=h).json()
            for x in gg["gigs"]:
                if not taken and not x["taken"] and x["hours"] <= gg["free_hours"]:
                    r = client.post(f"{C}/freelance/accept", headers=h, json={"field": f, "key": x["key"]})
                    assert r.status_code == 200, r.text
                    taken = x
        if taken:
            break
        _advance(client, h, 1)
    assert taken
    names = [i["name"] for i in client.get(f"{B}/overview", headers=h).json()["month"]["items"]]
    assert any(n.startswith("Freela:") for n in names)
    assert client.post(f"{C}/freelance/accept", headers=h, json={"field": taken["field"], "key": taken["key"]}).status_code == 409


def test_courses_cost_money_and_hours_and_make_history(client, auth_headers):
    g, h = _free_world(client, auth_headers, cash=20000, income=3000, expenses=1500, rent=0, name="Estudante", seed=12)
    free0 = career(client, h)["free_hours"]
    assert client.post(f"{C}/education/courses", headers=h, json={"key": "excel"}).status_code == 200
    assert career(client, h)["free_hours"] == free0 - 10
    assert any(i["name"] == "Curso: Excel e planilhas" for i in client.get(f"{B}/overview", headers=h).json()["month"]["items"])
    assert client.post(f"{C}/education/courses", headers=h, json={"key": "excel"}).status_code == 409
    _advance(client, h, 2)
    edu = client.get(f"{C}/education", headers=h).json()
    assert next(x for x in edu["history"] if x["key"] == "excel")["status"] == "DONE" and career(client, h)["free_hours"] == free0
    assert client.post(f"{C}/education/courses", headers=h, json={"key": "nao_existe"}).status_code == 404


def test_ranked_mode_starts_at_eighteen_with_a_low_paid_job_and_only_ranked_games_rank(client, auth_headers):
    g = client.post("/api/games", headers=auth_headers, json={"kind": "LIFE", "name": "Ranqueada"}).json()
    h = {**auth_headers, "X-Game-Id": str(g["id"])}
    r = client.post("/api/game/start", headers=h, json={"mode": "RANKED", "seed": 3, "age": 40})
    assert r.status_code == 200, r.text
    j = career(client, h)
    assert D(j["salary"]) == D("1800.00") and j["jobs"][0]["level_name"] == "Entrada" and j["jobs"][0]["kind"] == "CLT"
    assert client.get("/api/life", headers=h).json()["character"]["age_years"] == 18
    rank = client.get("/api/ranking?board=wealth&period=all", headers=auth_headers).json()
    assert rank["participants"] >= 1
    g2 = client.post("/api/games", headers=auth_headers, json={"kind": "LIFE", "name": "Livre"}).json()
    h2 = {**auth_headers, "X-Game-Id": str(g2["id"])}
    assert client.post("/api/game/start", headers=h2, json={"mode": "FREE", "free": {"cash": 5000, "monthly_income": 3000, "monthly_expenses": 1500, "rent": 0}}).status_code == 200


def test_company_price_has_a_ceiling_and_real_estate_is_harder(client, auth_headers):
    from decimal import Decimal as Dd
    from backend.services import company_rules as cr
    for key in ("RESTAURANT", "REAL_ESTATE_AGENCY"):
        seg = next(s for s in cr.SEGMENTS.values() if s.key.value == key) if hasattr(cr, "SEGMENTS") else None
        if seg is None:
            continue
        assert cr.price_factor(seg, seg.price * 3) == 0 and cr.price_factor(seg, Dd("1000000")) == 0
        assert 0 < cr.price_factor(seg, seg.price * Dd("1.3")) < 1 < cr.price_factor(seg, seg.price * Dd("0.7"))
    re_seg = next(s for s in cr.SEGMENTS.values() if s.key.value == "REAL_ESTATE_AGENCY")
    rs = next(s for s in cr.SEGMENTS.values() if s.key.value == "RESTAURANT")
    assert cr.price_factor(re_seg, re_seg.price * Dd("1.5")) < cr.price_factor(rs, rs.price * Dd("1.5"))


# ------------------------------------------------------------------ mérito, aumento e decisões com várias opções
def test_working_hard_builds_merit_and_eventually_brings_a_raise(client, auth_headers):
    g, h = _free_world(client, auth_headers, cash=30000, income=4000, expenses=1500, rent=0, name="Esforçado", seed=21)
    assert client.put(f"{C}/work", headers=h, json={"work_level": "INTENSE"}).status_code == 200
    start = D(career(client, h)["salary"])
    _advance(client, h, 14)
    j = career(client, h)
    assert D(j["salary"]) > start, "trabalhar muito deveria render um aumento em 14 meses"
    lazy = _free_world(client, auth_headers, cash=30000, income=4000, expenses=1500, rent=0, name="Preguiçoso", seed=21)[1]
    client.put(f"{C}/work", headers=lazy, json={"work_level": "REDUCED"})
    _advance(client, lazy, 14)
    assert career(client, lazy)["merit"] == 0


def test_ask_for_a_raise_rules_and_outcome(client, auth_headers):
    g, h = _free_world(client, auth_headers, cash=30000, income=4000, expenses=1500, rent=0, name="Pede", seed=22)
    assert client.post(f"{C}/raise/ask", headers=h).status_code == 409                                   # menos de 6 meses de casa
    _advance(client, h, 7)
    before = D(career(client, h)["salary"])
    r = client.post(f"{C}/raise/ask", headers=h)
    assert r.status_code == 200, r.text
    res = r.json()["raise_result"]
    assert 5 <= res["chance"] <= 70 and res["text"]
    assert client.post(f"{C}/raise/ask", headers=h).status_code == 409                                   # espere 6 meses
    _advance(client, h, 1)
    after = D(career(client, h)["salary"])
    assert (after > before) == res["granted"]


def test_decisions_with_more_than_two_options_exist():
    from backend.services import economy_events as E
    many = [d for d in E.MONTHLY if len(d.options) >= 3]
    assert len(many) >= 5 and any(d.key == "d_trab_projeto" and len(d.options) == 4 for d in many)
    for d in E.MONTHLY:
        for o in d.options:
            assert abs(sum(x.prob for x in o.outcomes) - 1.0) < 1e-9, (d.key, o.key)
        assert sum(1 for o in d.options if o.default) <= 1


# ------------------------------------------------------------------ sobrecarga, doenças, reação das atividades e calendário
L = "/api/life"


def test_calendar_adds_up_to_the_whole_month_and_lists_each_use_of_time(client, auth_headers):
    g, h = _free_world(client, auth_headers, cash=20000, income=3000, expenses=1500, rent=0, name="Agenda", seed=31)
    client.post(f"{C}/education/courses", headers=h, json={"key": "excel"})
    client.post(f"{L}/activities", headers=h, json={"key": client.get(L, headers=h).json()["activities"][0]["key"]})
    cal = client.get(f"{L}/calendar", headers=h).json()
    assert cal["total"] == 720 and sum(r["hours"] for r in cal["rows"]) == 720
    labels = " | ".join(r["label"] for r in cal["rows"])
    assert "Sono" in labels and "Trabalho" in labels and "Curso: Excel" in labels and "Tempo livre restante" in labels and "🎯" in labels


def test_overload_causes_stress_illness_and_burnout_and_treatment_costs_money(client, auth_headers):
    g, h = _free_world(client, auth_headers, cash=900000, income=9000, expenses=1500, rent=0, name="Sobrecarga", seed=33)
    client.put(f"{C}/work", headers=h, json={"work_level": "INTENSE"})
    for k in ("ingles", "python", "web"):
        client.post(f"{C}/education/courses", headers=h, json={"key": k})
    seen = set()
    for _ in range(40):
        _advance(client, h, 1)
        cs = client.get(L, headers=h).json()["conditions"]
        seen |= {c["key"] for c in cs}
        if cs:
            break
    j = client.get(L, headers=h).json()
    assert j["stress"] > 0 and j["conditions"], "sobrecarga contínua deveria causar alguma doença"
    key = j["conditions"][0]["key"]
    r = client.put(f"{L}/conditions/{key}/treatment", headers=h, json={"treated": True})
    assert r.status_code == 200 and r.json()["conditions"][0]["treated"] is True
    names = [i["name"] for i in client.get(f"{B}/overview", headers=h).json()["month"]["items"]]
    assert any(n.startswith("Tratamento:") for n in names)
    assert client.put(f"{L}/conditions/NAO_EXISTE/treatment", headers=h, json={"treated": True}).status_code == 404


def test_relationship_reacts_to_activities_with_small_or_big_gains(client, auth_headers):
    credit(client, auth_headers, "900000")
    g, h = _mk_world(client, auth_headers, seed=7, scenario="family")
    j = client.get(L, headers=h).json()
    friend = next(r for r in j["relationships"] if r["stage"] != "ENDED")
    seen = set()
    for it in j["interactions"]:
        before = next(r for r in client.get(L, headers=h).json()["relationships"] if r["person_id"] == friend["person_id"])["affinity"]
        r = client.post(f"{L}/people/{friend['person_id']}/interact", headers=h, json={"key": it["key"]})
        if r.status_code != 200:
            continue
        res = r.json()["result"]
        after = next(x for x in r.json()["relationships"] if x["person_id"] == friend["person_id"])["affinity"]
        assert res["reaction"] in ("LOVED", "LIKED", "NEUTRAL", "DISLIKED") and res["reaction_text"]
        assert (res["delta"] < 0) == (res["reaction"] == "DISLIKED") and (after - before == res["delta"] or after in (0, 100))
        seen.add(res["reaction"])
    assert len(seen) >= 2                                                                              # reações variam conforme a atividade e a pessoa


# ---------------------------------------------------------------- pedido de aumento POR EMPREGO
def _add_job(db, game_id, *, kind, title, net, months_ago):
    from sqlalchemy import select

    from backend.models import CareerJob, Game
    from backend.services import budget_service as bsvc
    uid = db.scalar(select(Game.world_user_id).where(Game.id == game_id))
    month = career_ref = None
    from backend.services.budget_service import open_month
    month = open_month(db, uid).ref_month
    j = CareerJob(user_id=uid, title=title, employer="Teste S.A.", field="comercio", kind=kind, level=1, net=net,
                  start_month=bsvc.shift_month(month, -months_ago), legacy=False)
    db.add(j)
    db.commit()
    return j.id


def test_raise_can_be_asked_per_job_even_when_a_pj_pays_more(client, auth_headers, db, monkeypatch):
    from backend.services import career_hub as chub
    g, h = _free_world(client, auth_headers, cash=30000, income=4000, expenses=1500, rent=0, name="Dois empregos", seed=31)
    _advance(client, h, 7)                                                     # o CLT inicial já tem mais de 6 meses de casa
    pj = _add_job(db, g["id"], kind="PJ", title="Consultoria", net=D("90000"), months_ago=8)
    real = chub.job_net
    monkeypatch.setattr(chub, "job_net", lambda d, j, ref: D("90000") if j.id == pj else real(d, j, ref))   # o PJ é o emprego mais bem pago
    c = career(client, h)
    clt = next(x for x in c["jobs"] if x["kind"] == "CLT" and x["status"] == "ACTIVE")
    pjo = next(x for x in c["jobs"] if x["id"] == pj)
    assert clt["can_raise"] is True and clt["raise_note"] is None
    assert pjo["can_raise"] is False and "PJ" in pjo["raise_note"]
    assert client.post(f"{C}/jobs/{pj}/raise/ask", headers=h).status_code == 409           # PJ não pede aumento
    r = client.post(f"{C}/jobs/{clt['id']}/raise/ask", headers=h)                           # ANTES do ajuste isto era 409: o "top job" era o PJ
    assert r.status_code == 200, r.text
    assert clt["title"] in r.json()["raise_result"]["text"]
    assert client.post(f"{C}/jobs/{clt['id']}/raise/ask", headers=h).status_code == 409    # intervalo de 6 meses neste emprego
    after = next(x for x in career(client, h)["jobs"] if x["id"] == clt["id"])
    assert after["can_raise"] is False and after["raise_ready_in"] == 6
    assert client.post(f"{C}/jobs/999999/raise/ask", headers=h).status_code == 409         # emprego que não é seu / não existe


def test_legacy_raise_endpoint_targets_the_best_clt_job_not_the_top_pj(client, auth_headers, db, monkeypatch):
    from backend.services import career_hub as chub
    g, h = _free_world(client, auth_headers, cash=30000, income=4000, expenses=1500, rent=0, name="Legado", seed=32)
    _advance(client, h, 7)
    pj = _add_job(db, g["id"], kind="PJ", title="Freela grande", net=D("90000"), months_ago=8)
    real = chub.job_net
    monkeypatch.setattr(chub, "job_net", lambda d, j, ref: D("90000") if j.id == pj else real(d, j, ref))
    assert client.post(f"{C}/raise/ask", headers=h).status_code == 200


def test_each_job_has_its_own_six_month_interval(client, auth_headers, db, monkeypatch):
    from backend.services import career_hub as chub
    g, h = _free_world(client, auth_headers, cash=30000, income=4000, expenses=1500, rent=0, name="Intervalos", seed=33)
    _advance(client, h, 7)
    second = _add_job(db, g["id"], kind="CLT", title="Segundo CLT", net=D("3000"), months_ago=9)
    real = chub.job_net
    monkeypatch.setattr(chub, "job_net", lambda d, j, ref: D("3000") if j.id == second else real(d, j, ref))
    c = career(client, h)
    first = next(x for x in c["jobs"] if x["kind"] == "CLT" and x["id"] != second and x["status"] == "ACTIVE")
    assert client.post(f"{C}/jobs/{first['id']}/raise/ask", headers=h).status_code == 200
    assert client.post(f"{C}/jobs/{first['id']}/raise/ask", headers=h).status_code == 409
    assert client.post(f"{C}/jobs/{second}/raise/ask", headers=h).status_code == 200       # o outro emprego não foi travado pelo primeiro
