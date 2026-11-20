"""Vida pessoal e família (etapa 4): personagem, pessoas, relacionamentos, filhos, orçamento familiar e isolamento."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import BudgetItem, Child, EntryOrigin, LedgerEntry, LifeLog, Person, Relationship
from tests.conftest import credit
from tests.test_budget import B, cat_id, close, overview, second_user

D = Decimal
L = "/api/life"


def life(client, h):
    r = client.get(L, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def uid(client, h):
    return client.get("/api/auth/me", headers=h).json()["id"]


def advance(client, h, n=1):
    for _ in range(n):
        assert close(client, h).status_code == 200


def arrange_partner(client, h, stage="MARRIED", affinity=80, trust=70, income="8000", wants_children=70, debts="0"):
    """Cria um parceiro direto no banco (cenário de teste) e devolve o person_id."""
    life(client, h)                                  # garante o mês aberto e o perfil de vida
    u = uid(client, h)
    with SessionLocal() as s:
        from backend.models import SimMonth
        ref = s.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        p = Person(user_id=u, name="Camila", age=29, personality="tranquilo", interests=["viagens", "cultura"],
                   occupation="Analista", income=D(income), assets=D("20000"), debts=D(debts), sociability=60,
                   wants_children=wants_children, preferences={}, met_month=ref)
        s.add(p)
        s.flush()
        s.add(Relationship(user_id=u, person_id=p.id, stage=stage, affinity=affinity, trust=trust,
                           since_month=date(ref.year - 1, ref.month, 1), stage_since=date(ref.year - 1, ref.month, 1)))
        s.commit()
        return p.id


def family_items(client, h):
    u = uid(client, h)
    with SessionLocal() as s:
        return {bi.source_key: bi for bi in s.scalars(select(BudgetItem).where(
            BudgetItem.user_id == u, BudgetItem.source_key.is_not(None)))
            if bi.source_key.startswith(("family:", "child:", "life:"))}


# ------------------------------------------------------------------ personagem e atributos

def test_create_character_and_default_attributes(client, auth_headers):
    r = client.put(f"{L}/character", headers=auth_headers, json={"name": "Giulia", "age_years": 31})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["character"] == {"name": "Giulia", "age_years": 31}
    a = j["attributes"]
    assert all(0 <= a[k] <= 100 for k in ("health", "wellbeing", "quality", "satisfaction", "social", "financial_stability"))
    assert client.put(f"{L}/character", headers=auth_headers, json={"name": "X", "age_years": 12}).status_code == 422


def test_overwork_reduces_time_and_wellbeing_while_health_investment_helps(client, auth_headers):
    credit(client, auth_headers, "100000")
    base = life(client, auth_headers)["attributes"]
    r = client.put(f"{L}/choices", headers=auth_headers, json={"work_level": "INTENSE", "health_level": "NONE"})
    assert r.status_code == 200
    a = r.json()["attributes"]
    assert a["free_hours_total"] < base["free_hours_total"]
    advance(client, auth_headers, 3)
    after = life(client, auth_headers)["attributes"]
    assert after["wellbeing"] < base["wellbeing"] and after["health"] < base["health"]
    # investir em saúde e reduzir jornada reverte a tendência (a um custo)
    client.put(f"{L}/choices", headers=auth_headers, json={"work_level": "REDUCED", "health_level": "PLUS"})
    advance(client, auth_headers, 4)
    better = life(client, auth_headers)["attributes"]
    assert better["health"] > after["health"]
    items = family_items(client, auth_headers)
    assert "life:style:health_level" in items and items["life:style:health_level"].kind.value == "EXPENSE"


def test_invalid_choice_rejected(client, auth_headers):
    assert client.put(f"{L}/choices", headers=auth_headers, json={"food_level": "LUXO"}).status_code == 400


def test_work_level_changes_income_via_budget(client, auth_headers):
    cat = cat_id(client, auth_headers, "Salário", "INCOME")
    client.post(f"{B}/items", headers=auth_headers, json={"name": "Salário", "kind": "INCOME", "category_id": cat,
                                                         "planned_amount": "5000", "recurring": True})
    client.put(f"{L}/choices", headers=auth_headers, json={"work_level": "INTENSE"})
    item = family_items(client, auth_headers)["life:work_adjust"]
    assert item.kind.value == "INCOME" and item.planned_amount == D("1000.00")
    client.put(f"{L}/choices", headers=auth_headers, json={"work_level": "REDUCED"})
    item = family_items(client, auth_headers)["life:work_adjust"]
    assert item.kind.value == "EXPENSE" and item.planned_amount == D("750.00")
    client.put(f"{L}/choices", headers=auth_headers, json={"work_level": "NORMAL"})
    assert "life:work_adjust" not in family_items(client, auth_headers)


# ------------------------------------------------------------------ pessoas e relacionamentos

def test_meeting_people_through_free_and_paid_activities(client, auth_headers):
    credit(client, auth_headers, "100000")
    met = None
    for i in range(60):
        r = client.post(f"{L}/activities", headers=auth_headers, json={"key": "volunteer"})   # gratuita
        if r.status_code == 409:                      # sem horas livres: avança o mês
            advance(client, auth_headers)
            continue
        assert r.status_code == 200, r.text
        if r.json()["result"]["met"]:
            met = r.json()["result"]["met"]
            break
    assert met, "atividades gratuitas devem permitir conhecer pessoas (sem depender de dinheiro)"
    j = life(client, auth_headers)
    rel = j["relationships"][0]
    assert rel["stage"] == "ACQUAINTANCE" and rel["name"] == met
    assert 0 <= rel["compatibility"] <= 100 and rel["interests"]
    assert any(h["kind"] == "MET" for h in j["history"])


def test_paid_activity_charges_ledger_with_family_origin_and_consumes_time(client, auth_headers):
    credit(client, auth_headers, "10000")
    before = D(client.get("/api/portfolio", headers=auth_headers).json()["cash_balance"])
    left = life(client, auth_headers)["attributes"]["free_hours_left"]
    r = client.post(f"{L}/activities", headers=auth_headers, json={"key": "restaurant"})
    assert r.status_code == 200
    after = D(client.get("/api/portfolio", headers=auth_headers).json()["cash_balance"])
    assert after == before - D(r.json()["result"]["cost"]) and D(r.json()["result"]["cost"]) == D("180.00")
    assert r.json()["attributes"]["free_hours_left"] == left - 6
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        e = s.scalar(select(LedgerEntry).where(LedgerEntry.user_id == u, LedgerEntry.origin == EntryOrigin.FAMILY))
        assert e is not None and e.amount == D("180.00")


def test_not_enough_free_time_blocks_activity(client, auth_headers):
    credit(client, auth_headers, "100000")
    client.put(f"{L}/choices", headers=auth_headers, json={"work_level": "INTENSE", "family_time": "NORMAL"})   # 40h
    assert client.post(f"{L}/activities", headers=auth_headers, json={"key": "trip"}).status_code == 200   # 30h de 40h
    assert client.post(f"{L}/activities", headers=auth_headers, json={"key": "trip"}).status_code == 409


def test_relationship_evolves_from_acquaintance_to_marriage_and_can_end(client, auth_headers):
    credit(client, auth_headers, "200000")
    pid = arrange_partner(client, auth_headers, stage="ACQUAINTANCE", affinity=20, trust=20)
    rel = lambda a: client.post(f"{L}/people/{pid}/relationship", headers=auth_headers, json={"action": a})   # noqa: E731
    assert rel("befriend").status_code == 409                       # ainda sem intimidade
    for _ in range(5):                                              # conviver, de graça e pagando
        assert client.post(f"{L}/people/{pid}/interact", headers=auth_headers, json={"key": "walk"}).status_code == 200
    assert rel("befriend").status_code == 200
    assert rel("date").status_code == 409                           # afinidade ainda baixa
    advance(client, auth_headers)
    for _ in range(8):
        r = client.post(f"{L}/people/{pid}/interact", headers=auth_headers, json={"key": "outing" if _ % 2 else "chat"})
        if r.status_code == 409:
            advance(client, auth_headers)
    with SessionLocal() as s:      # garante os requisitos para testar as demais transições (cenário)
        r_ = s.scalar(select(Relationship).where(Relationship.person_id == pid))
        r_.affinity, r_.trust = 90, 80
        s.commit()
    assert rel("date").status_code == 200
    with SessionLocal() as s:      # a relação começou agora (cenário): ainda é cedo para casar
        r_ = s.scalar(select(Relationship).where(Relationship.person_id == pid))
        r_.since_month = r_.stage_since
        s.commit()
    assert rel("marry").status_code == 409                          # cedo demais: precisa de tempo
    advance(client, auth_headers, 7)
    with SessionLocal() as s:
        r_ = s.scalar(select(Relationship).where(Relationship.person_id == pid))
        r_.affinity, r_.trust = 90, 80
        s.commit()
    assert rel("marry").status_code == 200
    assert next(x for x in life(client, auth_headers)["relationships"] if x["person_id"] == pid)["stage"] == "MARRIED"
    assert rel("end").status_code == 200
    j = life(client, auth_headers)
    assert j["relationships"][0]["stage"] == "ENDED"
    assert rel("befriend").status_code == 409                       # encerrado


def test_relationship_cools_down_without_interaction(client, auth_headers):
    credit(client, auth_headers, "100000")
    pid = arrange_partner(client, auth_headers, stage="FRIEND", affinity=50, trust=50)
    advance(client, auth_headers, 3)
    r = next(x for x in life(client, auth_headers)["relationships"] if x["person_id"] == pid)
    assert r["affinity"] < 50
    advance(client, auth_headers, 20)
    assert next(x for x in life(client, auth_headers)["relationships"] if x["person_id"] == pid)["stage"] in ("FRIEND", "ENDED")
    again = next(x for x in life(client, auth_headers)["relationships"] if x["person_id"] == pid)
    assert again["affinity"] <= 10 or again["stage"] == "FRIEND"


def test_compatibility_does_not_depend_on_wealth(client, auth_headers):
    pid = arrange_partner(client, auth_headers, stage="FRIEND", income="1500")
    a = next(x for x in life(client, auth_headers)["relationships"] if x["person_id"] == pid)["compatibility"]
    with SessionLocal() as s:
        p = s.get(Person, pid)
        p.income, p.assets = D("90000"), D("5000000")
        s.commit()
    b = next(x for x in life(client, auth_headers)["relationships"] if x["person_id"] == pid)["compatibility"]
    assert a == b


def test_marriage_requires_commitment_stage(client, auth_headers):
    pid = arrange_partner(client, auth_headers, stage="FRIEND")
    r = client.post(f"{L}/people/{pid}/relationship", headers=auth_headers, json={"action": "marry"})
    assert r.status_code == 409


# ------------------------------------------------------------------ família, filhos e orçamento

def test_partner_contribution_shared_vs_separate(client, auth_headers):
    credit(client, auth_headers, "100000")
    pid = arrange_partner(client, auth_headers, stage="MARRIED")
    client.post(f"{L}/move", headers=auth_headers, json={"kind": "SHARED", "monthly_cost": "3000"})
    advance(client, auth_headers)
    items = family_items(client, auth_headers)
    assert items["family:housing"].planned_amount == D("3000.00")
    assert "family:partner:contribution" not in items                # separado por padrão
    r = client.put(f"{L}/people/{pid}/finances", headers=auth_headers, json={"mode": "SHARED", "contribution_pct": "40"})
    assert r.status_code == 200, r.text
    c = family_items(client, auth_headers)["family:partner:contribution"]
    assert c.kind.value == "INCOME" and c.planned_amount == D("1200.00")
    client.put(f"{L}/people/{pid}/finances", headers=auth_headers, json={"mode": "SEPARATE"})
    assert "family:partner:contribution" not in family_items(client, auth_headers)


def test_partner_debts_and_income_cap_contribution(client, auth_headers):
    pid = arrange_partner(client, auth_headers, stage="MARRIED", income="2000", debts="50000")   # teto = 2000*0.5 - 500
    client.post(f"{L}/move", headers=auth_headers, json={"kind": "SHARED", "monthly_cost": "6000"})
    credit(client, auth_headers, "100000")
    advance(client, auth_headers)
    client.put(f"{L}/people/{pid}/finances", headers=auth_headers, json={"mode": "SHARED", "contribution_pct": "100"})
    assert family_items(client, auth_headers)["family:partner:contribution"].planned_amount == D("500.00")


def test_separate_finance_requires_household(client, auth_headers):
    pid = arrange_partner(client, auth_headers, stage="DATING")
    assert client.put(f"{L}/people/{pid}/finances", headers=auth_headers, json={"mode": "SHARED"}).status_code == 409


def test_child_birth_ages_and_family_expenses_flow_into_budget(client, auth_headers):
    credit(client, auth_headers, "500000")
    arrange_partner(client, auth_headers, stage="MARRIED", wants_children=80)
    assert client.post(f"{L}/children/plan", headers=auth_headers).status_code == 200
    assert client.post(f"{L}/children/plan", headers=auth_headers).status_code == 409      # já em gestação
    advance(client, auth_headers, 8)
    assert life(client, auth_headers)["children"] == []
    advance(client, auth_headers)                                                          # 9º mês: nascimento
    j = life(client, auth_headers)
    assert len(j["children"]) == 1 and j["children"][0]["age_years"] == 0
    kid = j["children"][0]
    items = family_items(client, auth_headers)
    assert f"life:birth:{kid['id']}" in items
    for line in ("food", "health", "clothing", "leisure", "housing"):
        assert f"child:{kid['id']}:{line}" in items
    assert f"child:{kid['id']}:education" not in items                                    # bebê sem creche
    assert all(e["origin"] in ("Filho(a)", "Estilo de vida", "Moradia compartilhada", "Parceiro(a)") for e in j["expenses"])
    # a despesa é lançada no fechamento, com origem FAMILY, sem duplicar
    advance(client, auth_headers)
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        entries = list(s.scalars(select(LedgerEntry).where(LedgerEntry.user_id == u, LedgerEntry.origin == EntryOrigin.FAMILY)))
        keys = [e.origin_ref for e in entries]
        assert len(keys) == len(set((k, e.ref_month) for k, e in zip(keys, entries)))
        assert any(k.startswith(f"child:{kid['id']}:") for k in keys)
    # creche passa a custar
    client.patch(f"{L}/children/{kid['id']}", headers=auth_headers, json={"daycare": True})
    assert family_items(client, auth_headers)[f"child:{kid['id']}:education"].planned_amount == D("900.00")


def test_children_needs_change_with_age_and_school(client, auth_headers):
    credit(client, auth_headers, "2000000")
    u = uid(client, auth_headers)
    advance(client, auth_headers)     # cria o perfil/estado
    client.put(f"{L}/character", headers=auth_headers, json={"name": "Pai", "age_years": 35})
    with SessionLocal() as s:
        from backend.models import SimMonth
        ref = s.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        # nasceu há 35 meses: faz 3 anos daqui a 1 mês (entra na escola)
        k = Child(user_id=u, name="Nina", birth_month=date((ref.year * 12 + ref.month - 1 - 35) // 12, (ref.year * 12 + ref.month - 1 - 35) % 12 + 1, 1))
        s.add(k)
        s.commit()
        kid_id = k.id
    client.put(f"{L}/choices", headers=auth_headers, json={"family_time": "NORMAL"})
    before = family_items(client, auth_headers)
    assert f"child:{kid_id}:education" not in before
    advance(client, auth_headers)
    j = life(client, auth_headers)
    assert j["children"][0]["age_years"] == 3
    assert any(h["kind"] == "SCHOOL_ENTRY" for h in j["history"])
    items = family_items(client, auth_headers)
    assert items[f"child:{kid_id}:education"].planned_amount == D("80.00")                 # pública
    client.patch(f"{L}/children/{kid_id}", headers=auth_headers, json={"school_kind": "PRIVATE", "activities": True})
    items = family_items(client, auth_headers)
    assert items[f"child:{kid_id}:education"].planned_amount == D("1200.00")
    assert items[f"child:{kid_id}:leisure"].planned_amount == D("120.00")                  # atividades só a partir dos 4 anos
    assert any(h["kind"] == "SCHOOL_CHANGE" for h in life(client, auth_headers)["history"])


def test_move_ends_old_costs_and_starts_new_in_correct_month(client, auth_headers):
    credit(client, auth_headers, "300000")
    r = client.post(f"{L}/move", headers=auth_headers, json={"kind": "RENT", "monthly_cost": "2500"})
    assert r.status_code == 200 and r.json()["housing"]["pending"]["kind"] == "RENT"
    assert "family:housing" not in family_items(client, auth_headers)                      # ainda não: só no mês que vem
    advance(client, auth_headers)
    items = family_items(client, auth_headers)
    assert items["family:housing"].planned_amount == D("2500.00")
    assert any(k.startswith("life:move:") for k in items)                                  # custo único da mudança
    j = life(client, auth_headers)
    assert j["housing"]["kind"] == "RENT" and j["housing"]["pending"] is None
    client.post(f"{L}/move", headers=auth_headers, json={"kind": "SHARED", "monthly_cost": "1800"})
    advance(client, auth_headers)
    items = family_items(client, auth_headers)
    assert items["family:housing"].planned_amount == D("1800.00")
    # mês anterior continua com o custo antigo no histórico
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        e = list(s.scalars(select(LedgerEntry).where(LedgerEntry.user_id == u, LedgerEntry.origin_ref == "family:housing")))
        assert [x.amount for x in sorted(e, key=lambda x: x.ref_month)] == [D("2500.00")]


def test_closing_month_is_idempotent_for_life_processing(client, auth_headers):
    credit(client, auth_headers, "100000")
    client.put(f"{L}/choices", headers=auth_headers, json={"work_level": "INTENSE"})
    assert close(client, auth_headers).status_code == 200
    h1 = life(client, auth_headers)["attributes"]
    r = client.post(f"{B}/close", headers=auth_headers, json={"ref_month": "2000-01", "confirm": True})
    assert r.status_code in (404, 409)
    assert life(client, auth_headers)["attributes"] == h1


def test_life_data_is_isolated_between_users(client, auth_headers):
    credit(client, auth_headers, "100000")
    other = second_user(client)
    pid = arrange_partner(client, auth_headers, stage="FRIEND")
    assert life(client, other)["relationships"] == []
    assert client.post(f"{L}/people/{pid}/interact", headers=other, json={"key": "chat"}).status_code == 404
    assert client.post(f"{L}/people/{pid}/relationship", headers=other, json={"action": "befriend"}).status_code == 404
    client.put(f"{L}/choices", headers=auth_headers, json={"food_level": "PREMIUM"})
    assert life(client, other)["choices"]["food_level"] == "NORMAL"
    assert client.get(L).status_code in (401, 403)


# ------------------------------------------------------------------ recusas e esfriamento

def _rel(client, h, pid):
    return next(x for x in life(client, h)["relationships"] if x["person_id"] == pid)


def test_refused_invitation_lowers_affinity_and_the_penalty_is_saved(client, auth_headers):
    credit(client, auth_headers, "100000")
    pid = arrange_partner(client, auth_headers, stage="ACQUAINTANCE", affinity=25, trust=30)
    before = _rel(client, auth_headers, pid)
    r = client.post(f"{L}/people/{pid}/relationship", headers=auth_headers, json={"action": "befriend"})
    assert r.status_code == 409 and "diminuiu" in r.text
    after = _rel(client, auth_headers, pid)
    assert after["affinity"] == before["affinity"] - 3 and after["trust"] == before["trust"] - 2 and after["stage"] == "ACQUAINTANCE"
    # amigo recusando namoro: perde mais
    with SessionLocal() as s:
        rel = s.scalar(select(Relationship).where(Relationship.person_id == pid))
        rel.stage, rel.affinity, rel.trust = "FRIEND", 40, 30
        s.commit()
    r = client.post(f"{L}/people/{pid}/relationship", headers=auth_headers, json={"action": "date"})
    assert r.status_code == 409
    assert _rel(client, auth_headers, pid)["affinity"] == 35
    # repetir o convite insistente continua custando afinidade, sem nunca passar de 0
    for _ in range(12):
        client.post(f"{L}/people/{pid}/relationship", headers=auth_headers, json={"action": "date"})
    assert _rel(client, auth_headers, pid)["affinity"] == 0


def test_accepted_invitation_does_not_cost_affinity(client, auth_headers):
    credit(client, auth_headers, "100000")
    pid = arrange_partner(client, auth_headers, stage="ACQUAINTANCE", affinity=60, trust=60)
    assert client.post(f"{L}/people/{pid}/relationship", headers=auth_headers, json={"action": "befriend"}).status_code == 200
    assert _rel(client, auth_headers, pid)["affinity"] == 60


def test_affinity_falls_faster_the_longer_nothing_is_done_together(client, auth_headers):
    credit(client, auth_headers, "300000")
    pid = arrange_partner(client, auth_headers, stage="FRIEND", affinity=95, trust=60)
    with SessionLocal() as s:
        rel = s.scalar(select(Relationship).where(Relationship.person_id == pid))
        rel.since_month = rel.stage_since = rel.stage_since.replace(year=rel.stage_since.year + 1)      # convivência recém-começada
        s.commit()
    drops, prev = [], 95
    for _ in range(8):
        advance(client, auth_headers)
        now = _rel(client, auth_headers, pid)["affinity"]
        drops.append(prev - now)
        prev = now
        if now <= 12:
            break
    assert drops[0] >= 2 and max(drops) > drops[0], drops          # a queda aumenta com o tempo parado
    # fazer algo juntos zera a contagem do esfriamento
    pid2 = arrange_partner(client, auth_headers, stage="FRIEND", affinity=60, trust=60)
    advance(client, auth_headers, 3)
    idle = _rel(client, auth_headers, pid2)["affinity"]
    assert idle < 60
    client.post(f"{L}/people/{pid2}/interact", headers=auth_headers, json={"key": "chat"})
    with SessionLocal() as s:
        assert s.scalar(select(Relationship.last_interaction_month).where(Relationship.person_id == pid2)) is not None
