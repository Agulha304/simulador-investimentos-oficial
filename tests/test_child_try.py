"""Tentar ter um filho: aceite do(a) parceiro(a) + concepção, ambos determinísticos (hash01)."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import Child, LifeProfile, Person, Relationship
from backend.services import life_service as ls
from tests.conftest import credit
from tests.test_budget import close
from tests.test_life import L, advance, arrange_partner, have_child, life, uid

D = Decimal
PG = "/api/progress"


def tune(client, h, pid, person=None, rel=None, profile=None):
    u = uid(client, h)
    with SessionLocal() as s:
        if person:
            for k, v in person.items():
                setattr(s.get(Person, pid), k, v)
        if rel:
            r = s.scalar(select(Relationship).where(Relationship.person_id == pid))
            for k, v in rel.items():
                setattr(r, k, v)
        if profile:
            p = s.scalar(select(LifeProfile).where(LifeProfile.user_id == u))
            for k, v in profile.items():
                setattr(p, k, v)
        s.commit()


def force(monkeypatch, accept=0.0, conceive=0.0):
    monkeypatch.setattr(ls, "_roll", lambda *k: accept if k[0] == "child-accept" else conceive)


def chances(client, h):
    c = life(client, h)["child_try"]
    return c["accept_chance_pct"], c["conceive_chance_pct"]


def add_child(client, h):
    u = uid(client, h)
    with SessionLocal() as s:
        s.add(Child(user_id=u, name="Bia", birth_month=date(2020, 1, 1)))
        s.commit()


def test_partner_who_does_not_want_children_always_refuses(client, auth_headers, monkeypatch):
    pid = arrange_partner(client, auth_headers, wants_children=10, affinity=90, trust=90)
    force(monkeypatch)                                          # mesmo com sorteio "perfeito"
    assert chances(client, auth_headers)[0] == 0
    r = client.post(f"{L}/children/try", headers=auth_headers)
    assert r.status_code == 200 and r.json()["outcome"] == "REFUSED" and "não quer ter filhos" in r.json()["text"]
    assert life(client, auth_headers)["pregnancy_due_month"] is None


def test_accept_chance_rises_with_affinity_trust_marriage_and_falls_with_kids_and_tight_money(client, auth_headers):
    credit(client, auth_headers, "500000")
    pid = arrange_partner(client, auth_headers, stage="COHABITING", affinity=30, trust=30, wants_children=40)
    base = chances(client, auth_headers)[0]
    tune(client, auth_headers, pid, rel={"affinity": 50})
    assert chances(client, auth_headers)[0] > base
    tune(client, auth_headers, pid, rel={"affinity": 30, "trust": 60})
    assert chances(client, auth_headers)[0] > base
    tune(client, auth_headers, pid, rel={"trust": 30, "stage": "MARRIED"})
    assert chances(client, auth_headers)[0] >= base + 10
    tune(client, auth_headers, pid, rel={"stage": "COHABITING"})
    assert chances(client, auth_headers)[0] == base
    add_child(client, auth_headers)
    one = chances(client, auth_headers)[0]
    assert one <= base - 7
    add_child(client, auth_headers)
    assert chances(client, auth_headers)[0] < one


def test_tight_finances_lower_accept_chance(client, auth_headers):
    pid = arrange_partner(client, auth_headers, stage="COHABITING", affinity=30, trust=30, wants_children=40)
    from backend.models import Portfolio
    with SessionLocal() as sx:
        sx.scalar(select(Portfolio).where(Portfolio.user_id == uid(client, auth_headers))).cash_balance = D("0")
        sx.commit()
    tight = chances(client, auth_headers)[0]
    credit(client, auth_headers, "500000")
    assert chances(client, auth_headers)[0] == tight + 10


def test_refusal_has_effects_consumes_the_month_and_hurts_the_next_request(client, auth_headers, monkeypatch):
    pid = arrange_partner(client, auth_headers, stage="COHABITING", affinity=60, trust=50, wants_children=40)
    force(monkeypatch, accept=0.999)
    r = client.post(f"{L}/children/try", headers=auth_headers)
    assert r.status_code == 200 and r.json()["outcome"] == "REFUSED"
    rel = next(x for x in life(client, auth_headers)["relationships"] if x["person_id"] == pid)
    assert (rel["affinity"], rel["trust"]) == (57, 49)
    again = client.post(f"{L}/children/try", headers=auth_headers)
    assert again.status_code == 409 and "já tentaram este mês" in again.json()["detail"]
    c = life(client, auth_headers)["child_try"]
    assert not c["can_try"] and "já tentaram" in c["blocked_reason"]
    # com a recusa recente a chance de aceite cai (compara com o mesmo estado sem a marca da recusa)
    with_refusal = chances(client, auth_headers)[0]
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        s.scalar(select(LifeProfile).where(LifeProfile.user_id == u)).last_child_refusal_month = None
        s.commit()
    assert chances(client, auth_headers)[0] == with_refusal + 10


def test_same_seed_and_month_give_the_same_result(client, auth_headers):
    arrange_partner(client, auth_headers, affinity=50, trust=50, wants_children=50)
    u = uid(client, auth_headers)
    outs = []
    with SessionLocal() as s:
        from backend.services import budget_service as bs
        month = bs.ensure_setup(s, u)
        for _ in range(2):
            outs.append(ls.try_for_child(db=s, user_id=u, month=month))
            s.rollback()                                       # desfaz: mesma semente/mês -> mesmo resultado
    assert outs[0] == outs[1]


def test_conception_probability_follows_the_age_table_and_drops_after_40():
    table = {25: 0.28, 29: 0.28, 30: 0.22, 34: 0.22, 35: 0.14, 37: 0.14, 38: 0.09, 39: 0.09, 40: 0.04, 42: 0.04, 43: 0.015, 50: 0.015}
    for age, prob in table.items():
        assert ls.conception_base(age) == prob
    assert ls.conception_base(43) < ls.conception_base(39) / 5
    p = SimpleNamespace(health=100, wellbeing=100, stress=0, family_time="NORMAL", gender="M", age_years=30)
    assert round(ls.health_factor(p), 3) == 1.1
    p.health = p.wellbeing = 0
    p.stress = 100
    assert round(ls.health_factor(p), 3) == 0.7
    p.family_time = "HIGH"
    assert round(ls.health_factor(p), 3) == 0.77


def test_fertile_age_rule():
    me = lambda g, a: SimpleNamespace(gender=g, age_years=a)
    other = lambda g, a: SimpleNamespace(gender=g, age=a)
    assert ls.fertile_age(me("M", 45), other("F", 28)) == 28           # parceira F: idade dela
    assert ls.fertile_age(me("F", 31), other("M", 50)) == 31           # jogadora F, parceiro M: idade dela
    assert ls.fertile_age(me("M", 30), other("M", 40)) == 35           # sem mulher / sem dado: média
    assert ls.fertile_age(me("N", 30), other("M", 40)) == 35
    assert ls.fertile_age(me("F", 31), other("F", 29)) == 29           # casal F+F: a parceira (regra de precedência)


def test_failure_increments_tries_and_success_resets_and_saves_pregnancy(client, auth_headers, monkeypatch):
    arrange_partner(client, auth_headers, wants_children=80)
    force(monkeypatch, accept=0.0, conceive=0.999)
    r = client.post(f"{L}/children/try", headers=auth_headers)
    assert r.status_code == 200 and r.json()["outcome"] == "NOT_CONCEIVED" and "mês que vem" in r.json()["text"]
    assert life(client, auth_headers)["child_try"]["tries"] == 1 and life(client, auth_headers)["pregnancy_due_month"] is None
    advance(client, auth_headers)
    assert client.post(f"{L}/children/try", headers=auth_headers).json()["outcome"] == "NOT_CONCEIVED"
    assert life(client, auth_headers)["child_try"]["tries"] == 2
    advance(client, auth_headers)
    force(monkeypatch)
    j = client.post(f"{L}/children/try", headers=auth_headers).json()
    assert j["outcome"] == "PREGNANT" and j["pregnancy_due_month"] and j["child_try"]["tries"] == 0
    assert j["accept_chance_pct"] is not None and j["conceive_chance_pct"] is not None
    assert any(h["kind"] == "PREGNANCY" for h in j["history"])


def test_needs_a_cohabiting_partner_and_no_ongoing_pregnancy(client, auth_headers, monkeypatch):
    life(client, auth_headers)
    assert client.post(f"{L}/children/try", headers=auth_headers).status_code == 409
    assert life(client, auth_headers)["child_try"]["can_try"] is False
    pid = arrange_partner(client, auth_headers, stage="DATING")
    assert client.post(f"{L}/children/try", headers=auth_headers).status_code == 409
    tune(client, auth_headers, pid, rel={"stage": "COHABITING"})
    have_child(client, auth_headers, monkeypatch)
    r = client.post(f"{L}/children/try", headers=auth_headers)
    assert r.status_code == 409 and "gestação" in r.json()["detail"]


def test_overview_child_try_is_coherent(client, auth_headers):
    pid = arrange_partner(client, auth_headers, wants_children=70)
    c = life(client, auth_headers)["child_try"]
    assert c["can_try"] and c["blocked_reason"] is None and c["partner_name"] == "Camila" and c["tries"] == 0
    assert 5 <= c["accept_chance_pct"] <= 90 and 20 <= c["conceive_chance_pct"] <= 35
    assert c["last_try_month"] is None and c["pregnancy_due_month"] is None


def test_birth_after_nine_months_unlocks_first_child(client, auth_headers, monkeypatch):
    arrange_partner(client, auth_headers, wants_children=80)
    have_child(client, auth_headers, monkeypatch)
    advance(client, auth_headers, 9)
    assert len(life(client, auth_headers)["children"]) == 1
    got = {a["key"]: a["unlocked"] for a in client.get(f"{PG}/achievements", headers=auth_headers).json()}
    assert got["first_child"]


def test_pregnancy_continues_if_partner_leaves_and_it_is_logged(client, auth_headers, monkeypatch):
    pid = arrange_partner(client, auth_headers, wants_children=80)
    have_child(client, auth_headers, monkeypatch)
    assert client.post(f"{L}/people/{pid}/relationship", headers=auth_headers, json={"action": "end"}).status_code == 200
    j = life(client, auth_headers)
    assert j["pregnancy_due_month"] and any(h["kind"] == "PREGNANCY_PARTNER_LEFT" for h in j["history"])
    advance(client, auth_headers, 9)
    assert len(life(client, auth_headers)["children"]) == 1


def test_statistics_by_age_are_in_expected_bands():
    """Taxa de concepção por tentativa em 1000 sementes (hash determinístico: sem flakiness)."""
    def rate(age):
        p = SimpleNamespace(health=70, wellbeing=65, stress=0, family_time="NORMAL", gender="N", age_years=age)
        person = SimpleNamespace(gender="F", age=age)
        prob = ls.conception_probability(p, person)
        return sum(ls.R.hash01("child-conceive", seed, 1, 1, "2026-01-01") < prob for seed in range(1000)) / 1000
    young, old = rate(25), rate(43)
    assert 0.22 <= young <= 0.34
    assert old <= 0.05 and young > 4 * old
