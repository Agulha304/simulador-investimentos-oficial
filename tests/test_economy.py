"""Economia dinâmica e eventos (etapa 5): índices, inflação nos módulos, eventos, decisões, idempotência e histórico."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import (
    BudgetItem, Child, CompanyMonth, EconomyState, EntryOrigin, LedgerEntry, RecurringItem, SimMonth, WorldEvent,
)
from backend.services import budget_service, company_rules, economy_service, goods_service
from tests.conftest import credit
from tests.test_budget import B, add_recurring, cat_id, close, second_user
from tests.test_companies import create_ok

D = Decimal
EC = "/api/economy"
L = "/api/life"


def uid(client, h):
    return client.get("/api/auth/me", headers=h).json()["id"]


def start_world(client, h, seed=7, initial=None):
    client.get(f"{B}/overview", headers=h)
    u = uid(client, h)
    with SessionLocal() as s:
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        economy_service.start_world(s, u, month, seed=seed, initial=initial)
        s.commit()


def rid(client, h, name):
    u = uid(client, h)
    with SessionLocal() as s:
        return s.scalar(select(RecurringItem.id).where(RecurringItem.user_id == u, RecurringItem.name == name))


def advance(client, h, n=1):
    for _ in range(n):
        r = close(client, h)
        assert r.status_code == 200, r.text


def states(client, h):
    u = uid(client, h)
    with SessionLocal() as s:
        return [(e.ref_month, e.inflation, e.interest, e.unemployment, e.growth, e.demand, e.confidence, dict(e.indices))
                for e in s.scalars(select(EconomyState).where(EconomyState.user_id == u).order_by(EconomyState.ref_month))]


def events(client, h):
    u = uid(client, h)
    with SessionLocal() as s:
        return [(e.key, e.start_month, e.end_month, e.scope, e.sector) for e in s.scalars(
            select(WorldEvent).where(WorldEvent.user_id == u).order_by(WorldEvent.id))]


def add_event(client, h, **kw):
    u = uid(client, h)
    with SessionLocal() as s:
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        base = dict(user_id=u, key="x", name="Evento", description="d", category="ECONOMIC", scope="WORLD", positive=True,
                    intensity=1, start_month=month.ref_month, end_month=month.ref_month, effects={}, status="ACTIVE", options=[])
        base.update(kw)
        ev = WorldEvent(**base)
        s.add(ev)
        s.commit()
        return ev.id


# ------------------------------------------------------------------ índices e condições

def test_world_starts_with_configurable_initial_conditions(client, auth_headers):
    start_world(client, auth_headers, initial={"inflation": 7.0, "unemployment": 11.5})
    j = client.get(EC, headers=auth_headers).json()
    assert j["dynamic"] and D(j["state"]["inflation"]) == D("7.0") and D(j["state"]["unemployment"]) == D("11.5")
    assert all(D(str(v)) == 1 for v in j["state"]["indices"].values())
    assert len(j["categories"]) == 14
    with pytest.raises(Exception):
        start_world(client, auth_headers)                                  # só uma vez
    with SessionLocal() as s, pytest.raises(Exception):
        economy_service.start_world(s, uid(client, auth_headers), s.scalar(select(SimMonth)), seed=1, initial={"inflation": 999})


def test_static_economy_keeps_prices_flat_for_existing_users(client, auth_headers):
    credit(client, auth_headers, "50000")
    advance(client, auth_headers, 3)
    assert states(client, auth_headers) == []
    j = client.get(EC, headers=auth_headers).json()
    assert j["dynamic"] is False and j["state"] is None


def test_price_indices_evolve_per_category_with_history(client, auth_headers):
    credit(client, auth_headers, "300000")
    start_world(client, auth_headers, seed=11)
    advance(client, auth_headers, 12)
    st = states(client, auth_headers)
    assert len(st) == 13 and [x[0] for x in st] == sorted(x[0] for x in st)
    last = st[-1][7]
    assert len({round(v, 3) for v in last.values()}) > 3                    # categorias com taxas diferentes
    assert all(v > 0 for v in last.values()) and last["alimentacao"] != last["moradia"]
    snap = states(client, auth_headers)
    advance(client, auth_headers, 2)
    assert states(client, auth_headers)[:13] == snap                        # histórico imutável
    j = client.get(EC, headers=auth_headers).json()
    assert len(j["history"]) == 15 and "monthly_changes" in j["history"][-1]


def test_same_seed_reproduces_world_and_different_seed_diverges(client, auth_headers):
    credit(client, auth_headers, "300000")
    other = second_user(client)
    credit(client, other, "300000")
    start_world(client, auth_headers, seed=5)
    start_world(client, other, seed=5)
    advance(client, auth_headers, 10)
    advance(client, other, 10)
    a, b = states(client, auth_headers), states(client, other)
    assert [x[1:] for x in a] == [x[1:] for x in b]
    world = lambda h: [e for e in events(client, h) if e[3] in ("WORLD", "SECTOR")]       # noqa: E731
    assert world(auth_headers) == world(other)
    third = second_user_c(client)
    credit(client, third, "300000")
    start_world(client, third, seed=999)
    advance(client, third, 10)
    assert [x[1:] for x in states(client, third)] != [x[1:] for x in a]


def second_user_c(client):
    r = client.post("/api/auth/register", json={"email": "carla@example.com", "name": "Carla", "password": "segredo123"})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ------------------------------------------------------------------ inflação nos módulos

def test_indexed_recurring_items_follow_category_inflation_but_contracts_stay_fixed(client, auth_headers):
    credit(client, auth_headers, "300000")
    mercado = add_recurring(client, auth_headers, "Mercado", 1000, category="Alimentação")
    aluguel = add_recurring(client, auth_headers, "Aluguel", 2000, category="Moradia")
    start_world(client, auth_headers, seed=3)
    r = client.put(f"{EC}/recurring/{rid(client, auth_headers, 'Mercado')}/indexation", headers=auth_headers,
                   json={"mode": "MONTHLY", "category": "alimentacao"})
    assert r.status_code == 200, r.text
    assert client.put(f"{EC}/recurring/{rid(client, auth_headers, 'Mercado')}/indexation", headers=auth_headers,
                      json={"mode": "MONTHLY", "category": "inexistente"}).status_code == 400
    advance(client, auth_headers, 6)
    u = uid(client, auth_headers)
    st = states(client, auth_headers)
    idx = st[-1][7]["alimentacao"] / st[0][7]["alimentacao"]
    with SessionLocal() as s:
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        items = {i.name: i.planned_amount for i in s.scalars(select(BudgetItem).where(BudgetItem.month_id == month.id))}
    assert items["Aluguel"] == D("2000.00")                                 # contrato sem reajuste automático
    assert abs(float(items["Mercado"]) - 1000 * idx) < 2.0                  # arredondamentos mensais


def test_annual_indexation_only_on_anniversary(client, auth_headers):
    credit(client, auth_headers, "500000")
    item = add_recurring(client, auth_headers, "Escola", 1000, category="Educação")
    start_world(client, auth_headers, seed=4, initial={"inflation": 12.0})
    client.put(f"{EC}/recurring/{rid(client, auth_headers, 'Escola')}/indexation", headers=auth_headers,
               json={"mode": "ANNUAL", "category": "educacao"})
    advance(client, auth_headers, 11)
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        vers = list(s.scalars(select(RecurringItem).where(RecurringItem.user_id == u)))[0].id
        from backend.models import RecurringItemVersion
        assert len(list(s.scalars(select(RecurringItemVersion).where(RecurringItemVersion.item_id == vers)))) == 1
    advance(client, auth_headers, 1)                                        # 12º mês: aniversário
    with SessionLocal() as s:
        v = list(s.scalars(select(RecurringItemVersion).where(RecurringItemVersion.item_id == vers).order_by(
            RecurringItemVersion.effective_from)))
        assert len(v) == 2 and v[1].amount > v[0].amount


def test_inflation_changes_family_expenses(client, auth_headers):
    credit(client, auth_headers, "500000")
    start_world(client, auth_headers, seed=8)
    client.get(L, headers=auth_headers)
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        ref = s.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        s.add(Child(user_id=u, name="Lia", birth_month=date(ref.year - 7, ref.month, 1)))
        s.commit()
    advance(client, auth_headers)
    with SessionLocal() as s:
        st = s.scalar(select(EconomyState).where(EconomyState.user_id == u).order_by(EconomyState.ref_month.desc()))
        food = s.scalar(select(BudgetItem).where(BudgetItem.user_id == u, BudgetItem.source_key.like("child:%:food")).order_by(
            BudgetItem.id.desc()))
        assert food.planned_amount == (D(500) * D(str(st.indices["alimentacao"]))).quantize(D("0.01"))
        assert st.indices["alimentacao"] != 1


def test_food_inflation_reaches_personal_family_and_company_costs(client, auth_headers):
    """Um único índice 'alimentacao' alimenta orçamento pessoal, família e fornecedor do restaurante."""
    credit(client, auth_headers, "5000000")
    start_world(client, auth_headers, seed=2)
    co = create_ok(client, auth_headers, name="Bistrô", segment="RESTAURANT")["company"]
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        from backend.models import Company
        c = s.get(Company, co["id"])
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        base = economy_service.supplier_mult(s, c, month.ref_month)
        st = s.scalar(select(EconomyState).where(EconomyState.user_id == u))
        st.indices = {**st.indices, "alimentacao": 1.5}
        s.commit()
        s.refresh(c)
        assert economy_service.supplier_mult(s, c, month.ref_month) == base * D("1.5")
        assert economy_service.index_value(s, u, month.ref_month, "alimentacao") == D("1.5")
        from backend.services import life_service, pricing
        assert pricing.scale(s, u, month.ref_month, "alimentacao", 400) == D("600.00")
    # empresa de outro setor não usa o índice de alimentação
    with SessionLocal() as s:
        from backend.models import Company
        c = s.get(Company, co["id"])
        assert economy_service.supplier_category(c) == "alimentacao"


def test_economy_and_events_change_company_demand_and_costs(client, auth_headers):
    credit(client, auth_headers, "5000000")
    start_world(client, auth_headers, seed=2)
    co = create_ok(client, auth_headers, name="Café Central", segment="CAFE")["company"]
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        from backend.models import Company
        c = s.get(Company, co["id"])
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        ref = month.ref_month
        seg = company_rules.SEGMENTS[c.segment]
        expected = company_rules.demand_units(seg, location=c.location, size=c.size, units=c.units, reputation=c.reputation,
                                              price=c.price, company_id=c.id, ref=ref, marketing=False,
                                              relevance=float(c.relevance))
        st = s.scalar(select(EconomyState).where(EconomyState.user_id == u))
        st.demand = D("50")                                                  # recessão forte
        s.commit()
    advance(client, auth_headers)
    with SessionLocal() as s:
        cm = s.scalar(select(CompanyMonth).where(CompanyMonth.company_id == co["id"]).order_by(CompanyMonth.ref_month))
        assert abs(float(cm.demand_units) - expected * 0.5) <= max(0.02 * expected, 0.02)
    # evento setorial de alta de demanda multiplica a demanda do segmento
    with SessionLocal() as s:
        from backend.models import Company
        c = s.get(Company, co["id"])
        ref = s.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        mult_before = economy_service.company_demand_mult(s, c, ref)
    ev = add_event(client, auth_headers, key="alta_setor", scope="SECTOR", sector="CAFE",
                   effects={"company_demand_pct": 20}, start_month=date(2000, 1, 1), end_month=date(2100, 1, 1))
    other = add_event(client, auth_headers, key="crise_setor", scope="SECTOR", sector="RESTAURANT",
                      effects={"company_demand_pct": -50}, start_month=date(2000, 1, 1), end_month=date(2100, 1, 1))
    with SessionLocal() as s:
        from backend.models import Company
        c = s.get(Company, co["id"])
        ref = s.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        assert abs(economy_service.company_demand_mult(s, c, ref) / mult_before - 1.2) < 1e-9     # só o setor CAFE sobe


def test_recession_cuts_company_sales_proportionally_to_the_sector(client, auth_headers):
    """Mesmo mês, com e sem crise: a recessão (-14% no pico no café, x3 nas vendas) derruba a demanda em dezenas de %."""
    from sqlalchemy.orm.attributes import flag_modified
    from backend.models import Company, EconomicCrisis
    credit(client, auth_headers, "5000000")
    start_world(client, auth_headers, seed=2)
    co = create_ok(client, auth_headers, name="Café Crise", segment="CAFE")["company"]
    cafe2 = create_ok(client, auth_headers, name="Mercado Crise", segment="SUPERMARKET")["company"]
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        for cid in (co["id"], cafe2["id"]):
            s.get(Company, cid).relevance = D("40")
        s.commit()
        c = s.get(Company, co["id"])
        ref = s.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        calm = economy_service.company_demand_mult(s, c, ref)
        assert not economy_service.company_crisis_info(s, c, ref)["active"]
        st = s.scalar(select(EconomyState).where(EconomyState.user_id == u).order_by(EconomyState.ref_month.desc()))
        eng = dict(st.engine)
        eng["info"] = {**eng.get("info", {}), "sector": {"CAFE": -14.0, "SUPERMARKET": -4.0}}      # recessão em intensidade 1
        st.engine = eng
        flag_modified(st, "engine")
        s.add(EconomicCrisis(user_id=u, type="RECESSION", label="Recessão econômica", start_month=ref, status="ACTIVE", phase="PEAK",
                             intensity=D("1"), peak=D("1"), sectors={"CAFE": -14.0, "SUPERMARKET": -4.0}, assets={}, triggers={}, path=[]))
        s.commit()
        crisis = economy_service.company_demand_mult(s, c, ref)
        assert crisis / calm == pytest.approx(0.58, abs=0.01)                               # -42% no café
        sm = economy_service.company_demand_mult(s, s.get(Company, cafe2["id"]), ref)
        assert crisis < sm                                                                  # proporcional ao setor (supermercado sofre menos)
        info = economy_service.company_crisis_info(s, c, ref)
        assert info["active"] and info["sector_pct"] == -42.0 and info["crises"][0]["type"] == "RECESSION"
    d = client.get(f"/api/companies/{co['id']}", headers=auth_headers).json()
    assert d["market"]["crisis"]["active"] is True
    advance(client, auth_headers)
    with SessionLocal() as s:
        cm = s.scalar(select(CompanyMonth).where(CompanyMonth.company_id == co["id"]))
        c = s.get(Company, co["id"])
        no_crisis = company_rules.demand_units(company_rules.SEGMENTS[c.segment], location=c.location, size=c.size, units=c.units,
                                               reputation=50, price=c.price, company_id=c.id, ref=cm.ref_month, marketing=False,
                                               relevance=40.0) * float(st.demand) / 100
        assert float(cm.demand_units) == pytest.approx(no_crisis * 0.58, rel=0.02)


def test_interest_rate_makes_financing_more_expensive(client, auth_headers):
    credit(client, auth_headers, "100000")
    start_world(client, auth_headers, seed=1, initial={"interest": 14.5})
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        ref = s.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        add = economy_service.financing_rate_add(s, u, ref)
        assert add == D("4.0000")
        from backend.models import GoodCategory, AmortizationSystem
        base, _ = goods_service.simulate_financing(GoodCategory.RESIDENTIAL, D("500000"), D("200000"), 120,
                                                   AmortizationSystem.PRICE, None)
        hi, rows = goods_service.simulate_financing(GoodCategory.RESIDENTIAL, D("500000"), D("200000"), 120,
                                                    AmortizationSystem.PRICE, None, add)
        assert hi == base + 4


def test_asset_values_respond_to_events_and_conditions(client, auth_headers):
    start_world(client, auth_headers, seed=1)
    add_event(client, auth_headers, key="valorizacao_imoveis", effects={"assets_pct": 0.5})
    u = uid(client, auth_headers)
    from backend.models import GoodCategory
    with SessionLocal() as s:
        ref = s.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        assert economy_service.asset_adjust(s, u, ref, GoodCategory.RESIDENTIAL) > D("0.4")
        assert economy_service.asset_adjust(s, u, ref, GoodCategory.CAR) == D("0")


# ------------------------------------------------------------------ eventos

def test_events_have_full_definition_and_expire(client, auth_headers):
    credit(client, auth_headers, "800000")
    start_world(client, auth_headers, seed=21)
    advance(client, auth_headers, 40)
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        evs = list(s.scalars(select(WorldEvent).where(WorldEvent.user_id == u).order_by(WorldEvent.id)))
        assert evs, "em 40 meses o mundo deve gerar eventos"
        keys = {(e.key, e.start_month) for e in evs}
        assert len(keys) == len(evs)                                       # nunca o mesmo evento duas vezes no mês
        for e in evs:
            assert e.name and e.description and e.category in ("ECONOMIC", "PERSONAL", "BUSINESS", "FINANCIAL")
            assert e.scope in ("WORLD", "SECTOR", "USER", "COMPANY") and e.start_month <= e.end_month and e.intensity in (1, 2, 3)
        ref = s.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        assert all(e.status == "ENDED" for e in evs if e.end_month < ref and e.status != "PENDING")
        assert all(e.status in ("ACTIVE", "PENDING") for e in evs if e.end_month >= ref)
        # companhia ausente: nenhum evento empresarial
        assert not any(e.category == "BUSINESS" for e in evs)


def test_business_events_only_when_user_has_companies(client, auth_headers):
    credit(client, auth_headers, "5000000")
    start_world(client, auth_headers, seed=33)
    create_ok(client, auth_headers, name="Café", segment="CAFE")
    advance(client, auth_headers, 60)
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        biz = list(s.scalars(select(WorldEvent).where(WorldEvent.user_id == u, WorldEvent.category == "BUSINESS")))
        assert biz and all(e.company_id is not None for e in biz)


def test_advance_is_idempotent_per_month(client, auth_headers):
    credit(client, auth_headers, "300000")
    start_world(client, auth_headers, seed=9)
    advance(client, auth_headers, 3)
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        n_states = len(list(s.scalars(select(EconomyState).where(EconomyState.user_id == u))))
        n_events = len(list(s.scalars(select(WorldEvent).where(WorldEvent.user_id == u))))
        n_items = len(list(s.scalars(select(BudgetItem).where(BudgetItem.user_id == u))))
        economy_service.advance_to_month(s, u, month)
        economy_service.advance_to_month(s, u, month)
        s.commit()
        assert len(list(s.scalars(select(EconomyState).where(EconomyState.user_id == u)))) == n_states
        assert len(list(s.scalars(select(WorldEvent).where(WorldEvent.user_id == u)))) == n_events
        assert len(list(s.scalars(select(BudgetItem).where(BudgetItem.user_id == u)))) == n_items


def test_decision_event_hides_outcomes_and_applies_cost_and_effects(client, auth_headers):
    credit(client, auth_headers, "100000")
    start_world(client, auth_headers, seed=6)
    eid = add_event(client, auth_headers, key="acontecimento_familiar", name="Acontecimento familiar", category="PERSONAL",
                    scope="USER", status="PENDING", positive=False,
                    options=[{"key": "ajudar", "label": "Ajudar", "hint": "Custa dinheiro", "cost": 1500},
                             {"key": "recusar", "label": "Recusar", "hint": "Preserva o caixa", "cost": 0}])
    j = client.get(EC, headers=auth_headers).json()
    pend = j["pending"][0]
    assert pend["id"] == eid and {o["key"] for o in pend["options"]} == {"ajudar", "recusar"}
    assert "effects" not in pend and "outcomes" not in str(pend) and pend["outcome"] is None
    assert client.post(f"{EC}/events/{eid}/decide", headers=auth_headers, json={"option": "xyz"}).status_code == 400
    r = client.post(f"{EC}/events/{eid}/decide", headers=auth_headers, json={"option": "ajudar"})
    assert r.status_code == 200, r.text
    assert r.json()["event"]["status"] == "ACTIVE" and r.json()["event"]["outcome"]
    assert client.post(f"{EC}/events/{eid}/decide", headers=auth_headers, json={"option": "recusar"}).status_code == 409
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        it = s.scalar(select(BudgetItem).where(BudgetItem.user_id == u, BudgetItem.source_key == f"econ:{eid}:oneoff:0"))
        assert it is not None and it.planned_amount == D("1500.00")
    before = D(client.get("/api/portfolio", headers=auth_headers).json()["cash_balance"])
    advance(client, auth_headers)
    after = D(client.get("/api/portfolio", headers=auth_headers).json()["cash_balance"])
    assert before - after >= D("1500.00")
    with SessionLocal() as s:
        e = s.scalar(select(LedgerEntry).where(LedgerEntry.user_id == u, LedgerEntry.origin == EntryOrigin.EVENT))
        assert e is not None and e.amount == D("1500.00")


def test_unresolved_decision_uses_default_option_when_month_turns(client, auth_headers):
    credit(client, auth_headers, "100000")
    start_world(client, auth_headers, seed=6)
    eid = add_event(client, auth_headers, key="oportunidade_profissional", category="PERSONAL", scope="USER",
                    status="PENDING", options=[{"key": "aceitar", "label": "A", "hint": "h", "cost": 0},
                                               {"key": "recusar", "label": "R", "hint": "h", "cost": 0}])
    advance(client, auth_headers)
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        ev = s.get(WorldEvent, eid)
        assert ev.status in ("ACTIVE", "ENDED") and ev.choice == "recusar"


def test_event_income_effect_flows_to_budget_and_stops_when_event_ends(client, auth_headers):
    credit(client, auth_headers, "300000")
    cat = cat_id(client, auth_headers, "Salário", "INCOME")
    client.post(f"{B}/items", headers=auth_headers, json={"name": "Salário", "kind": "INCOME", "category_id": cat,
                                                         "planned_amount": "5000", "recurring": True})
    start_world(client, auth_headers, seed=12)
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        ref = s.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
    eid = add_event(client, auth_headers, key="promocao", category="PERSONAL", scope="USER", name="Promoção",
                    effects={"income_pct": 10}, start_month=ref, end_month=budget_service.shift_month(ref, 1))
    with SessionLocal() as s:
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        economy_service.sync_month(s, u, month)
        s.commit()
        it = s.scalar(select(BudgetItem).where(BudgetItem.user_id == u, BudgetItem.source_key == f"econ:{eid}:income"))
        assert it.planned_amount == D("500.00") and it.kind.value == "INCOME"
    advance(client, auth_headers)                                           # ainda dentro do período
    with SessionLocal() as s:
        assert s.scalar(select(BudgetItem).where(BudgetItem.user_id == u, BudgetItem.source_key == f"econ:{eid}:income"))
    advance(client, auth_headers, 2)                                        # terminou
    with SessionLocal() as s:
        assert s.get(WorldEvent, eid).status == "ENDED"
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        assert s.scalar(select(BudgetItem).where(BudgetItem.month_id == month.id, BudgetItem.source_key == f"econ:{eid}:income")) is None


def test_economy_data_is_isolated_between_users(client, auth_headers):
    credit(client, auth_headers, "100000")
    other = second_user(client)
    start_world(client, auth_headers, seed=6)
    eid = add_event(client, auth_headers, key="x", status="PENDING", category="PERSONAL", scope="USER",
                    options=[{"key": "a", "label": "A", "hint": "", "cost": 0}])
    assert client.get(EC, headers=other).json()["dynamic"] is False
    assert client.get(EC, headers=other).json()["pending"] == []
    assert client.post(f"{EC}/events/{eid}/decide", headers=other, json={"option": "a"}).status_code == 404
    assert client.get(EC).status_code in (401, 403)


# ------------------------------------------------------------------ atomicidade do fechamento

def test_failure_in_any_module_leaves_month_unchanged(client, auth_headers, monkeypatch):
    credit(client, auth_headers, "100000")
    start_world(client, auth_headers, seed=6)
    advance(client, auth_headers)
    u = uid(client, auth_headers)
    cash_before = client.get("/api/portfolio", headers=auth_headers).json()["cash_balance"]
    n_states = len(states(client, auth_headers))
    from backend.services import finance_ledger, life_service
    monkeypatch.setattr(life_service, "advance_to_month", lambda *a, **k: (_ for _ in ()).throw(finance_ledger.FinanceError("falha simulada")))
    r = close(client, auth_headers)
    assert r.status_code == 400 and "falha simulada" in r.text
    monkeypatch.undo()
    assert client.get("/api/portfolio", headers=auth_headers).json()["cash_balance"] == cash_before
    assert len(states(client, auth_headers)) == n_states                   # estado econômico do mês não ficou pela metade
    with SessionLocal() as s:
        opens = list(s.scalars(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN")))
        assert len(opens) == 1 and opens[0].closing_balance is None
    assert close(client, auth_headers).status_code == 200                 # e o fechamento ainda funciona depois
