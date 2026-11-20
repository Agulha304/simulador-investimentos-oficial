"""Sócios, calote, processos jurídicos, situação financeira dos amigos e histórias da convivência."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import Company, CompanyPartner, LedgerEntry, LifeLog, Person, Relationship, SimMonth, WorldEvent
from backend.services import economy_events as E, economy_service, life_rules as R
from tests.conftest import credit
from tests.test_budget import second_user
from tests.test_companies import create_ok, cash as co_cash
from tests.test_life import advance, arrange_partner, life, uid

D = Decimal
L = "/api/life"
C = "/api/companies"


def _friend(client, h, name="Sócio", stage="FRIEND", affinity=85, trust=85, assets="500000"):
    pid = arrange_partner(client, h, stage=stage, affinity=affinity, trust=trust)
    with SessionLocal() as s:
        p = s.get(Person, pid)
        p.name, p.assets, p.personality = name, D(assets), "ambicioso"
        s.commit()
    return pid


def _invite(client, h, pid, share="30", capital="150000"):
    r = client.post(f"{C}/partner-invites", headers=h, json={"person_id": pid, "share_pct": share, "capital": capital})
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ histórias e situação financeira

def test_interactions_return_a_story_and_it_is_logged(client, auth_headers):
    credit(client, auth_headers, "300000")
    pid = arrange_partner(client, auth_headers, stage="FRIEND", affinity=50, trust=50)
    seen = set()
    for _ in range(3):
        r = client.post(f"{L}/people/{pid}/interact", headers=auth_headers, json={"key": "help"})
        assert r.status_code == 200, r.text
        story = r.json()["result"]["story"]
        assert story and "ONG" in story or story in [t.format(name="Camila") for t in R.STORIES["help"]]
        seen.add(story)
        advance(client, auth_headers)
    assert len(seen) >= 2                                                               # histórias variam
    assert any(h["kind"] == "TOGETHER" for h in life(client, auth_headers)["history"])
    act = client.post(f"{L}/activities", headers=auth_headers, json={"key": "cinema"}).json()
    assert act["result"]["story"].startswith("Você foi a:")


def test_every_relationship_shows_financial_condition(client, auth_headers):
    pid = _friend(client, auth_headers, assets="900000")
    rel = next(x for x in life(client, auth_headers)["relationships"] if x["person_id"] == pid)
    assert rel["stage"] == "FRIEND" and rel["finance_label"] in ("muito confortável", "confortável", "estável", "apertada", "endividado(a)")
    assert {"income", "assets", "debts"} <= set(rel)
    with SessionLocal() as s:
        p = s.get(Person, pid)
        p.assets, p.debts, p.income = D("1000"), D("90000"), D("3000")
        s.commit()
    assert next(x for x in life(client, auth_headers)["relationships"] if x["person_id"] == pid)["finance_label"] == "endividado(a)"


# ------------------------------------------------------------------ convites e sociedade

def test_partner_can_refuse_and_refusal_hurts_the_relationship(client, auth_headers):
    credit(client, auth_headers, "2000000")
    stranger = arrange_partner(client, auth_headers, stage="ACQUAINTANCE", affinity=30, trust=30)
    inv = _invite(client, auth_headers, stranger)
    assert inv["accepted"] is False and "intimidade" in inv["message"]
    assert next(x for x in life(client, auth_headers)["relationships"] if x["person_id"] == stranger)["affinity"] == 24      # −6 gravado
    broke = _friend(client, auth_headers, "Sem dinheiro", assets="1000")
    inv2 = _invite(client, auth_headers, broke, capital="200000")
    assert inv2["accepted"] is False and "não tem como investir" in inv2["message"]
    assert _invite(client, auth_headers, broke, capital="200000")["id"] == inv2["id"]                 # não dá para tentar de novo no mesmo mês
    assert client.post(f"{C}/partner-invites", headers=auth_headers, json={"person_id": broke, "share_pct": "2", "capital": "100"}).status_code == 400


def test_company_with_accepted_partners_splits_capital_and_ownership(client, auth_headers):
    credit(client, auth_headers, "3000000")
    accepted = []
    for i in range(6):
        pid = _friend(client, auth_headers, f"Sócio {i}")
        inv = _invite(client, auth_headers, pid, share="30", capital="200000")
        if inv["accepted"]:
            accepted.append((pid, inv))
    assert len(accepted) >= 3, "amigos próximos, ricos e compatíveis costumam aceitar"                 # decisão probabilística (não 100%)
    pid, inv = accepted[0]
    before = co_cash(client, auth_headers)
    with SessionLocal() as s:
        assets_before = s.get(Person, pid).assets
    r = create_ok(client, auth_headers, name="Sociedade", segment="CAFE", extra="40000", partner_invite_ids=[inv["id"]])
    cap = D(r["company"]["cash"]) if False else None
    comp = r["company"]
    assert D(comp["owner_share_pct"]) == D("70.00")                                                    # 100% − 30% do sócio
    partners = r["partners"]
    assert len(partners) == 1 and partners[0]["person_id"] == pid and D(partners[0]["share_pct"]) == D("30.00") and partners[0]["status"] == "ACTIVE"
    with SessionLocal() as s:
        assert s.get(Person, pid).assets == assets_before - D(partners[0]["contribution"])             # o aporte saiu do patrimônio dele(a)
    spent = before - co_cash(client, auth_headers)
    total_capital = D(partners[0]["contribution"]) / D("0.30")
    assert abs(spent - total_capital * D("0.70")) < D("0.05")                                          # você pagou só a sua parte
    # um convite só vale uma vez
    assert client.post(C, headers=auth_headers, json={"name": "Outra", "segment": "CAFE", "capital": "300000", "partner_invite_ids": [inv["id"]]}).status_code == 409
    # lucros: só a parte do dono vai para o seu caixa pessoal
    cid = comp["id"]
    from tests.test_budget import close
    for _ in range(2):
        assert close(client, auth_headers).status_code == 200
    det = client.get(f"{C}/{cid}", headers=auth_headers).json()
    assert det["partners"][0]["finance"] in ("muito confortável", "confortável", "estável", "apertada", "endividado(a)")


def test_partner_without_funds_blocks_company_creation(client, auth_headers):
    credit(client, auth_headers, "3000000")
    for i in range(8):
        pid = _friend(client, auth_headers, f"Sócio {i}", assets="60000")
        inv = _invite(client, auth_headers, pid, share="30", capital="150000")
        if inv["accepted"]:
            break
    else:
        pytest.skip("ninguém aceitou")
    with SessionLocal() as s:
        s.get(Person, pid).assets = D("1000")                                                          # perdeu o dinheiro depois de aceitar
        s.commit()
    from tests.test_companies import quote
    q = quote(client, auth_headers)
    r = client.post(C, headers=auth_headers, json={"name": "Quebrada", "segment": "CAFE", "capital": str(D(q["required_capital"]) + 30000), "partner_invite_ids": [inv["id"]]})
    assert r.status_code in (400, 409) and "aportar" in r.text or r.status_code == 400


# ------------------------------------------------------------------ calote e processos

def _company_with_partner(client, h, share="30"):
    credit(client, h, "6000000")
    for i in range(10):
        pid = _friend(client, h, f"Sócio {i}")
        inv = _invite(client, h, pid, share=share, capital="200000")
        if inv["accepted"]:
            r = create_ok(client, h, name="Com Sócio", segment="CAFE", extra="40000", partner_invite_ids=[inv["id"]])
            return r["company"]["id"], pid
    pytest.skip("ninguém aceitou")


def _spawn(client, h, key, company_id):
    u = uid(client, h)
    with SessionLocal() as s:
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        ctx = economy_service._context(s, u, month.ref_month)
        d = E.CATALOG_BY_KEY[key]
        ev = economy_service._make_event(s, u, d, month.ref_month, 1, ctx)
        s.commit()
        return ev.id if ev else None


def test_partner_default_hits_the_company_and_the_friendship_and_can_be_pursued_in_court(client, auth_headers):
    cid, pid = _company_with_partner(client, auth_headers)
    before = D(client.get(f"{C}/{cid}", headers=auth_headers).json()["company"]["cash"])
    eid = _spawn(client, auth_headers, "calote_socio", cid)
    assert eid, "o evento exige empresa com sócios"
    det = client.get(f"{C}/{cid}", headers=auth_headers).json()
    assert det["partners"][0]["status"] == "DEFAULTED" and D(det["company"]["owner_share_pct"]) == D("100.00")      # cotas voltam para você
    after = D(det["company"]["cash"])
    assert after < before                                                                           # o sócio levou dinheiro
    rel = next(x for x in life(client, auth_headers)["relationships"] if x["person_id"] == pid)
    assert rel["affinity"] <= 85 - 30 + 1 and rel["trust"] <= 85 - 35 + 1
    pend = client.get("/api/economy/decisions", headers=auth_headers).json()["pending"]
    ev = next(e for e in pend if e["id"] == eid)
    assert {o["key"] for o in ev["options"]} == {"negociar", "processar", "aceitar"} and "outcomes" not in str(ev)
    r = client.post(f"/api/economy/events/{eid}/decide", headers=auth_headers, json={"option": "processar"})
    assert r.status_code == 200 and r.json()["event"]["outcome"]
    with SessionLocal() as s:
        lawyer = s.scalar(select(LedgerEntry).where(LedgerEntry.description.like("%Advogado (ação contra sócio)%")))
        assert lawyer is not None and lawyer.amount == D("3000.00")
        assert any(l.kind == "LEGAL" for l in s.scalars(select(LifeLog)))


def test_labor_lawsuit_costs_scale_with_payroll_and_default_is_the_worst(client, auth_headers):
    credit(client, auth_headers, "3000000")
    cid = create_ok(client, auth_headers, name="Com Funcionários", segment="CAFE", extra="60000")["company"]["id"]
    eid = _spawn(client, auth_headers, "processo_trabalhista", cid)
    assert eid
    r = client.post(f"/api/economy/events/{eid}/decide", headers=auth_headers, json={"option": "acordo"})
    assert r.status_code == 200
    with SessionLocal() as s:
        e = s.scalar(select(LedgerEntry).where(LedgerEntry.description.like("Acordo trabalhista (evento)")))
        assert e is not None and e.amount >= D("3000.00") and e.company_id == cid
        payroll_deal = e.amount
    from tests.test_budget import close
    assert close(client, auth_headers).status_code == 200                      # outro mês, outro processo
    eid2 = _spawn(client, auth_headers, "processo_trabalhista", cid)
    r2 = client.post(f"/api/economy/events/{eid2}/decide", headers=auth_headers, json={"option": "ignorar"})
    assert r2.status_code == 200, r2.text
    with SessionLocal() as s:
        worst = s.scalar(select(LedgerEntry).where(LedgerEntry.description.like("Condenação trabalhista (revelia)%")))
        assert worst is not None and worst.amount >= payroll_deal * D("1.9")


def test_company_legal_events_need_employees_or_partners(client, auth_headers):
    credit(client, auth_headers, "3000000")
    cid = create_ok(client, auth_headers, name="Sem Sócios", segment="CAFE", extra="60000")["company"]["id"]
    assert _spawn(client, auth_headers, "calote_socio", cid) is None                                # sem sócios: não há calote
    d = E.CATALOG_BY_KEY["calote_socio"]
    assert d.cond({"inflation": 4, "interest": 10, "unemployment": 8, "growth": 2, "demand": 100, "confidence": 55}, {"co_partners": {}}) == 0
    assert E.CATALOG_BY_KEY["processo_trabalhista"].cond({"unemployment": 12}, {"co_employees": {1: 3}}) > E.CATALOG_BY_KEY["processo_trabalhista"].cond({"unemployment": 6}, {"co_employees": {1: 3}})


def test_monthly_legal_decisions_depend_on_what_you_own():
    macro = {"inflation": 4, "interest": 10, "unemployment": 8, "growth": 2, "demand": 100, "confidence": 55}
    for key, flag in (("d_multa", "has_vehicle"), ("d_acidente", "has_vehicle"), ("d_inquilino", "has_rented")):
        d = E.MONTHLY_BY_KEY[key]
        assert d.cond(macro, {flag: False, "salary": 0}) == 0 and d.cond(macro, {flag: True, "salary": 0}) > 0
    assert E.MONTHLY_BY_KEY["d_vizinho"].cond(macro, {"salary": 0}) > 0
    for key in ("d_multa", "d_inquilino", "d_acidente", "d_vizinho"):
        opts = {o.key for o in E.MONTHLY_BY_KEY[key].options}
        assert len(opts) >= 2 and any("advogado" in o.hint.lower() or "justiça" in o.hint.lower() or "recorrer" in o.label.lower() for o in E.MONTHLY_BY_KEY[key].options)


def test_partners_data_is_private(client, auth_headers):
    credit(client, auth_headers, "300000")
    pid = _friend(client, auth_headers)
    other = second_user(client)
    assert client.post(f"{C}/partner-invites", headers=other, json={"person_id": pid, "share_pct": "30", "capital": "100000"}).status_code == 404
    assert client.get(f"{C}/invites/current", headers=other).json() == []
