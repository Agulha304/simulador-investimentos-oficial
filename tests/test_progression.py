"""Progressão e integração (etapa 6): modos livre/carreira, cenários, objetivos, conquistas, relatórios e integração geral."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import (
    Achievement, BudgetItem, Child, Company, CompanyMonth, CompanyStatus, EconomyState, EntryOrigin, Goal, LedgerEntry,
    LifeProfile, MonthReport, Person, RecurringItem, Relationship, SimMonth, Transaction,
)
from backend.services import company_service, economy_service
from backend.services import progression_rules as P
from tests.conftest import credit
from tests.test_budget import B, close, second_user
from tests.test_companies import create_ok

D = Decimal
G = "/api/game"
PG = "/api/progress"


def uid(client, h):
    return client.get("/api/auth/me", headers=h).json()["id"]


def cash(client, h):
    return D(client.get("/api/portfolio", headers=h).json()["cash_balance"])


def start(client, h, **body):
    return client.post(f"{G}/start", headers=h, json=body)


def free(client, h, seed=5, **cfg):
    r = start(client, h, mode="FREE", seed=seed, free=cfg)
    assert r.status_code == 200, r.text
    return r.json()


def career(client, h, key, seed=5):
    r = start(client, h, mode="CAREER", scenario=key, seed=seed)
    assert r.status_code == 200, r.text
    return r.json()


def advance(client, h, n=1):
    for _ in range(n):
        r = close(client, h)
        assert r.status_code == 200, r.text


def goals(client, h):
    return {g["key"]: g for g in client.get(f"{PG}/goals", headers=h).json()}


# ------------------------------------------------------------------ modo livre

def test_free_mode_applies_initial_configuration_and_is_open_ended(client, auth_headers):
    free(client, auth_headers, cash=35000, monthly_income=5000, monthly_expenses=2000, rent=1200)
    assert cash(client, auth_headers) == D("35000.00")
    j = client.get(f"{PG}/overview", headers=auth_headers).json()
    assert j["mode"] == "FREE" and j["scenario"] is None and j["dynamic_economy"] is True
    assert D(j["monthly_income"]) == D("5000.00") and D(j["monthly_expense"]) == D("3200.00")
    assert j["goals"] == []                                    # sem objetivos impostos
    info = client.get(G, headers=auth_headers).json()
    assert info["started"] and len(info["scenarios"]) == 5 and info["mode"] == "FREE"


def test_free_mode_allows_every_system_from_the_start(client, auth_headers):
    free(client, auth_headers, cash=300000, monthly_income=4000, monthly_expenses=1500)
    c = create_ok(client, auth_headers, name="Café Livre", segment="CAFE")["company"]       # empresa
    assert c["id"]
    assert client.put("/api/life/choices", headers=auth_headers, json={"leisure_level": "HIGH"}).status_code == 200   # vida pessoal
    assert client.get("/api/economy", headers=auth_headers).json()["dynamic"]                                         # economia
    assert client.post(f"{PG}/goals", headers=auth_headers, json={"template": "net_worth", "target": "500000"}).status_code == 201


@pytest.mark.parametrize("cfg", [
    dict(cash=0, monthly_income=1000, monthly_expenses=3000),                            # não se sustenta
    dict(cash=1000, monthly_income=2000, monthly_expenses=500, rent=1800),               # aluguel > 70% da renda sem caixa
    dict(cash=-5, monthly_income=1000),
])
def test_free_mode_rejects_combinations_that_break_the_simulation(client, auth_headers, cfg):
    r = start(client, auth_headers, mode="FREE", free=cfg)
    assert r.status_code in (400, 422), r.text
    assert client.get(G, headers=auth_headers).json()["started"] is False             # nada ficou pela metade


def test_game_start_only_on_fresh_account_and_only_once(client, auth_headers):
    free(client, auth_headers)
    assert start(client, auth_headers, mode="FREE").status_code == 409
    other = second_user(client)
    credit(client, other, "1000")
    advance(client, other)
    assert start(client, other, mode="FREE").status_code == 409                        # já tem histórico: não apaga nada
    assert start(client, second_user_b(client), mode="X").status_code == 400


def second_user_b(client):
    r = client.post("/api/auth/register", json={"email": "caio@example.com", "name": "Caio", "password": "segredo123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_same_seed_makes_a_reproducible_scenario(client, auth_headers):
    other = second_user(client)
    career(client, auth_headers, "young_pro", seed=77)
    career(client, other, "young_pro", seed=77)
    for h in (auth_headers, other):
        credit(client, h, "50000")
        advance(client, h, 8)
    def snap(h):
        u = uid(client, h)
        with SessionLocal() as s:
            return [(e.ref_month, e.inflation, e.interest, e.indices) for e in s.scalars(
                select(EconomyState).where(EconomyState.user_id == u).order_by(EconomyState.ref_month))]
    assert snap(auth_headers) == snap(other)


# ------------------------------------------------------------------ modo carreira e cenários

@pytest.mark.parametrize("key", list(P.SCENARIOS))
def test_each_career_scenario_starts_with_defined_conditions(client, auth_headers, key):
    sc = P.SCENARIOS[key]
    career(client, auth_headers, key)
    assert cash(client, auth_headers) == D(sc.cash).quantize(D("0.01"))
    j = client.get(f"{PG}/overview", headers=auth_headers).json()
    assert j["mode"] == "CAREER" and j["scenario"] == key
    assert D(j["monthly_income"]) >= D(sc.salary)
    assert D(j["monthly_expense"]) >= sum(D(e.amount) for e in sc.expenses)
    g = goals(client, auth_headers)
    assert set(g) == {x.key for x in sc.goals} and all(x["origin"] == "SCENARIO" for x in g.values())
    assert client.get(G, headers=auth_headers).json()["scenarios"]
    advance(client, auth_headers)                                                       # a simulação roda
    assert client.get(f"{PG}/reports/latest", headers=auth_headers).status_code == 200


def test_family_scenario_has_partner_children_and_shared_costs(client, auth_headers):
    career(client, auth_headers, "family")
    life = client.get("/api/life", headers=auth_headers).json()
    spouse = next(r for r in life["relationships"] if r["stage"] == "MARRIED")
    assert spouse["name"].startswith("Marina") and len(life["children"]) == 1
    assert {"MOTHER", "FATHER"} <= {r["role"] for r in life["relationships"]}              # a família de origem também começa com você
    assert life["children"][0]["age_years"] == 3 and life["housing"]["kind"] == "SHARED"
    keys = {e["key"] for e in life["expenses"]}
    assert "family:housing" in keys and "family:partner:contribution" in keys and any(k.startswith("child:") for k in keys)


def test_career_scenario_keeps_freedom_of_choice(client, auth_headers):
    career(client, auth_headers, "entrepreneur")
    # nada obriga a abrir a empresa: o usuário pode fechar meses investindo ou seguindo outro caminho
    advance(client, auth_headers, 2)
    assert goals(client, auth_headers)["first_company"]["status"] == "ACTIVE"
    assert start(client, auth_headers, mode="CAREER", scenario="investor").status_code == 409
    assert start(client, second_user(client), mode="CAREER", scenario="nao_existe").status_code == 400


# ------------------------------------------------------------------ objetivos

def test_goal_requires_sustained_achievement_not_a_single_action(client, auth_headers):
    free(client, auth_headers, cash=50000, monthly_income=6000, monthly_expenses=2000)
    r = client.post(f"{PG}/goals", headers=auth_headers, json={"template": "net_worth", "target": "1000", "sustain_months": 3})
    assert r.status_code == 201
    key = r.json()["key"]
    assert client.post(f"{PG}/goals", headers=auth_headers, json={"template": "net_worth", "target": "1000"}).status_code == 409
    advance(client, auth_headers)
    g = goals(client, auth_headers)[key]
    assert g["status"] == "ACTIVE" and g["streak"] == 1 and g["progress"] == pytest.approx(0.333, abs=0.01)
    advance(client, auth_headers, 2)
    g = goals(client, auth_headers)[key]
    assert g["status"] == "DONE" and g["done_month"]
    names = {a["key"]: a for a in client.get(f"{PG}/achievements", headers=auth_headers).json()}
    assert names["first_goal"]["unlocked"]


def test_goal_streak_resets_when_condition_breaks(client, auth_headers):
    free(client, auth_headers, cash=20000, monthly_income=3000, monthly_expenses=1000)
    key = client.post(f"{PG}/goals", headers=auth_headers, json={"template": "invested", "target": "5000", "sustain_months": 2}).json()["key"]
    advance(client, auth_headers, 2)                           # nada investido: nunca avança
    g = goals(client, auth_headers)[key]
    assert g["streak"] == 0 and g["status"] == "ACTIVE" and D(g["current"]) == 0


def test_debt_free_goal_refused_when_there_is_no_debt(client, auth_headers):
    free(client, auth_headers)
    assert client.post(f"{PG}/goals", headers=auth_headers, json={"template": "debt_free"}).status_code == 400
    assert client.post(f"{PG}/goals", headers=auth_headers, json={"template": "inexistente"}).status_code == 400


def test_goal_evaluation_is_idempotent_per_month(client, auth_headers):
    free(client, auth_headers, cash=50000, monthly_income=6000, monthly_expenses=2000)
    client.post(f"{PG}/goals", headers=auth_headers, json={"template": "net_worth", "target": "1000", "sustain_months": 5})
    advance(client, auth_headers)
    u = uid(client, auth_headers)
    from backend.services import progression_service as ps
    with SessionLocal() as s:
        ref = s.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == u, SimMonth.status == "CLOSED"))
        m = ps.metrics(s, u, ref)
        ps.evaluate_goals(s, u, ref, m)
        ps.evaluate_goals(s, u, ref, m)
        s.commit()
        assert s.scalar(select(Goal.streak).where(Goal.user_id == u, Goal.origin == "USER")) == 1


# ------------------------------------------------------------------ conquistas

def test_achievements_are_recorded_once_and_survive_closing_a_company(client, auth_headers, assets):
    credit(client, auth_headers, "500000")
    free(client, auth_headers, cash=400000, monthly_income=8000, monthly_expenses=2000)
    r = client.post("/api/trades/buy", headers=auth_headers, json={"asset_id": assets["PETR4"].id, "quantity": "10"})
    assert r.status_code == 201, r.text
    create_ok(client, auth_headers, name="Café Conquista", segment="CAFE")
    advance(client, auth_headers)
    got = {a["key"]: a for a in client.get(f"{PG}/achievements", headers=auth_headers).json()}
    for k in ("first_investment", "first_company", "first_employee", "first_positive_month"):
        assert got[k]["unlocked"], k
    assert not got["first_million"]["unlocked"] and not got["first_child"]["unlocked"]
    before = {k: v["unlocked_month"] for k, v in got.items() if v["unlocked"]}
    u = uid(client, auth_headers)
    with SessionLocal() as s:                                   # a empresa deixa de existir como ativa
        for c in s.scalars(select(Company).where(Company.user_id == u)):
            c.status = CompanyStatus.CLOSED
        s.commit()
    advance(client, auth_headers, 2)
    again = {a["key"]: a for a in client.get(f"{PG}/achievements", headers=auth_headers).json()}
    assert {k: v["unlocked_month"] for k, v in again.items() if v["unlocked"]}.items() >= before.items()   # nada se perde, datas intactas
    with SessionLocal() as s:
        rows = list(s.scalars(select(Achievement.key).where(Achievement.user_id == u)))
        assert len(rows) == len(set(rows))                      # única por chave


def test_family_achievements_come_from_personal_history(client, auth_headers):
    career(client, auth_headers, "family")
    advance(client, auth_headers)
    got = {a["key"]: a["unlocked"] for a in client.get(f"{PG}/achievements", headers=auth_headers).json()}
    assert got["married"] and got["first_partner"] and got["first_child"]


def test_million_is_recorded_once_reached(client, auth_headers):
    free(client, auth_headers, cash=900000, monthly_income=10000, monthly_expenses=3000)
    advance(client, auth_headers)
    assert not {a["key"]: a["unlocked"] for a in client.get(f"{PG}/achievements", headers=auth_headers).json()}["first_million"]
    credit(client, auth_headers, "200000")
    advance(client, auth_headers)
    assert {a["key"]: a["unlocked"] for a in client.get(f"{PG}/achievements", headers=auth_headers).json()}["first_million"]


# ------------------------------------------------------------------ relatórios

def test_monthly_report_uses_real_data(client, auth_headers):
    career(client, auth_headers, "young_pro")
    assert client.get(f"{PG}/reports/latest", headers=auth_headers).status_code == 404
    advance(client, auth_headers)
    rep = client.get(f"{PG}/reports/latest", headers=auth_headers).json()
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        m = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "CLOSED"))
        assert rep["month"] == m.ref_month.isoformat()
        assert D(str(rep["income"])) == m.total_income and D(str(rep["expense"])) == m.total_expense
        assert rep["result"] == pytest.approx(float(m.total_income - m.total_expense))
        assert D(str(rep["closing_balance"])) == m.closing_balance
    for k in ("net_worth", "debts", "companies", "family_changes", "events", "economy", "achievements", "expense_by_category", "metrics"):
        assert k in rep
    assert rep["economy"]["inflation"] > 0 and rep["expense_by_category"]["Moradia"] == 1800.0
    lst = client.get(f"{PG}/reports", headers=auth_headers).json()
    assert len(lst) == 1 and lst[0]["month"] == rep["month"]
    assert client.get(f"{PG}/reports/{rep['month'][:7]}", headers=auth_headers).json() == rep
    assert client.get(f"{PG}/reports/1999-01", headers=auth_headers).status_code == 404
    assert client.get(f"{PG}/reports/lixo", headers=auth_headers).status_code == 404


def test_monthly_report_lists_company_results_and_family_changes(client, auth_headers):
    credit(client, auth_headers, "600000")
    free(client, auth_headers, cash=500000, monthly_income=5000, monthly_expenses=2000)
    create_ok(client, auth_headers, name="Bistrô do Mês", segment="RESTAURANT")
    advance(client, auth_headers)
    rep = client.get(f"{PG}/reports/latest", headers=auth_headers).json()
    assert [c["name"] for c in rep["companies"]] == ["Bistrô do Mês"]
    with SessionLocal() as s:
        cm = s.scalar(select(CompanyMonth))
        assert rep["companies"][0]["net_result"] == pytest.approx(float(cm.net_result)) and rep["company_profit"] == pytest.approx(float(cm.net_result))


def test_annual_report_aggregates_twelve_months_of_real_history(client, auth_headers):
    credit(client, auth_headers, "400000")
    career(client, auth_headers, "young_pro")
    advance(client, auth_headers, 13)
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        closed = list(s.scalars(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "CLOSED").order_by(SimMonth.ref_month)))
    year = closed[0].ref_month.year
    assert client.get(f"{PG}/reports/annual/1990", headers=auth_headers).status_code == 404
    total_months = 0
    for y in sorted({m.ref_month.year for m in closed}):
        a = client.get(f"{PG}/reports/annual/{y}", headers=auth_headers).json()
        rows = [m for m in closed if m.ref_month.year == y]
        total_months += a["months"]
        assert a["months"] == len(rows)
        assert a["income"] == pytest.approx(float(sum(m.total_income for m in rows)))
        assert a["expense"] == pytest.approx(float(sum(m.total_expense for m in rows)))
        assert a["invested"] == pytest.approx(float(sum(m.invested for m in rows)))
        assert len(a["monthly"]) == len(rows) and a["net_worth_end"] == a["monthly"][-1]["net_worth"]
        assert a["net_worth_change"] == pytest.approx(a["net_worth_end"] - a["net_worth_start"])
    assert total_months == 13
    first = client.get(f"{PG}/reports/annual/{year}", headers=auth_headers).json()
    cfg = client.get(G, headers=auth_headers).json()["config"]
    assert first["net_worth_start"] == pytest.approx(cfg["initial_net_worth"])           # baseline real da partida
    full = [y for y in {m.ref_month.year for m in closed} if len([m for m in closed if m.ref_month.year == y]) == 12]
    for y in full:
        assert client.get(f"{PG}/reports/annual/{y}", headers=auth_headers).json()["complete"]


# ------------------------------------------------------------------ painel geral

def test_dashboard_matches_portfolio_and_modules(client, auth_headers):
    credit(client, auth_headers, "400000")
    free(client, auth_headers, cash=300000, monthly_income=5000, monthly_expenses=2000)
    create_ok(client, auth_headers, name="Painel Café", segment="CAFE")
    advance(client, auth_headers, 2)
    j = client.get(f"{PG}/overview", headers=auth_headers).json()
    pf = client.get("/api/portfolio", headers=auth_headers).json()
    assert D(j["cash"]) == D(pf["cash_balance"]) and D(j["net_worth"]) == D(pf["total_equity_brl"])
    assert len(j["companies"]) == 1 and j["economy"]["inflation"] and j["month"]
    for k in ("monthly_income", "monthly_expense", "debts", "invested", "passive_income", "family", "wellbeing", "goals",
              "pending_events", "achievements_unlocked"):
        assert k in j
    # patrimônio consolidado = caixa + investimentos + bens líquidos + participação nas empresas
    parts = D(pf["cash_balance"]) + D(pf["market_value_brl"]) + D(pf["fixed_income_value_brl"]) + D(pf["goods_net_brl"]) + D(pf["companies_net_brl"])
    assert parts == D(pf["total_equity_brl"])


# ------------------------------------------------------------------ integração entre módulos

def test_closing_month_processes_every_module_in_one_cycle(client, auth_headers):
    credit(client, auth_headers, "600000")
    free(client, auth_headers, cash=500000, monthly_income=5000, monthly_expenses=2000)
    create_ok(client, auth_headers, name="Café Integrado", segment="CAFE")
    client.get("/api/life", headers=auth_headers)
    client.post(f"{PG}/goals", headers=auth_headers, json={"template": "net_worth", "target": "1000"})
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        ref = s.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
    advance(client, auth_headers)
    with SessionLocal() as s:
        assert s.scalar(select(CompanyMonth.id).where(CompanyMonth.ref_month == ref)) is not None            # empresas
        assert s.scalar(select(LifeProfile.last_processed_month).where(LifeProfile.user_id == u)) == ref      # família
        nxt = s.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        assert s.scalar(select(EconomyState.id).where(EconomyState.user_id == u, EconomyState.ref_month == nxt))   # economia
        assert s.scalar(select(MonthReport.id).where(MonthReport.user_id == u, MonthReport.ref_month == ref))     # relatório
        assert s.scalar(select(Goal.last_eval_month).where(Goal.user_id == u, Goal.origin == "USER")) == ref      # objetivos
        assert s.scalar(select(Achievement.id).where(Achievement.user_id == u))                                   # conquistas
        assert s.scalar(select(BudgetItem.id).where(BudgetItem.user_id == u, BudgetItem.month_id == s.scalar(
            select(SimMonth.id).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))))                        # orçamento do novo mês


def test_company_and_family_expenses_are_kept_separate(client, auth_headers):
    credit(client, auth_headers, "800000")
    career(client, auth_headers, "family")
    credit(client, auth_headers, "800000")
    create_ok(client, auth_headers, name="Café da Família", segment="CAFE")
    advance(client, auth_headers)
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        fam = list(s.scalars(select(LedgerEntry).where(LedgerEntry.user_id == u, LedgerEntry.origin == EntryOrigin.FAMILY)))
        biz = list(s.scalars(select(LedgerEntry).where(LedgerEntry.user_id == u, LedgerEntry.company_id.is_not(None))))
        assert fam and biz and not ({e.id for e in fam} & {e.id for e in biz})
        assert all(e.company_id is None for e in fam)
    rep = client.get(f"{PG}/reports/latest", headers=auth_headers).json()
    fam_exp = sum(e.amount for e in fam if e.kind.value == "EXPENSE")
    assert rep["family_expense"] == pytest.approx(float(fam_exp)) and rep["company_profit"] != rep["family_expense"]
    # orçamento familiar não conta duas vezes: cada item do mês tem chave única
    with SessionLocal() as s:
        keys = [bi.source_key for bi in s.scalars(select(BudgetItem).where(BudgetItem.user_id == u, BudgetItem.source_key.is_not(None)))]
        months = [(bi.month_id, bi.source_key) for bi in s.scalars(select(BudgetItem).where(BudgetItem.user_id == u, BudgetItem.source_key.is_not(None)))]
        assert len(months) == len(set(months))


def test_inflation_chain_raises_family_budget_and_restaurant_costs(client, auth_headers):
    """Inflação dos alimentos → orçamento familiar e custo de estoque do restaurante (mesmo índice)."""
    credit(client, auth_headers, "5000000")
    career(client, auth_headers, "family")
    credit(client, auth_headers, "5000000")
    co = create_ok(client, auth_headers, name="Restaurante da Cadeia", segment="RESTAURANT")["company"]
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        c = s.get(Company, co["id"])
        from backend.models import InventoryItem
        item = s.scalar(select(InventoryItem).where(InventoryItem.company_id == c.id).order_by(InventoryItem.id))
        company_service.buy_stock(s, u, month, c.id, item.id, D("100"), "chain-1")
        first = s.scalar(select(LedgerEntry.amount).where(LedgerEntry.user_id == u, LedgerEntry.idempotency_key.like("%chain-1%")))
        st = s.scalar(select(EconomyState).where(EconomyState.user_id == u).order_by(EconomyState.ref_month.desc()))
        st.indices = {**st.indices, "alimentacao": st.indices["alimentacao"] * 1.5}
        s.commit()
    with SessionLocal() as s:
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN"))
        c = s.get(Company, co["id"])
        item = s.scalar(select(InventoryItem).where(InventoryItem.company_id == c.id).order_by(InventoryItem.id))
        company_service.buy_stock(s, u, month, c.id, item.id, D("100"), "chain-2")
        second = s.scalar(select(LedgerEntry.amount).where(LedgerEntry.user_id == u, LedgerEntry.idempotency_key.like("%chain-2%")))
        s.commit()
    assert first is not None and second is not None and float(second) == pytest.approx(float(first) * 1.5, rel=0.01)
    # a família usa o mesmo índice na abertura do mês seguinte
    advance(client, auth_headers)
    with SessionLocal() as s:
        st = s.scalar(select(EconomyState).where(EconomyState.user_id == u).order_by(EconomyState.ref_month.desc()))
        food = s.scalar(select(BudgetItem).where(BudgetItem.user_id == u, BudgetItem.source_key.like("child:%:food")).order_by(BudgetItem.id.desc()))
        expected = (D(400) * D(str(st.indices["alimentacao"]))).quantize(D("0.01"))     # faixa 3-5 anos
        assert food.planned_amount == expected


def test_failure_in_progression_rolls_back_the_whole_close(client, auth_headers, monkeypatch):
    credit(client, auth_headers, "600000")
    free(client, auth_headers, cash=500000, monthly_income=5000, monthly_expenses=2000)
    create_ok(client, auth_headers, name="Café Atômico", segment="CAFE")
    client.get("/api/life", headers=auth_headers)
    u = uid(client, auth_headers)
    before = cash(client, auth_headers)
    from backend.services import finance_ledger, progression_service
    def boom(*a, **k):
        raise finance_ledger.FinanceError("falha no fim do fechamento")
    monkeypatch.setattr(progression_service, "on_month_closed", boom)
    r = close(client, auth_headers)
    assert r.status_code == 400
    monkeypatch.undo()
    assert cash(client, auth_headers) == before
    with SessionLocal() as s:
        assert s.scalar(select(CompanyMonth.id)) is None                                  # empresa não avançou
        assert s.scalar(select(MonthReport.id).where(MonthReport.user_id == u)) is None
        assert len(list(s.scalars(select(EconomyState).where(EconomyState.user_id == u)))) == 1
        assert len(list(s.scalars(select(SimMonth).where(SimMonth.user_id == u, SimMonth.status == "OPEN")))) == 1
        assert s.scalar(select(LifeProfile.last_processed_month).where(LifeProfile.user_id == u)) is None
    advance(client, auth_headers)                                                          # e depois o fechamento funciona
    assert client.get(f"{PG}/reports/latest", headers=auth_headers).status_code == 200


def test_closing_twice_does_not_duplicate_anything(client, auth_headers):
    free(client, auth_headers, cash=50000, monthly_income=5000, monthly_expenses=2000)
    advance(client, auth_headers)
    u = uid(client, auth_headers)
    with SessionLocal() as s:
        closed = s.scalar(select(SimMonth.ref_month).where(SimMonth.user_id == u, SimMonth.status == "CLOSED"))
    r = client.post(f"{B}/close", headers=auth_headers, json={"ref_month": closed.strftime("%Y-%m"), "confirm": True})
    assert r.status_code == 409
    with SessionLocal() as s:
        assert len(list(s.scalars(select(MonthReport).where(MonthReport.user_id == u)))) == 1
        assert len(list(s.scalars(select(EconomyState).where(EconomyState.user_id == u)))) == 2


def test_progress_data_is_isolated_between_users(client, auth_headers):
    free(client, auth_headers, cash=50000, monthly_income=5000, monthly_expenses=2000)
    client.post(f"{PG}/goals", headers=auth_headers, json={"template": "net_worth", "target": "999"})
    advance(client, auth_headers)
    other = second_user(client)
    assert client.get(f"{PG}/goals", headers=other).json() == []
    assert client.get(f"{PG}/reports", headers=other).json() == []
    assert client.get(f"{PG}/reports/latest", headers=other).status_code == 404
    assert client.get(f"{PG}/reports/annual/{date.today().year}", headers=other).status_code == 404
    ach = client.get(f"{PG}/achievements", headers=other).json()
    assert not any(a["unlocked"] for a in ach)
    assert client.get(f"{PG}/overview").status_code in (401, 403)
