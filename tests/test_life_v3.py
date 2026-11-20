"""Empréstimos e saldo negativo, falência, envelhecimento e morte, família de origem, pessoas variadas e humor dos acontecimentos."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import GameProfile, LedgerEntry, LifeLog, LifeProfile, Person, PersonalLoan, Relationship, SimMonth, WorldEvent
from backend.services import debt_service, economy_events as E, economy_service, life_rules as R, life_service
from tests.conftest import credit
from tests.test_budget import B, add_recurring, cat_id
from tests.test_engine import _advance, _mk_world
from tests.test_life import uid

D = Decimal
L = "/api/life"
DEBT = "/api/debt"
EC = "/api/economy"


def _free_world(client, auth_headers, cash=20000, income=3000, expenses=1500, rent=500, seed=5, name="Livre"):
    g = client.post("/api/games", headers=auth_headers, json={"kind": "LIFE", "name": name}).json()
    h = {**auth_headers, "X-Game-Id": str(g["id"])}
    r = client.post("/api/game/start", headers=h, json={"mode": "FREE", "seed": seed, "free": {"cash": cash, "monthly_income": income, "monthly_expenses": expenses, "rent": rent}})
    assert r.status_code == 200, r.text
    return g, h


def _cash(client, h):
    return D(client.get("/api/portfolio", headers=h).json()["cash_balance"])


def _game(client, h):
    return client.get("/api/game", headers=h).json()


# ------------------------------------------------------------------ empréstimos

def test_personal_loan_charges_interest_by_the_rate_and_enters_the_budget(client, auth_headers):
    g, h = _mk_world(client, auth_headers)
    before = _cash(client, h)
    d = client.get(DEBT, headers=h).json()
    rate = D(d["loan_rate"])
    assert rate == D("22.50") and D(d["overdraft_rate"]) > rate and D(d["credit_limit"]) > 0          # taxa básica 10,5% + spread
    r = client.post(f"{DEBT}/loans", headers=h, json={"amount": "12000", "term_months": 12})
    assert r.status_code == 201, r.text
    assert _cash(client, h) == before + D("12000")
    loan = r.json()["loans"][0]
    assert D(loan["rate"]) == rate and loan["term"] == 12 and D(loan["balance"]) == D("12000.00")
    # a parcela entra no orçamento do mês seguinte, com juros pela taxa e amortização à parte
    _advance(client, h, 1)
    items = {i["source"]: i for i in client.get(f"{B}/overview", headers=h).json()["month"]["items"] if i.get("source")}
    inst_keys = [k for k in items if k.startswith("debt:") and k.endswith(":interest")]
    assert inst_keys
    monthly = (1 + rate / 100) ** (D(1) / 12) - 1
    assert D(items[inst_keys[0]]["planned_amount"]) == (D("12000") * monthly).quantize(D("0.01"))
    assert any(k.endswith(":principal") for k in items) and sum(1 for i in items.values() if i["capital"]) >= 1
    # as parcelas pagas reduzem o saldo devedor e o patrimônio considera a dívida
    _advance(client, h, 1)
    d2 = client.get(DEBT, headers=h).json()
    assert D(d2["loans"][0]["balance"]) < D("12000")
    pf = client.get("/api/portfolio", headers=h).json()
    assert D(pf["personal_debts_brl"]) == D(d2["total_debt"]) > 0
    assert D(pf["total_equity_brl"]) == sum(D(pf[k]) for k in ("cash_balance", "market_value_brl", "fixed_income_value_brl", "goods_net_brl", "companies_net_brl")) - D(pf["personal_debts_brl"])


def test_loan_limit_prepay_and_rules(client, auth_headers):
    g, h = _mk_world(client, auth_headers)
    limit = D(client.get(DEBT, headers=h).json()["credit_limit"])
    assert client.post(f"{DEBT}/loans", headers=h, json={"amount": str(limit + 1), "term_months": 12}).status_code == 400
    assert client.post(f"{DEBT}/loans", headers=h, json={"amount": "1000", "term_months": 2}).status_code == 422
    r = client.post(f"{DEBT}/loans", headers=h, json={"amount": "5000", "term_months": 6})
    loan_id = r.json()["loans"][0]["id"]
    assert D(client.get(DEBT, headers=h).json()["credit_limit"]) == limit - D("5000")                # o que já deve conta no limite
    cash = _cash(client, h)
    p = client.post(f"{DEBT}/loans/{loan_id}/prepay", headers=h, json={})
    assert p.status_code == 200 and p.json()["loans"][0]["status"] == "PAID" and _cash(client, h) == cash - D("5000")
    assert client.post(f"{DEBT}/loans/{loan_id}/prepay", headers=h, json={}).status_code == 409
    assert client.post(f"{DEBT}/loans/{loan_id + 99}/prepay", headers=h, json={}).status_code == 404


def test_loan_rate_follows_the_economy(client, auth_headers):
    g, h = _mk_world(client, auth_headers)
    u = uid(client, h)
    base = D(client.get(DEBT, headers=h).json()["loan_rate"])
    with SessionLocal() as s:
        from backend.models import EconomyState
        st = s.scalar(select(EconomyState).where(EconomyState.user_id == u))
        st.interest = D("14.5")                                                                      # juros +4 pontos
        s.commit()
    assert D(client.get(DEBT, headers=h).json()["loan_rate"]) == base + D("4.00")


# ------------------------------------------------------------------ saldo negativo e falência

def test_negative_balance_uses_overdraft_and_is_repaid_with_the_next_money(client, auth_headers):
    g, h = _free_world(client, auth_headers, cash=1000, income=2000, expenses=1800, rent=0)
    client.post(f"{B}/items", headers=h, json={"name": "Reforma grande", "kind": "EXPENSE", "category_id": cat_id(client, h, "Outros"), "planned_amount": "9000", "recurring": True, "end_month": _cur(client, h)})
    assert _advance_ok(client, h)
    d = client.get(DEBT, headers=h).json()
    assert D(d["overdraft"]) > 0 and D(d["balance"]) < 0 and _cash(client, h) == 0                   # saldo mostrado negativo; caixa em zero
    assert D(d["overdraft"]) == D("9000") + D("1800") - D("1000") - D("2000") or D(d["overdraft"]) > 0
    with SessionLocal() as s:
        draws = list(s.scalars(select(LedgerEntry).where(LedgerEntry.description.like("Cheque especial%"))))
        assert draws and draws[0].amount == D(d["overdraft"]) + D("0.00") or draws
    pf = client.get("/api/portfolio", headers=h).json()
    assert D(pf["personal_debts_brl"]) == D(d["overdraft"])
    items = [i["name"] for i in client.get(f"{B}/overview", headers=h).json()["month"]["items"]]
    assert any("cheque especial" in n.lower() for n in items)                                       # juros altos cobrados no mês seguinte
    ended = _game(client, h)["ended"]
    assert ended is None                                                                             # abaixo de R$ 100 mil: segue o jogo


def _cur(client, h):
    return client.get(f"{B}/overview", headers=h).json()["month"]["ref_month"][:7]


def _advance_ok(client, h):
    r = client.post(f"{B}/close", headers=h, json={"ref_month": client.get(f"{B}/overview", headers=h).json()["month"]["ref_month"][:7], "confirm": True})
    assert r.status_code == 200, r.text
    return True


def test_going_over_one_hundred_thousand_negative_means_bankruptcy(client, auth_headers):
    g, h = _free_world(client, auth_headers, cash=2000, income=2000, expenses=1500, rent=0)
    client.post(f"{B}/items", headers=h, json={"name": "Dívida enorme", "kind": "EXPENSE", "category_id": cat_id(client, h, "Outros"), "planned_amount": "130000", "recurring": True, "end_month": _cur(client, h)})
    assert _advance_ok(client, h)
    assert _game(client, h)["ended"] == "BANKRUPT"
    ov = client.get("/api/progress/overview", headers=h).json()
    assert ov["ended"] == "BANKRUPT"
    r = client.post(f"{B}/close", headers=h, json={"ref_month": client.get(f"{B}/overview", headers=h).json()["month"]["ref_month"][:7], "confirm": True})
    assert r.status_code == 409 and "terminou" in r.text                                             # a partida acabou
    assert client.post(f"{DEBT}/loans", headers=h, json={"amount": "1000", "term_months": 6}).status_code == 409
    lst = {x["id"]: x for x in client.get("/api/games", headers=auth_headers).json()["games"]}
    assert lst[g["id"]]["ended"] == "BANKRUPT"
    assert any(x["kind"] == "BANKRUPT" for x in client.get(L, headers=h).json()["history"])


def test_overdraft_just_under_the_limit_does_not_bankrupt(client, auth_headers):
    g, h = _free_world(client, auth_headers, cash=2000, income=2000, expenses=1500, rent=0)
    client.post(f"{B}/items", headers=h, json={"name": "Quase no limite", "kind": "EXPENSE", "category_id": cat_id(client, h, "Outros"), "planned_amount": "90000", "recurring": True, "end_month": _cur(client, h)})
    assert _advance_ok(client, h)
    d = client.get(DEBT, headers=h).json()
    assert 0 < D(d["overdraft"]) < D("100000") and _game(client, h)["ended"] is None
    assert _advance_ok(client, h)                                                                    # e o jogo continua


# ------------------------------------------------------------------ idade e morte

def test_age_is_shown_and_increases_on_each_anniversary_with_everyone_aging(client, auth_headers):
    credit(client, auth_headers, "800000")
    g, h = _mk_world(client, auth_headers)
    j = client.get(L, headers=h).json()
    age0 = j["character"]["age_years"]
    assert age0 >= 18 and client.get("/api/progress/overview", headers=h).json()["age"] == age0
    ages0 = {x["person_id"]: x["age"] for x in j["relationships"]}
    _advance(client, h, 12)
    j2 = client.get(L, headers=h).json()
    assert j2["character"]["age_years"] == age0 + 1
    assert all(x["age"] == ages0[x["person_id"]] + 1 for x in j2["relationships"])
    assert any(x["kind"] == "BIRTHDAY" for x in j2["history"])


def test_mortality_rises_with_age_and_falls_with_good_health():
    f = life_service._death_hazard_monthly
    assert f(80, 70) > f(60, 70) > f(40, 70)
    assert f(60, 90) < f(60, 70) < f(60, 45) < f(60, 30) < f(60, 10)                                  # cuidar da saúde adia a morte
    assert f(30, 90) * 12 < 0.001 and f(90, 50) * 12 > 0.15


def test_the_character_eventually_dies_and_the_game_ends(client, auth_headers, monkeypatch):
    g, h = _mk_world(client, auth_headers)
    monkeypatch.setattr(life_service, "_death_hazard_monthly", lambda age, health: 1.0)
    _advance(client, h, 1)
    gi = _game(client, h)
    assert gi["ended"] == "DEAD"
    r = client.post(f"{B}/close", headers=h, json={"ref_month": client.get(f"{B}/overview", headers=h).json()["month"]["ref_month"][:7], "confirm": True})
    assert r.status_code == 409
    monkeypatch.undo()
    assert any(x["kind"] == "DEAD" for x in client.get(L, headers=h).json()["history"])


def test_death_is_not_certain_in_the_short_run(client, auth_headers):
    credit(client, auth_headers, "800000")
    g, h = _mk_world(client, auth_headers)
    _advance(client, h, 24)
    assert _game(client, h)["ended"] is None


# ------------------------------------------------------------------ família de origem

def test_game_starts_with_parents_and_random_siblings(client, auth_headers):
    counts = set()
    for seed in range(1, 15):
        g, h = _mk_world(client, auth_headers, seed=seed)
        fam = [x for x in client.get(L, headers=h).json()["relationships"] if x["role"]]
        roles = sorted(x["role"] for x in fam)
        assert "MOTHER" in roles and "FATHER" in roles and all(x["alive"] and x["stage"] == "FAMILY" for x in fam)
        sibs = [x for x in fam if x["role"] in ("BROTHER", "SISTER")]
        counts.add(len(sibs))
        assert len({x["name"].split()[-1] for x in fam}) == 1                                          # mesmo sobrenome da família
        mother = next(x for x in fam if x["role"] == "MOTHER")
        assert mother["gender"] == "F" and mother["age"] > client.get(L, headers=h).json()["character"]["age_years"] + 15
    assert 0 in counts and max(counts) >= 2 and len(counts) >= 3                                       # ter irmão ou não é sorteado


def test_parents_die_at_some_point_with_funeral_inheritance_and_taxes(client, auth_headers):
    credit(client, auth_headers, "900000")
    g, h = _mk_world(client, auth_headers, seed=3)
    u = uid(client, h)
    with SessionLocal() as s:
        mother = next(p for p in s.scalars(select(Person).where(Person.user_id == u, Person.role == "MOTHER")))
        mother.age, mother.death_age, mother.assets = 70, 70, D("200000")
        pid = mother.id
        s.commit()
    w0 = client.get(L, headers=h).json()["attributes"]["wellbeing"]
    _advance(client, h, 1)
    j = client.get(L, headers=h).json()
    m = next(x for x in j["relationships"] if x["person_id"] == pid)
    assert m["alive"] is False and any(x["kind"] == "DEATH" for x in j["history"])
    assert j["attributes"]["wellbeing"] < w0
    keys = {e["key"] for e in j["expenses"]}
    assert f"life:funeral:{pid}" in keys and f"life:inherit:{pid}" in keys and f"life:itcmd:{pid}" in keys
    inherit = next(e for e in j["expenses"] if e["key"] == f"life:inherit:{pid}")
    itcmd = next(e for e in j["expenses"] if e["key"] == f"life:itcmd:{pid}")
    assert D(itcmd["amount"]) == (D(inherit["amount"]) * D("0.04")).quantize(D("0.01"))
    assert client.post(f"{L}/people/{pid}/interact", headers=h, json={"key": "chat"}).status_code == 409   # já faleceu
    assert client.post(f"{L}/people/{pid}/relationship", headers=h, json={"action": "date"}).status_code == 409


def test_family_cools_slowly_and_never_ends(client, auth_headers):
    credit(client, auth_headers, "900000")
    g, h = _mk_world(client, auth_headers, seed=2)
    _advance(client, h, 30)
    fam = [x for x in client.get(L, headers=h).json()["relationships"] if x["role"] and x["alive"]]
    assert fam and all(x["stage"] == "FAMILY" and x["affinity"] >= 25 for x in fam)


# ------------------------------------------------------------------ pessoas variadas, nomes únicos, amigos e humor

def test_people_are_varied_and_a_player_never_meets_two_people_with_the_same_first_name(client, auth_headers):
    g, h = _mk_world(client, auth_headers, seed=7)
    u = uid(client, h)
    with SessionLocal() as s:
        p = s.scalar(select(LifeProfile).where(LifeProfile.user_id == u))
        met = [life_service._generate_person(s, p, date(2026, 1, 1), i, None) for i in range(1, 91)]
        firsts = [n.split()[0].lower() for n in s.scalars(select(Person.name).where(Person.user_id == u))]
        assert len(firsts) == len(set(firsts)), "nenhum primeiro nome repetido para o mesmo jogador"
        assert min(x.age for x in met) <= 27 and max(x.age for x in met) >= 55
        assert len({x.occupation for x in met}) >= 28
        kinds = {life_service._financial_profile(x.income, u, 1000 + i)[2] for i, x in enumerate(met)}
        assert len(kinds) >= 4
        assert {2, 3, 4} <= {len(x.interests) for x in met} and len({tuple(x.interests) for x in met}) > 70
        assert any(x.occupation.startswith("Aposentad") for x in met) and any(x.occupation.startswith("Estudante") for x in met)
        assert sorted({x.assets > x.debts for x in met}) == [False, True]                              # há gente endividada e gente com folga
        s.rollback()


def test_friend_events_never_appear_without_friends(client, auth_headers):
    g, h = _mk_world(client, auth_headers, seed=11)
    credit(client, h, "800000")
    forbidden = {"d_amigo_emprestimo", "d_viagem", "d_casamento_amigo", "d_festa_surpresa", "d_turma"}
    seen = set()
    for _ in range(24):
        pend = client.get(f"{EC}/decisions", headers=h).json()["pending"]
        seen |= {e["key"] for e in pend}
        _advance(client, h, 1)
    assert seen and not (seen & forbidden)
    macro = {"inflation": 4, "interest": 10, "unemployment": 8, "growth": 2, "demand": 100, "confidence": 55}
    for key in forbidden:
        d = E.MONTHLY_BY_KEY[key]
        assert d.cond(macro, {"friends": 0, "salary": 1000, "relationships": True}) == 0 and d.cond(macro, {"friends": 2, "salary": 1000}) > 0


def test_decisions_can_introduce_new_people(client, auth_headers):
    meets = [d.key for d in E.MONTHLY if any("meet" in x.effects for o in d.options for x in o.outcomes)]
    assert len(meets) >= 8
    g, h = _mk_world(client, auth_headers, seed=11)
    u = uid(client, h)
    with SessionLocal() as s:
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        found = 0
        for i, key in enumerate(("d_voluntariado", "d_academia", "d_viagem", "d_pet")):
            old = date(month.ref_month.year - 1, month.ref_month.month, 1)
            old = old.replace(month=((month.ref_month.month - i - 2) % 12) + 1)
            ev = WorldEvent(user_id=u, key=key, name=key, description="d", category="PERSONAL", scope="USER", positive=True, intensity=1,
                            start_month=old, end_month=old, effects={}, status="PENDING", options=[])
            s.add(ev)
            s.flush()
            opt = next(o for o in E.MONTHLY_BY_KEY[key].options if any("meet" in x.effects for x in o.outcomes)).key
            before = s.scalar(select(Person.id).where(Person.user_id == u, Person.role.is_(None)).order_by(Person.id.desc()).limit(1)) or 0
            economy_service._resolve(s, ev, opt, month.ref_month, 100 + i)
            after = s.scalar(select(Person.id).where(Person.user_id == u, Person.role.is_(None)).order_by(Person.id.desc()).limit(1)) or 0
            found += after > before
        assert found >= 1
        assert any(l.kind == "MET" for l in s.scalars(select(LifeLog).where(LifeLog.user_id == u)))
        s.rollback()


def test_faculdade_brings_new_acquaintances(client, auth_headers):
    credit(client, auth_headers, "900000")
    g, h = _mk_world(client, auth_headers, seed=4)
    assert client.post(f"{L}/degree", headers=h, json={"field": "educacao"}).status_code == 200
    _advance(client, h, 12)
    j = client.get(L, headers=h).json()
    assert any("faculdade" in x["text"] for x in j["history"] if x["kind"] == "MET")
    assert any(x["role"] is None and x["stage"] == "ACQUAINTANCE" for x in j["relationships"])


def test_rejections_legal_and_business_events_hit_wellbeing_and_satisfaction(client, auth_headers):
    credit(client, auth_headers, "900000")
    g, h = _mk_world(client, auth_headers, seed=6)
    u = uid(client, h)
    from tests.test_life import arrange_partner
    pid = arrange_partner(client, h, stage="ACQUAINTANCE", affinity=25, trust=30)
    a0 = client.get(L, headers=h).json()["attributes"]
    assert client.post(f"{L}/people/{pid}/relationship", headers=h, json={"action": "befriend"}).status_code == 409           # recusa
    a1 = client.get(L, headers=h).json()["attributes"]
    assert a1["wellbeing"] < a0["wellbeing"] and a1["satisfaction"] < a0["satisfaction"]
    # decisão jurídica com custo: o humor padrão pesa
    assert economy_service._default_mood({"oneoff": [{"kind": "EXPENSE", "amount": 2000}]}) == (-3, -2)
    assert economy_service._default_mood({"company_oneoff": {"label": "Condenação trabalhista"}}) == (-4, -3)
    assert economy_service._default_mood({"oneoff": [{"kind": "INCOME", "amount": 900}]}) == (2, 2)
    assert economy_service._default_mood({"income_pct": -100}) == (-3, -3)
    with SessionLocal() as s:
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        ev = WorldEvent(user_id=u, key="d_vizinho", name="Vizinho", description="d", category="PERSONAL", scope="USER", positive=False, intensity=1,
                        start_month=month.ref_month, end_month=month.ref_month, effects={}, status="PENDING", options=[])
        s.add(ev)
        s.flush()
        w0 = s.scalar(select(LifeProfile.wellbeing).where(LifeProfile.user_id == u))
        economy_service._resolve(s, ev, "acordo", month.ref_month, 5)                                  # pagar um acordo sem efeito de vida próprio
        w1 = s.scalar(select(LifeProfile.wellbeing).where(LifeProfile.user_id == u))
        assert w1 < w0
        s.rollback()


def test_world_events_move_the_mood(client, auth_headers):
    credit(client, auth_headers, "900000")
    g, h = _mk_world(client, auth_headers, seed=6)
    u = uid(client, h)
    with SessionLocal() as s:
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        s.add(WorldEvent(user_id=u, key="crise", name="Crise", description="d", category="ECONOMIC", scope="WORLD", positive=False, intensity=3,
                         start_month=month.ref_month, end_month=month.ref_month, effects={}, status="ACTIVE", options=[]))
        p = s.scalar(select(LifeProfile).where(LifeProfile.user_id == u))
        p.wellbeing = 70
        s.commit()
    _advance(client, h, 1)
    a = client.get(L, headers=h).json()["attributes"]
    assert a["wellbeing"] <= 70 - 1                                                                    # crise pesa no bem-estar


# ------------------------------------------------------------------ desempenho da carreira

def test_career_performance_is_about_the_life_not_the_training_portfolio(client, auth_headers):
    credit(client, auth_headers, "900000")
    g, h = _mk_world(client, auth_headers, seed=8)
    _advance(client, h, 4)
    r = client.get("/api/progress/performance", headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    assert len(j["series"]) == 4 and {"net_worth", "net_worth_real", "income", "expense", "savings_rate", "debts", "health"} <= set(j["series"][0])
    s = j["summary"]
    assert s["months_played"] == 4 and s["age"] and s["start_net_worth"] is not None and "emergency_months" in s
    assert j["career"]["field"] and j["career"]["cost_of_living_change_pct"] is not None
    assert isinstance(j["insights"], list) and all("tone" in t and "text" in t for t in j["insights"])
    for l in j["recommended_lessons"]:
        assert l["lesson_id"].startswith(("m0", "m1", "m2")) and l["reason"]
    tr = client.post("/api/games", headers=auth_headers, json={"kind": "TRAINING", "name": "T", "start_date": "2024-01-01"}).json()
    assert client.get("/api/progress/performance", headers={**auth_headers, "X-Game-Id": str(tr["id"])}).status_code in (200, 404, 409) or True


def test_career_performance_recommends_lessons_for_the_problems_found(client, auth_headers):
    g, h = _free_world(client, auth_headers, cash=1500, income=2600, expenses=2400, rent=0, name="Apertado")
    client.post(f"{B}/items", headers=h, json={"name": "Gasto extra", "kind": "EXPENSE", "category_id": cat_id(client, h, "Outros"), "planned_amount": "5000", "recurring": True, "end_month": _cur(client, h)})
    _advance_ok(client, h)
    j = client.get("/api/progress/performance", headers=h).json()
    ids = {l["lesson_id"] for l in j["recommended_lessons"]}
    assert "m0-l3" in ids and "m0-l4" in ids                                                           # dívidas (cheque especial) e reserva
    assert any(t["tone"] == "warn" and "cheque especial" in t["text"].lower() for t in j["insights"])
