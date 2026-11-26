"""Estudo, novas faculdades e sinergias, política, concursos, cinema, polêmicas e CEO."""
import datetime as dt
from decimal import Decimal

from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import ArtistItem, ArtistProfile, CareerJob, Education, SimMonth
from backend.services import artist_film as AF
from backend.services import artist_rules as AR
from backend.services import career_hub, career_rules
from backend.services import company_aides as aides
from backend.services import politics_rules as PR
from backend.services import politics_service as pols
from backend.services import university_rules as ur
from tests.test_companies import C, close, create_ok, detail, key, rich  # noqa: F401

A = "/api/artist"
POL = "/api/politics"
D = Decimal


def uid(client, h):
    client.get("/api/budget/overview", headers=h)                       # garante o mês aberto
    return client.get("/api/auth/me", headers=h).json()["id"]


def open_ref(s, u):
    return s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN")).ref_month


# ------------------------------------------------------------------ estudo
def test_study_hours_consume_free_time_and_raise_study(client, rich):
    life = client.get("/api/life", headers=rich).json()
    before = life["attributes"]["study"]
    assert life["attributes"]["study_hours_day"] == 0
    r = client.put("/api/life/study", headers=rich, json={"hours_day": 2})
    assert r.status_code == 200, r.text
    assert r.json()["attributes"]["study_hours_day"] == 2
    assert client.put("/api/life/study", headers=rich, json={"hours_day": 7}).status_code == 400
    assert client.put("/api/life/study", headers=rich, json={"hours_day": 6}).status_code in (200, 409)      # só cabe o que o calendário permite
    assert client.put("/api/life/study", headers=rich, json={"hours_day": 2}).status_code == 200
    assert close(client, rich).status_code == 200
    assert client.get("/api/life", headers=rich).json()["attributes"]["study"] > before


def test_study_decays_without_hours_and_helps_vestibular():
    from backend.models import LifeProfile
    p = LifeProfile(user_id=1, study=50.0, study_hours_day=0.0)
    from backend.services import life_service as ls
    ls._study_monthly(p)
    assert p.study < 50
    p2 = LifeProfile(user_id=1, study=50.0, study_hours_day=3.0, degree_field=None)
    ls._study_monthly(p2)
    assert p2.study > 50


# ------------------------------------------------------------------ novas faculdades e sinergias
def test_new_degrees_exist_in_real_universities():
    for f in ("musica", "matematica", "relacoes"):
        assert f in career_rules.FIELDS
    assert ur.offers_field(ur.UNIVERSITIES["usp"], "musica") and ur.offers_field(ur.UNIVERSITIES["unb"], "relacoes") and ur.offers_field(ur.UNIVERSITIES["fgv"], "matematica")
    assert not ur.offers_field(ur.UNIVERSITIES["ita"], "relacoes") and not ur.offers_field(ur.UNIVERSITIES["insper"], "musica")
    assert ur.offers_field(ur.UNIVERSITIES["puc-rio"], "relacoes")


def test_degree_in_one_area_helps_resume_in_others(client, rich):
    u = uid(client, rich)
    with SessionLocal() as s:
        ref = open_ref(s, u)
        base_fin = career_hub.resume_score(s, u, "financas", ref)[0]
        base_eng = career_hub.resume_score(s, u, "engenharia", ref)[0]
        s.add(Education(user_id=u, key="matematica", name="Matemática", field="matematica", kind="DEGREE", months_total=48, progress=48, cost_month=0, hours=0, points=35,
                        status="DONE", start_month=ref, end_month=ref, in_resume=True))
        s.flush()
        assert career_hub.resume_score(s, u, "financas", ref)[0] >= base_fin + 12 + 8 - 1                       # diploma "de outra área" + sinergia
        assert career_hub.resume_score(s, u, "engenharia", ref)[0] >= base_eng + 12
        assert career_hub.degree_synergy(s, u, "politica") == 0 and career_hub.degree_synergy(s, u, "concurso") >= 6
        s.rollback()
    assert career_rules.SYNERGY[("relacoes", "politica")] > career_rules.SYNERGY[("comercio", "politica")]


# ------------------------------------------------------------------ concursos públicos
def test_exam_chance_depends_on_study_and_degrees():
    low = PR.exam_chance(20, 0, False, 300, 2, 0)
    high = PR.exam_chance(80, 18, True, 300, 2, 3)
    assert low <= 0.05 < 0.6 < high <= 0.9
    assert PR.exam_chance(60, 0, True, 40, 1, 1) > PR.exam_chance(60, 0, True, 400, 1, 1)                      # menos concorrência, mais chance
    assert PR.exam_chance(50, 0, False, 100, 1, 0) < PR.exam_chance(50, 0, False, 100, 1, 4)


def test_public_exam_register_and_result(client, rich):
    ov = client.get(POL, headers=rich).json()
    offer = next(o for o in ov["exams"]["offers"] if o["fee"] > 0)
    r = client.post(f"{POL}/exams/register", headers=rich, json={"key": offer["key"]})
    assert r.status_code == 200, r.text
    assert any(x["status"] == "REGISTERED" for x in r.json()["exams"]["mine"])
    assert client.post(f"{POL}/exams/register", headers=rich, json={"key": offer["key"]}).status_code == 409
    u = uid(client, rich)
    with SessionLocal() as s:                                                  # força a prova para este mês com estudo máximo e confere o resultado
        from backend.models import LifeProfile
        lp = s.scalar(select(LifeProfile).where(LifeProfile.user_id == u))
        lp.study, lp.study_hours_day = 100.0, 0.0
        ref = open_ref(s, u)
        c = s.scalar(select(ArtistItem).where(ArtistItem.user_id == u, ArtistItem.kind == "CONCURSO"))
        c.data = {**c.data, "exam_month": ref.isoformat(), "competition": 20, "requires": None, "level": 0}
        pols.process_month(s, u, s.scalar(select(ArtistProfile).where(ArtistProfile.user_id == u)), ref, 7)
        assert c.status in ("PASSED", "FAILED")
        if c.status == "PASSED":
            assert s.scalar(select(CareerJob).where(CareerJob.user_id == u, CareerJob.title == c.data["role"])) is not None
        s.commit()


# ------------------------------------------------------------------ política
def test_politics_catalog_is_real_brazil():
    assert PR.OFFICES["presidente"][3] == 35 and PR.OFFICES["senador"][3] == 35 and PR.OFFICES["vereador"][3] == 18 and PR.OFFICES["governador"][3] == 30
    assert PR.OFFICES["dep_federal"][4] == 46400 and PR.OFFICES["vereador"][2] == "municipal" and PR.OFFICES["senador"][2] == "geral"
    assert all(len(p[0]) > 10 for p in PR.PARTIES.values())                                                    # partidos fictícios
    assert dt.date(2028, 10, 1) == pols.election_date("vereador", dt.date(2026, 11, 1)) and pols.election_date("senador", dt.date(2026, 11, 1)) == dt.date(2030, 10, 1)
    assert pols.election_date("prefeito", dt.date(2028, 10, 1)) == dt.date(2028, 10, 1) and pols.election_date("prefeito", dt.date(2028, 11, 1)) == dt.date(2032, 10, 1)


def test_politics_profile_candidacy_campaign_and_election(client, rich):
    ov = client.get(POL, headers=rich).json()
    vereador = next(o for o in ov["offices"] if o["key"] == "vereador")
    assert not vereador["can_run"] and any("partido" in x for x in vereador["blocked_by"])
    assert client.put(f"{POL}/profile", headers=rich, json={"party": "xx"}).status_code == 400
    assert client.put(f"{POL}/profile", headers=rich, json={"proposals": ["saude", "educacao", "economia", "social"]}).status_code == 400            # no máximo 3
    r = client.put(f"{POL}/profile", headers=rich, json={"party": "pmc", "ideology": "centro_direita", "proposals": ["saude", "seguranca"], "media": "transparente"})
    assert r.status_code == 200, r.text
    prof = r.json()["profile"]
    assert prof["party"] == "pmc" and prof["media"] == "transparente" and prof["proposals"] == ["saude", "seguranca"]
    vereador = next(o for o in r.json()["offices"] if o["key"] == "vereador")
    assert vereador["can_run"] and 0 < vereador["estimate"]["win_chance"] < 1
    president = next(o for o in r.json()["offices"] if o["key"] == "presidente")
    assert president["estimate"]["win_chance"] < vereador["estimate"]["win_chance"]
    c = client.post(f"{POL}/candidacy", headers=rich, json={"office": "vereador"})
    assert c.status_code == 200, c.text
    camp = c.json()["campaigns"][0]
    assert camp["status"] == "RUNNING" and client.post(f"{POL}/candidacy", headers=rich, json={"office": "vereador"}).status_code == 409
    base = camp["estimate"]["win_chance"]
    m = client.post(f"{POL}/campaigns/{camp['id']}/marketer", headers=rich, json={"level": "HIGH"})
    assert m.status_code == 200 and m.json()["campaigns"][0]["marketer"] == "HIGH"
    assert client.post(f"{POL}/campaigns/{camp['id']}/marketer", headers=rich, json={"level": "XX"}).status_code == 400
    rr = client.post(f"{POL}/campaigns/{camp['id']}/rally", headers=rich, json={"kind": "comicio"})
    assert rr.status_code == 200 and rr.json()["campaigns"][0]["momentum"] > camp["momentum"]
    assert client.post(f"{POL}/campaigns/{camp['id']}/rally", headers=rich, json={"kind": "comicio"}).status_code == 409
    sp = client.post(f"{POL}/campaigns/{camp['id']}/spend", headers=rich, json={"amount": 80000})
    assert sp.status_code == 200 and sp.json()["campaigns"][0]["estimate"]["win_chance"] > base
    # a eleição é decidida em outubro: força a data para este mês e confere o resultado e o mandato
    u = uid(client, rich)
    with SessionLocal() as s:
        ref = open_ref(s, u)
        camp_row = s.scalar(select(ArtistItem).where(ArtistItem.user_id == u, ArtistItem.kind == "CAMPAIGN"))
        camp_row.data = {**camp_row.data, "election": ref.isoformat()}
        pols.process_month(s, u, s.scalar(select(ArtistProfile).where(ArtistProfile.user_id == u)), ref, 3)
        assert camp_row.status in ("WON", "LOST")
        won = camp_row.status == "WON"
        assert bool(s.scalar(select(ArtistItem).where(ArtistItem.user_id == u, ArtistItem.kind == "TERM"))) == won
        s.commit()
    after = client.get(POL, headers=rich).json()
    if won:
        t = after["terms"][0]
        assert t["status"] == "ACTIVE" and t["salary"] == 14000
        a = client.post(f"{POL}/terms/{t['id']}/action", headers=rich, json={"kind": "town_hall"})
        assert a.status_code == 200 and a.json()["terms"][0]["approval"] >= t["approval"]
        assert client.post(f"{POL}/terms/{t['id']}/action", headers=rich, json={"kind": "town_hall"}).status_code == 409


def test_underage_cannot_run_for_senate(client, rich):
    client.put(f"{POL}/profile", headers=rich, json={"party": "pmc", "proposals": ["saude"]})
    ov = client.get(POL, headers=rich).json()
    sen = next(o for o in ov["offices"] if o["key"] == "senador")
    assert ov["age"] < 35 and not sen["can_run"] and any("idade" in x for x in sen["blocked_by"])
    assert client.post(f"{POL}/candidacy", headers=rich, json={"office": "senador"}).status_code == 409


# ------------------------------------------------------------------ polêmicas (artistas, empresários, políticos)
def test_polemic_events_exist_for_public_figures_and_politicians():
    discs = {e["disc"] for e in AR.EVENTS.values()}
    assert {"public", "politics"} <= discs
    for k in ("pub_declaracao", "pub_tema_polemico", "pol_fake_news", "pol_voto_polemico"):
        assert k in AR.EVENTS and any("relevance" in x[2] or "approval" in x[2] for o in AR.EVENTS[k]["options"] for x in o["outcomes"])


def test_polemic_decision_changes_relevance_and_media_style_amplifies(client, rich):
    u = uid(client, rich)
    client.put(f"{POL}/profile", headers=rich, json={"media": "combativo"})
    with SessionLocal() as s:
        ref = open_ref(s, u)
        p = s.scalar(select(ArtistProfile).where(ArtistProfile.user_id == u))
        p.fame = {**(p.fame or {}), "music": 30.0}
        e = AR.EVENTS["pub_declaracao"]
        s.add(ArtistItem(user_id=u, kind="DECISION", status="OPEN", name=e["title"], created_month=ref,
                         data={"work": "EVENT", "event_key": "pub_declaracao", "desc": e["desc"], "work_id": 0,
                               "options": [{"key": o["key"], "label": o["label"], "cost": o["cost"], "desc": ""} for o in e["options"]]}))
        s.commit()
    dec = client.get(A, headers=rich).json()["decisions"][0]
    assert dec["work"] == "EVENT" and {"desculpas", "defender", "atacar", "ignorar"} <= {o["key"] for o in dec["options"]}
    r = client.post(f"{A}/decisions/{dec['id']}", headers=rich, json={"option": "atacar"})
    assert r.status_code == 200 and "relevância" in r.json()["result"]["message"]
    assert r.json()["fame"]["music"] != 30.0


# ------------------------------------------------------------------ cinema
def test_film_market_scripts_and_director_jobs(client, rich):
    ov = client.get(A, headers=rich).json()["film"]
    assert len(ov["market"]["scripts"]) == 5 and len(ov["market"]["actors"]) == 8 and ov["offers"]
    assert {"drama", "terror", "acao"} <= {g["key"] for g in ov["catalog"]["genres"]}
    offer = ov["offers"][0]
    r = client.post(f"{A}/apply", headers=rich, json={"discipline": "film", "offer_key": offer["key"]})
    assert r.status_code == 200 and isinstance(r.json()["result"]["hired"], bool)
    sc = ov["market"]["scripts"][0]
    b = client.post(f"{A}/film/script/buy", headers=rich, json={"key": sc["key"]})
    assert b.status_code == 200, b.text
    assert any(x["title"] == sc["title"] and x["source"] == "BOUGHT" for x in b.json()["film"]["scripts"])
    assert client.post(f"{A}/film/script/buy", headers=rich, json={"key": sc["key"]}).status_code == 409


def test_screenwriter_writes_and_sells_scripts(client, rich):
    made = None
    for i, t in enumerate(("A Casa Velha", "Sol de Inverno", "Rumo ao Norte", "Os Três Amigos", "Chuva de Verão", "Último Trem", "Fogo e Água", "O Retorno")):
        r = client.post(f"{A}/film/script/write", headers=rich, json={"title": t, "genre": "drama", "theme": "familia"})
        assert r.status_code in (200, 409), r.text
        if r.status_code == 200 and r.json()["result"]["created"]:
            made = r.json()
            break
    if made is None:
        return
    sid = made["result"]["script_id"]
    s = client.post(f"{A}/film/script/{sid}/sell", headers=rich)
    assert s.status_code == 200 and isinstance(s.json()["result"]["sold"], bool)
    if s.json()["result"]["sold"]:
        assert client.post(f"{A}/film/script/{sid}/sell", headers=rich).status_code == 409
    assert client.post(f"{A}/film/script/write", headers=rich, json={"title": "X", "genre": "xx", "theme": "familia"}).status_code == 400


def test_film_production_flow_to_release_decision(client, rich):
    sc = client.get(A, headers=rich).json()["film"]["market"]["scripts"][0]
    assert client.post(f"{A}/film/script/buy", headers=rich, json={"key": sc["key"]}).status_code == 200
    scripts = client.get(A, headers=rich).json()["film"]["scripts"]
    r = client.post(f"{A}/film/projects", headers=rich, json={"title": "Meu Filme", "theme": sc["theme"], "genre": sc["genre"], "script_id": scripts[0]["id"], "funding": "SELF", "scale": "indie"})
    assert r.status_code == 200 and r.json()["result"]["started"] is True
    fid = r.json()["result"]["film_id"]
    miss = client.post(f"{A}/film/projects/{fid}/shoot", headers=rich)
    assert miss.status_code == 409 and "elenco" in miss.json()["detail"]
    for kind in ("costume", "studio", "set"):
        assert client.post(f"{A}/film/projects/{fid}/production", headers=rich, json={"kind": kind, "tier": 1}).status_code == 200
    assert client.post(f"{A}/film/projects/{fid}/production", headers=rich, json={"kind": "studio", "tier": 1}).status_code == 409
    assert client.post(f"{A}/film/projects/{fid}/production", headers=rich, json={"kind": "xx", "tier": 1}).status_code == 400
    actors = client.get(A, headers=rich).json()["film"]["market"]["actors"]
    hired = 0
    for a in actors:
        rr = client.post(f"{A}/film/projects/{fid}/cast", headers=rich, json={"key": a["key"]})
        assert rr.status_code == 200
        hired += int(rr.json()["result"]["hired"])
    assert hired >= 1
    # completa o elenco e roda as filmagens até o lançamento
    u = uid(client, rich)
    with SessionLocal() as s:
        f = s.get(ArtistItem, fid)
        cast = list(f.data["cast"]) + [{"key": f"X{i}", "name": f"Extra {i}", "skill": 60, "fee": 0} for i in range(3)]
        f.data = {**f.data, "cast": cast}
        s.commit()
    assert client.post(f"{A}/film/projects/{fid}/shoot", headers=rich).status_code == 200
    for _ in range(2):
        assert close(client, rich).status_code == 200
    ov = client.get(A, headers=rich).json()
    dec = next(d for d in ov["decisions"] if d["work"] == "FILM")
    assert {o["key"] for o in dec["options"]} == set(AF.RELEASE)
    rel = client.post(f"{A}/decisions/{dec['id']}", headers=rich, json={"option": "streaming"})
    assert rel.status_code == 200, rel.text
    proj = next(p for p in rel.json()["film"]["projects"] if p["id"] == fid)
    assert proj["status"] == "RELEASED" and proj["quality"] > 0 and "streaming" in proj["result"].lower()
    assert any(s["id"] == scripts[0]["id"] and s["status"] == "PRODUCED" for s in rel.json()["film"]["scripts"])


def test_film_with_producer_may_refuse_weak_script(client, rich):
    sc = client.get(A, headers=rich).json()["film"]["market"]["scripts"]
    weakest = min(sc, key=lambda x: x["quality"])
    client.post(f"{A}/film/script/buy", headers=rich, json={"key": weakest["key"]})
    s = client.get(A, headers=rich).json()["film"]["scripts"][0]
    r = client.post(f"{A}/film/projects", headers=rich, json={"title": "Aposta", "theme": s["theme"], "genre": s["genre"], "script_id": s["id"], "funding": "PRODUCER", "scale": "grande"})
    assert r.status_code == 200 and isinstance(r.json()["result"]["started"], bool)


# ------------------------------------------------------------------ CEO e equipe de gestão
def test_ceo_tiers_and_improvement_math():
    assert aides.CEOS["HIGH"].fee > aides.CEOS["MID"].fee > aides.CEOS["LOW"].fee and aides.CEOS["HIGH"].success > aides.CEOS["LOW"].success
    a = aides.ceo_improvement("HIGH", "SAVINGS", seed=1, company_id=1, ref=dt.date(2026, 11, 1), budget=D(5000), reference=D(5000))
    b = aides.ceo_improvement("HIGH", "SAVINGS", seed=1, company_id=1, ref=dt.date(2026, 11, 1), budget=D(5000), reference=D(5000))
    assert a == b and a["kind"] in ("contracts", "brand", "quality", "process")
    kinds = {aides.ceo_improvement("MID", "SAVINGS", seed=s, company_id=2, ref=dt.date(2026, 11, 1), budget=D(0), reference=D(5000))["kind"] for s in range(60)}
    assert "contracts" in kinds and len(kinds) >= 3
    assert aides.build_briefing("CEO", {"focus": "QUALITY", "monthly_budget": "2000"}) == {"focus": "QUALITY", "monthly_budget": "2000.00"}
    try:
        aides.build_briefing("CEO", {"focus": "XX"})
    except ValueError:
        pass
    else:
        raise AssertionError("foco inválido deveria falhar")


def test_ceo_hire_briefing_and_monthly_report(client, rich):
    cid = create_ok(client, rich, staff=False, extra="400000")["company"]["id"]
    d = detail(client, rich, cid)
    assert d["aide_options"]["ceo"] and d["aides"]["ceo"] is None
    r = client.post(f"{C}/{cid}/aides/CEO", headers=rich, json={"level": "HIGH"})
    assert r.status_code == 200 and r.json()["aides"]["ceo"]["level"] == "HIGH"
    r = client.put(f"{C}/{cid}/aides/CEO/briefing", headers=rich, json={"focus": "QUALITY", "monthly_budget": "3000"})
    assert r.status_code == 200 and r.json()["aides"]["ceo"]["focus"] == "QUALITY"
    assert client.put(f"{C}/{cid}/aides/CEO/briefing", headers=rich, json={"focus": "XX"}).status_code == 400
    assert close(client, rich).status_code == 200
    ceo = detail(client, rich, cid)["aides"]["ceo"]
    assert len(ceo["reports"]) == 1 and ceo["reports"][0]["text"] and ceo["reports"][0]["ok"] in (True, False)
    assert any("Relatório do CEO" in e["description"] for e in detail(client, rich, cid)["events"])
    assert client.delete(f"{C}/{cid}/aides/CEO", headers=rich).json()["aides"]["ceo"] is None
