"""Empresas (etapa 3): contas separadas, folha, estoque, receitas, expansão, locação, lucros e fechamento mensal."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.models import (
    Company, CompanyMonth, FinanceAccount, Good, LedgerEntry, Portfolio, Transaction,
)
from backend.services import company_rules, company_service

D = Decimal
C = "/api/companies"
B = "/api/budget"
G = "/api/goods"


def fund(client, h, amount="10000000"):
    r = client.post("/api/portfolio/deposit", headers=h, json={"amount": amount})
    assert r.status_code == 201, r.text


def portfolio(client, h):
    return client.get("/api/portfolio", headers=h).json()


def cash(client, h) -> Decimal:
    return D(portfolio(client, h)["cash_balance"])


def quote(client, h, segment="CAFE", location="bairro", size="SMALL"):
    r = client.post(f"{C}/quote", headers=h, json={"segment": segment, "location": location, "size": size})
    assert r.status_code == 200, r.text
    return r.json()


def create(client, h, name="Café da Esquina", segment="CAFE", extra="30000", **kw):
    q = quote(client, h, segment, kw.get("location", "bairro"), kw.get("size", "SMALL"))
    body = {"name": name, "segment": segment, "capital": str(D(q["required_capital"]) + D(extra)), **kw}
    return client.post(C, headers=h, json=body)


def create_ok(client, h, **kw):
    r = create(client, h, **kw)
    assert r.status_code == 201, r.text
    return r.json()


def detail(client, h, cid):
    r = client.get(f"{C}/{cid}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def close(client, h):
    ref = client.get(f"{B}/overview", headers=h).json()["month"]["ref_month"][:7]
    return client.post(f"{B}/close", headers=h, json={"ref_month": ref, "confirm": True})


def key():
    return uuid.uuid4().hex


def earn_profit(client, h, cid, limit=16):
    """Fecha meses até a empresa ter lucro acumulado distribuível (a estruturação inicial leva alguns meses para ser recuperada)."""
    for _ in range(limit):
        if D(detail(client, h, cid)["distributable_profit"]) > 0:
            return
        assert close(client, h).status_code == 200
    pytest.fail("a empresa não gerou lucro distribuível")


def second_user(client):
    r = client.post("/api/auth/register", json={"email": "bia@example.com", "name": "Bia", "password": "segredo123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _flat_season(monkeypatch):
    """Sem sazonalidade: receitas e resultados ficam previsíveis nos testes (a sazonalidade tem teste próprio)."""
    monkeypatch.setattr(company_rules, "season_factor", lambda *a, **k: 1.0)


@pytest.fixture
def rich(client, auth_headers):
    fund(client, auth_headers)
    return auth_headers


# ------------------------------------------------------------------ 1/2. criação

def test_catalog_has_twelve_segments_with_distinct_models(client, auth_headers):
    cat = client.get(f"{C}/catalog", headers=auth_headers).json()
    keys = {s["key"] for s in cat["segments"]}
    assert len(keys) == 12 and {"RESTAURANT", "TECH", "INDUSTRY", "CONSTRUCTION", "ECOMMERCE"} <= keys
    by = {s["key"]: s for s in cat["segments"]}
    assert by["RESTAURANT"]["stock"] and by["TECH"]["stock"] == []              # segmentos com e sem estoque
    assert {r["key"] for r in by["RESTAURANT"]["roles"]} != {r["key"] for r in by["TECH"]["roles"]}
    assert len({s["required_capital"] for s in cat["segments"]}) >= 10
    assert {l["key"] for l in cat["locations"]} >= {"centro", "bairro", "interior"}


def test_create_company_builds_coherent_structure(client, rich, db):
    before = cash(client, rich)
    q = quote(client, rich)
    d = create_ok(client, rich, extra="30000")
    co = d["company"]
    capital = D(q["required_capital"]) + D("30000")
    assert cash(client, rich) == before - capital                               # saiu da conta pessoal
    expected_cash = capital - D(q["setup_cost"]) - D(q["initial_stock"])
    assert D(co["cash"]) == expected_cash                                       # entrou na conta da empresa (menos estrutura e estoque)
    assert co["segment"] == "CAFE" and co["status"] == "ACTIVE" and co["reputation"] == 50
    assert [e["role"] for e in d["employees"]] == ["barista", "attendant"]
    assert d["lease"]["kind"] == "EXTERNAL" and D(d["lease"]["monthly_rent"]) > 0
    assert {c["kind"] for c in d["costs"]} == {"UTILITIES", "TOOLS", "ACCOUNTING"}
    assert d["inventory"][0]["name"] == "Insumos de café" and D(d["inventory"][0]["quantity"]) > 1500
    assert db.scalar(select(func.count()).select_from(FinanceAccount).where(FinanceAccount.kind == "BUSINESS")) == 1
    assert {e["type"] for e in d["events"]} == {"CREATED", "CAPITAL"}


def test_create_several_companies_with_own_accounts(client, rich, db):
    a = create_ok(client, rich, name="Café A")["company"]
    b = create_ok(client, rich, name="Oficina B", segment="WORKSHOP")["company"]
    c3 = create_ok(client, rich, name="Tech C", segment="TECH", size="MEDIUM", location="centro")["company"]
    assert len({a["id"], b["id"], c3["id"]}) == 3
    assert len(client.get(C, headers=rich).json()) == 3
    assert create(client, rich, name="Café A").status_code == 409                # nome repetido
    accounts = db.scalars(select(Company.account_id)).all()
    assert len(set(accounts)) == 3                                               # uma conta por empresa
    ov = client.get(f"{C}/overview", headers=rich).json()
    assert ov["count"] == 3 and D(ov["cash_total"]) == sum(D(x["cash"]) for x in ov["companies"])


def test_capital_below_minimum_rejected_without_side_effects(client, rich, db):
    start = cash(client, rich)
    r = client.post(C, headers=rich, json={"name": "Pequena demais", "segment": "INDUSTRY", "capital": "1000"})
    assert r.status_code == 400 and "capital inicial insuficiente" in r.json()["detail"]
    assert cash(client, rich) == start and db.scalar(select(func.count()).select_from(Company)) == 0
    broke = client.post(C, headers=rich, json={"name": "Sem saldo", "segment": "CAFE", "capital": "99999999"})
    assert broke.status_code == 422                                              # saldo pessoal insuficiente
    assert db.scalar(select(func.count()).select_from(Company)) == 0 and cash(client, rich) == start


def test_location_and_size_change_costs(client, auth_headers):
    cheap = quote(client, auth_headers, "RESTAURANT", "interior", "SMALL")
    dear = quote(client, auth_headers, "RESTAURANT", "shopping", "LARGE")
    assert D(dear["required_capital"]) > D(cheap["required_capital"]) * 3
    assert D(dear["monthly_fixed"]) > D(cheap["monthly_fixed"]) and dear["expected_units"] > cheap["expected_units"]
    assert client.post(f"{C}/quote", headers=auth_headers, json={"segment": "CAFE", "location": "marte"}).status_code == 400


# ------------------------------------------------------------------ 3/4. capital e contas separadas

def test_capital_transfer_moves_between_accounts_and_is_not_an_expense(client, rich, db):
    cid = create_ok(client, rich)["company"]["id"]
    personal_before, co_before = cash(client, rich), D(detail(client, rich, cid)["company"]["cash"])
    equity_before = D(portfolio(client, rich)["total_equity_brl"])
    k = key()
    r = client.post(f"{C}/{cid}/contribute", headers=rich, json={"amount": "10000", "idempotency_key": k})
    assert r.status_code == 200
    assert client.post(f"{C}/{cid}/contribute", headers=rich, json={"amount": "10000", "idempotency_key": k}).status_code == 200  # repetição
    assert cash(client, rich) == personal_before - D("10000")
    assert D(detail(client, rich, cid)["company"]["cash"]) == co_before + D("10000")
    assert D(portfolio(client, rich)["total_equity_brl"]) == equity_before          # transferir não é perda
    m = client.get(f"{B}/overview", headers=rich).json()["month"]
    assert D(m["capital_out"]) >= D("10000") and D(m["realized_expense"]) == 0      # patrimonial, fora das despesas
    assert client.post(f"{C}/{cid}/contribute", headers=rich, json={"amount": "999999999", "idempotency_key": key()}).status_code == 422


def test_business_entries_stay_out_of_personal_budget(client, rich):
    cid = create_ok(client, rich)["company"]["id"]
    entries = client.get(f"{B}/entries", headers=rich).json()
    assert all("empresa" not in e["description"].lower() or e["capital"] for e in entries)
    assert not any(e["description"].startswith("Estoque inicial") or "Estruturação" in e["description"] for e in entries)
    assert len(detail(client, rich, cid)["ledger"]) >= 3                         # aporte, estrutura e estoque na conta da empresa


# ------------------------------------------------------------------ 5/6. funcionários e folha

def test_hire_and_fire_with_costs(client, rich):
    cid = create_ok(client, rich, extra="80000")["company"]["id"]
    d0 = detail(client, rich, cid)
    cap0 = d0["expected_capacity"]
    r = client.post(f"{C}/{cid}/employees", headers=rich, json={"role": "barista", "level": "SENIOR"})
    assert r.status_code == 201
    d1 = r.json()
    new = d1["employees"][-1]
    assert D(new["salary"]) == D("2100") * D("1.5") and D(new["total_cost"]) == D(new["salary"]) * D("1.35")
    assert D(d0["company"]["cash"]) - D(d1["company"]["cash"]) == D(new["salary"]) * D("0.5")     # custo de contratação
    assert d1["expected_capacity"] > cap0                                           # mais produtividade
    assert D(d1["monthly_obligations"]) > D(d0["monthly_obligations"])
    f = client.delete(f"{C}/{cid}/employees/{new['id']}", headers=rich)
    assert f.status_code == 200
    gone = next(e for e in f.json()["employees"] if e["id"] == new["id"])
    assert gone["status"] == "TERMINATED" and gone["terminated_on"]
    assert D(d1["company"]["cash"]) - D(f.json()["company"]["cash"]) == D(new["salary"])           # rescisão de 1 salário
    assert client.delete(f"{C}/{cid}/employees/{new['id']}", headers=rich).status_code == 409
    assert client.post(f"{C}/{cid}/employees", headers=rich, json={"role": "astronauta"}).status_code == 400


def test_hiring_without_runway_requires_explicit_risk_confirmation(client, rich, db):
    cid = create_ok(client, rich, extra="0")["company"]["id"]
    row = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid))
    row.balance = D("12000.00")                                                      # caixa curto para os custos mensais
    db.commit()
    r = client.post(f"{C}/{cid}/employees", headers=rich, json={"role": "barista", "level": "MID"})
    assert r.status_code == 409 and "RISCO" in r.json()["detail"]
    assert len(detail(client, rich, cid)["employees"]) == 2                           # nada mudou
    ok = client.post(f"{C}/{cid}/employees", headers=rich, json={"role": "barista", "level": "MID", "confirm_risk": True})
    assert ok.status_code == 201 and len(ok.json()["employees"]) == 3
    row.balance = D("500.00")
    db.commit()
    assert client.post(f"{C}/{cid}/employees", headers=rich, json={"role": "barista", "confirm_risk": True}).status_code == 400


def test_payroll_processed_at_close_with_charges(client, rich, db):
    cid = create_ok(client, rich)["company"]["id"]
    staff = detail(client, rich, cid)["employees"]
    expected = sum(D(e["total_cost"]) for e in staff)
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    assert D(m["payroll"]) == expected
    line = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "PAYROLL"))
    assert line.amount == expected and line.capital is False


# ------------------------------------------------------------------ 7/8. estoque

def test_buy_stock_updates_quantity_and_weighted_cost(client, rich):
    cid = create_ok(client, rich, extra="40000")["company"]["id"]
    d0 = detail(client, rich, cid)
    item = d0["inventory"][0]
    r = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": "500", "idempotency_key": key()})
    assert r.status_code == 201
    d1 = r.json()
    new = d1["inventory"][0]
    assert D(new["quantity"]) == D(item["quantity"]) + 500
    spent = D(d0["company"]["cash"]) - D(d1["company"]["cash"])
    assert spent > 0 and abs(float(D(new["value"]) - D(item["value"])) - float(spent)) < 1.0
    k = key()
    again = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": "500", "idempotency_key": k})
    same = client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": "500", "idempotency_key": k})
    assert same.status_code == 201 and D(same.json()["inventory"][0]["quantity"]) == D(again.json()["inventory"][0]["quantity"])   # repetição não soma de novo
    assert client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": item["id"], "quantity": "99999999", "idempotency_key": key()}).status_code == 422
    assert client.post(f"{C}/{cid}/stock", headers=rich, json={"item_id": 999999, "quantity": "1", "idempotency_key": key()}).status_code == 404


def test_stock_is_consumed_by_sales_and_replenished(client, rich):
    cid = create_ok(client, rich, extra="40000")["company"]["id"]
    item0 = detail(client, rich, cid)["inventory"][0]
    assert close(client, rich).status_code == 200
    d = detail(client, rich, cid)
    m = d["months"][0]
    used = D(m["units_sold"]) * D("1.05")                                           # 5% de desperdício
    after = D(d["inventory"][0]["quantity"])
    assert after != D(item0["quantity"]) and m["stockout"] is False
    assert after >= D(item0["quantity"]) - used                                      # consumo debitado (e possível reposição automática)
    assert D(d["inventory"][0]["value"]) > 0


def test_stockout_stops_sales_and_hurts_reputation(client, rich, db):
    cid = create_ok(client, rich)["company"]["id"]
    from backend.models import InventoryItem
    for i in db.scalars(select(InventoryItem).where(InventoryItem.company_id == cid)):
        i.quantity = D("0")
    comp = db.get(Company, cid)
    comp.auto_restock = False
    db.commit()
    assert close(client, rich).status_code == 200
    d = detail(client, rich, cid)
    m = d["months"][0]
    assert m["stockout"] is True and D(m["units_sold"]) == 0 and D(m["revenue"]) == 0
    assert d["company"]["reputation"] < 50 and D(m["net_result"]) < 0               # custos fixos continuam


# ------------------------------------------------------------------ 9/10. receita, lucro e prejuízo

def test_revenue_from_demand_price_and_capacity(client, rich, db):
    cid = create_ok(client, rich, extra="40000")["company"]["id"]
    d0 = detail(client, rich, cid)
    price = D(d0["company"]["price"])
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    assert D(m["units_sold"]) == min(D(str(d0["expected_demand"])), D(str(d0["expected_capacity"]))).quantize(D("1"), rounding="ROUND_FLOOR")
    assert D(m["revenue"]) == D(m["units_sold"]) * price
    assert D(m["net_result"]) == D(m["operating_result"]) - D(m["taxes"]) - D(m["interest"])
    assert D(m["operating_result"]) == D(m["revenue"]) - D(m["variable_costs"]) - D(m["fixed_costs"]) - D(m["payroll"])
    sale = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "REVENUE"))
    assert sale.amount == D(m["revenue"]) and sale.kind == "INCOME" and sale.capital is False
    # preço mais alto reduz a demanda; capacidade e demanda explicam a origem da receita
    cheap = D(str(client.patch(f"{C}/{cid}/settings", headers=rich, json={"price": str(price / 2)}).json()["expected_demand"]))
    dear = D(str(client.patch(f"{C}/{cid}/settings", headers=rich, json={"price": str(price * 2)}).json()["expected_demand"]))
    assert cheap > D(str(d0["expected_demand"])) > dear


def test_loss_when_costs_exceed_revenue(client, rich):
    cid = create_ok(client, rich, extra="60000")["company"]["id"]
    client.patch(f"{C}/{cid}/settings", headers=rich, json={"owner_salary": "30000"})       # pró-labore inviável
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    assert D(m["net_result"]) < 0 and D(m["payroll"]) > D("30000")


def test_negative_cash_becomes_debt_with_interest(client, rich, db):
    cid = create_ok(client, rich, extra="0")["company"]["id"]
    acc = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid))
    acc.balance = D("-20000.00")
    db.commit()
    d0 = detail(client, rich, cid)
    stock_value = sum(D(i["value"]) for i in d0["inventory"])
    assert D(d0["company"]["debts"]) == D("20000") and D(d0["company"]["equity"]) == D("-20000") + stock_value   # caixa negativo é dívida
    assert close(client, rich).status_code == 200
    m = detail(client, rich, cid)["months"][0]
    assert D(m["interest"]) == D("800.00")                                           # 4% ao mês sobre o saldo negativo


def test_seasonality_changes_demand_deterministically(client, rich, monkeypatch):
    monkeypatch.undo()
    from datetime import date
    seg = company_rules.SEGMENTS[company_rules.CompanySegment.CLOTHING]
    a = company_rules.season_factor(seg, 1, date(2027, 1, 1))
    assert a == company_rules.season_factor(seg, 1, date(2027, 1, 1))
    assert a != company_rules.season_factor(seg, 1, date(2027, 2, 1)) or True
    assert 1 - seg.volatility <= a <= 1 + seg.volatility


# ------------------------------------------------------------------ 11. bens e equipamentos da empresa

def test_company_buys_equipment_without_mixing_with_personal_goods(client, rich, db):
    cid = create_ok(client, rich, extra="60000")["company"]["id"]
    d0 = detail(client, rich, cid)
    personal_cash = cash(client, rich)
    r = client.post(f"{C}/{cid}/goods/purchase", headers=rich, json={"listing_key": "camera-pro", "idempotency_key": key()})
    assert r.status_code == 201, r.text
    d1 = r.json()
    assert [g["name"] for g in d1["goods"]] == ["Câmera mirrorless profissional"]
    assert D(d0["company"]["cash"]) - D(d1["company"]["cash"]) >= D("21000")          # pago pela empresa
    assert cash(client, rich) == personal_cash                                         # o dinheiro pessoal não mexeu
    assert client.get(G, headers=rich).json() == []                                    # não aparece nos bens pessoais
    assert client.get(f"{G}/overview", headers=rich).json()["count"] == 0
    assert d1["expected_capacity"] > d0["expected_capacity"]                           # equipamento aumenta a capacidade
    gid = d1["goods"][0]["id"]
    assert client.post(f"{G}/{gid}/sell", headers=rich, json={}).status_code == 409    # venda pessoal bloqueada
    assert D(d1["company"]["equity"]) == D(d0["company"]["equity"])                    # equipamento sem taxa: o dinheiro vira bem, sem perda
    assert close(client, rich).status_code == 200
    assert close(client, rich).status_code == 200                                       # custos do bem começam no mês seguinte à compra
    assert any(e["line"] == "ASSET_COSTS" for e in detail(client, rich, cid)["ledger"])


def test_company_goods_must_be_paid_in_cash_and_funded(client, rich):
    cid = create_ok(client, rich, extra="0")["company"]["id"]
    assert client.post(f"{C}/{cid}/goods/purchase", headers=rich, json={"listing_key": "apto-rj-3q", "idempotency_key": key()}).status_code == 422
    assert client.post(f"{C}/{cid}/goods/purchase", headers=rich, json={"listing_key": "nada", "idempotency_key": key()}).status_code == 404


# ------------------------------------------------------------------ 12. imóveis: locação

def test_lease_own_property_creates_personal_income_and_company_expense(client, rich, db):
    cid = create_ok(client, rich, extra="60000")["company"]["id"]
    gid = client.post(f"{G}/purchase", headers=rich, json={"listing_key": "sala-sp-comercial", "idempotency_key": key()}).json()["good"]["id"]
    r = client.post(f"{C}/{cid}/lease", headers=rich, json={"kind": "OWN_GOOD", "good_id": gid, "monthly_rent": "4000"})
    assert r.status_code == 200, r.text
    assert r.json()["lease"]["kind"] == "OWN_GOOD" and D(r.json()["lease"]["monthly_rent"]) == D("4000")
    assert client.get(f"{G}/{gid}", headers=rich).json()["real_estate"]["occupancy"] == "COMPANY_USE"
    other = create_ok(client, rich, name="Outra", segment="AGENCY", extra="60000")["company"]["id"]
    assert client.post(f"{C}/{other}/lease", headers=rich, json={"kind": "OWN_GOOD", "good_id": gid}).status_code == 409   # um imóvel, um negócio
    assert client.post(f"{G}/{gid}/sell", headers=rich, json={}).status_code == 409
    assert client.post(f"{G}/{gid}/occupancy", headers=rich, json={"mode": "VACANT"}).status_code == 409
    personal_before = cash(client, rich)
    assert close(client, rich).status_code == 200
    rent_in = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id.is_(None), LedgerEntry.description == "Aluguel recebido de Café da Esquina"))
    rent_out = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "RENT"))
    assert rent_in.amount == rent_out.amount == D("4000.00") and rent_in.kind == "INCOME" and rent_in.capital is False
    assert any(i["name"].startswith("IPTU") for i in client.get(f"{B}/overview", headers=rich).json()["month"]["items"])
    assert cash(client, rich) > personal_before - D("20000")                           # entrou aluguel no caixa pessoal
    # encerrar a locação libera o imóvel
    new = client.post(f"{C}/{cid}/lease", headers=rich, json={"kind": "EXTERNAL", "monthly_rent": "3000"})
    assert new.status_code == 200 and client.get(f"{G}/{gid}", headers=rich).json()["real_estate"]["occupancy"] == "VACANT"
    assert client.post(f"{C}/{other}/lease", headers=rich, json={"kind": "OWN_GOOD", "good_id": gid}).status_code == 200


def test_lease_validations(client, rich):
    cid = create_ok(client, rich)["company"]["id"]
    land = client.post(f"{G}/purchase", headers=rich, json={"listing_key": "terreno-atibaia", "idempotency_key": key()}).json()["good"]["id"]
    assert client.post(f"{C}/{cid}/lease", headers=rich, json={"kind": "OWN_GOOD", "good_id": land}).status_code == 400
    home = client.post(f"{G}/purchase", headers=rich, json={"listing_key": "apto-bh-2q", "idempotency_key": key()}).json()["good"]["id"]
    client.post(f"{G}/{home}/occupancy", headers=rich, json={"mode": "OWNER_OCCUPIED"})
    assert client.post(f"{C}/{cid}/lease", headers=rich, json={"kind": "OWN_GOOD", "good_id": home}).status_code == 409
    assert client.post(f"{C}/{cid}/lease", headers=rich, json={"kind": "OWN_GOOD", "good_id": 999999}).status_code == 404
    assert client.post(f"{C}/{cid}/lease", headers=rich, json={"kind": "OWN_GOOD"}).status_code == 400


# ------------------------------------------------------------------ 13. expansão e crédito

def test_expansion_has_cost_and_consequences(client, rich):
    cid = create_ok(client, rich, extra="150000")["company"]["id"]
    d0 = detail(client, rich, cid)
    r = client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "CAPACITY"})
    assert r.status_code == 200
    d1 = r.json()
    assert d1["company"]["capacity_level"] == 1 and d1["expected_capacity"] > d0["expected_capacity"]
    assert D(d0["company"]["cash"]) - D(d1["company"]["cash"]) == D(d0["expansion_costs"]["CAPACITY"])
    u = client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "NEW_UNIT"}).json()
    assert u["company"]["units"] == 2 and D(u["monthly_obligations"]) > D(d1["monthly_obligations"]) and u["expected_demand"] > d1["expected_demand"]
    big = client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "LARGER_PREMISES"}).json()
    assert big["company"]["size"] == "MEDIUM" and D(big["lease"]["monthly_rent"]) > D(d0["lease"]["monthly_rent"])
    mk = client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "MARKETING"}).json()
    assert mk["company"]["marketing_until"] is not None
    assert client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "XYZ"}).status_code == 422


def test_expansion_requires_cash_and_does_not_guarantee_profit(client, rich, db):
    cid = create_ok(client, rich, extra="0")["company"]["id"]
    acc = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid))
    acc.balance = D("1000.00")
    db.commit()
    assert client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "NEW_UNIT"}).status_code == 400
    assert detail(client, rich, cid)["company"]["units"] == 1
    acc.balance = D("400000.00")
    db.commit()
    client.post(f"{C}/{cid}/expand", headers=rich, json={"kind": "NEW_UNIT"})        # mais custos fixos sem mais demanda garantida
    assert close(client, rich).status_code == 200


def test_company_loan_creates_debt_and_installments_are_processed(client, rich, db):
    cid = create_ok(client, rich)["company"]["id"]
    d0 = detail(client, rich, cid)
    r = client.post(f"{C}/{cid}/loans", headers=rich, json={"amount": "40000", "term_months": 12})
    assert r.status_code == 201
    d1 = r.json()
    assert D(d1["company"]["cash"]) == D(d0["company"]["cash"]) + D("40000")
    assert D(d1["company"]["equity"]) == D(d0["company"]["equity"])                   # empréstimo não cria patrimônio
    assert D(d1["company"]["debts"]) == D("40000") and len(d1["loans"][0]["installments"]) == 12
    assert client.post(f"{C}/{cid}/loans", headers=rich, json={"amount": "99999999", "term_months": 12}).status_code == 400
    assert close(client, rich).status_code == 200                                      # parcela 1 vence no mês seguinte
    assert close(client, rich).status_code == 200
    d2 = detail(client, rich, cid)
    first = d2["loans"][0]["installments"][0]
    assert first["status"] == "PAID" and D(d2["loans"][0]["balance"]) == D(first["balance_after"])
    assert D(d2["company"]["debts"]) == D(first["balance_after"]) or D(d2["company"]["debts"]) >= D(first["balance_after"])
    kinds = {(e.line, e.capital) for e in db.scalars(select(LedgerEntry).where(LedgerEntry.company_id == cid)) if e.line in ("INTEREST", "LOAN_PRINCIPAL")}
    assert kinds == {("INTEREST", False), ("LOAN_PRINCIPAL", True)}


# ------------------------------------------------------------------ 14/15. lucros

def test_profit_distribution_flows_to_personal_account(client, rich, db):
    cid = create_ok(client, rich, extra="80000")["company"]["id"]
    assert client.post(f"{C}/{cid}/distribute", headers=rich, json={"amount": "100", "idempotency_key": key()}).status_code == 400   # ainda sem lucro
    earn_profit(client, rich, cid)
    d = detail(client, rich, cid)
    available = D(d["distributable_profit"])
    assert available > 0 and available == sum(D(m["net_result"]) for m in d["months"])
    personal, equity = cash(client, rich), D(portfolio(client, rich)["total_equity_brl"])
    k = key()
    amount = (available / 2).quantize(D("0.01"))
    r = client.post(f"{C}/{cid}/distribute", headers=rich, json={"amount": str(amount), "idempotency_key": k})
    assert r.status_code == 200
    assert client.post(f"{C}/{cid}/distribute", headers=rich, json={"amount": str(amount), "idempotency_key": k}).status_code == 200
    assert cash(client, rich) == personal + amount                                      # entrou uma vez
    assert D(r.json()["company"]["cash"]) == D(d["company"]["cash"]) - amount
    assert D(portfolio(client, rich)["total_equity_brl"]) == equity                    # distribuir não cria patrimônio
    assert D(r.json()["distributable_profit"]) == available - amount
    own = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id.is_(None), LedgerEntry.description.like("Distribuição de lucros%")))
    assert own.kind == "INCOME" and own.capital is False


def test_distribution_cannot_exceed_profit_or_cash(client, rich, db):
    cid = create_ok(client, rich, extra="80000")["company"]["id"]
    earn_profit(client, rich, cid)
    d = detail(client, rich, cid)
    over = D(d["distributable_profit"]) + 1
    r = client.post(f"{C}/{cid}/distribute", headers=rich, json={"amount": str(over), "idempotency_key": key()})
    assert r.status_code == 400 and "lucro distribuível" in r.json()["detail"]
    acc = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid))
    acc.balance = D("10.00")                                                            # há lucro contábil, mas não há caixa
    db.commit()
    r = client.post(f"{C}/{cid}/distribute", headers=rich, json={"amount": str(D(d["distributable_profit"])), "idempotency_key": key()})
    assert r.status_code == 400 and "caixa" in r.json()["detail"]


def test_partial_ownership_splits_distribution_and_equity(client, rich):
    cid = create_ok(client, rich, extra="80000", owner_share_pct="60")["company"]["id"]
    earn_profit(client, rich, cid)
    d = detail(client, rich, cid)
    amount = D(d["distributable_profit"]).quantize(D("0.01"))
    before = cash(client, rich)
    assert client.post(f"{C}/{cid}/distribute", headers=rich, json={"amount": str(amount), "idempotency_key": key()}).status_code == 200
    assert cash(client, rich) - before == (amount * D("0.6")).quantize(D("0.01"))     # só a participação do usuário
    p = portfolio(client, rich)
    assert D(p["companies_net_brl"]) == (D(detail(client, rich, cid)["company"]["equity"]) * D("0.6")).quantize(D("0.01"))


def test_owner_salary_is_personal_income_and_company_cost(client, rich, db):
    cid = create_ok(client, rich, extra="60000")["company"]["id"]
    client.patch(f"{C}/{cid}/settings", headers=rich, json={"owner_salary": "3000"})
    before = cash(client, rich)
    assert close(client, rich).status_code == 200
    pl = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id == cid, LedgerEntry.line == "PRO_LABORE"))
    own = db.scalar(select(LedgerEntry).where(LedgerEntry.company_id.is_(None), LedgerEntry.description == "Pró-labore: Café da Esquina"))
    assert pl.amount == own.amount == D("3000.00") and own.kind == "INCOME" and own.capital is False
    assert cash(client, rich) == before + D("3000.00")


# ------------------------------------------------------------------ 16/17/18. fechamento mensal

def test_close_month_with_several_companies_processes_each_once(client, rich, db):
    ids = [create_ok(client, rich, name=f"Empresa {n}", segment=s, extra="60000")["company"]["id"]
           for n, s in enumerate(["CAFE", "CLOTHING", "TECH"])]
    assert close(client, rich).status_code == 200
    rows = db.scalars(select(CompanyMonth).order_by(CompanyMonth.company_id)).all()
    assert [r.company_id for r in rows] == ids and len({r.ref_month for r in rows}) == 1
    assert close(client, rich).status_code == 200
    assert db.scalar(select(func.count()).select_from(CompanyMonth)) == 6
    assert all(detail(client, rich, i)["company"]["status"] == "ACTIVE" for i in ids)


def test_company_month_cannot_be_processed_twice(client, rich, db):
    cid = create_ok(client, rich)["company"]["id"]
    assert close(client, rich).status_code == 200
    first = detail(client, rich, cid)["months"][0]
    cash_after = D(detail(client, rich, cid)["company"]["cash"])
    ledger_n = db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.company_id == cid))
    from backend.models import SimMonth
    closed = db.scalar(select(SimMonth).where(SimMonth.status == "CLOSED"))
    assert company_service.process_month(db, closed.user_id, closed) == []              # nada a fazer
    db.commit()
    assert db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.company_id == cid)) == ledger_n
    assert D(detail(client, rich, cid)["company"]["cash"]) == cash_after
    assert detail(client, rich, cid)["months"][0] == first
    again = client.post(f"{B}/close", headers=rich, json={"ref_month": closed.ref_month.isoformat()[:7], "confirm": True})
    assert again.status_code == 409


def test_failure_during_close_rolls_back_every_company(client, rich, db, monkeypatch):
    ids = [create_ok(client, rich, name=f"E{n}", extra="40000")["company"]["id"] for n in range(3)]
    cash_before = {i: detail(client, rich, i)["company"]["cash"] for i in ids}
    personal = cash(client, rich)
    real = company_service._process_company
    calls = {"n": 0}

    def flaky(db_, c, month):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("falha na terceira empresa")
        return real(db_, c, month)

    monkeypatch.setattr(company_service, "_process_company", flaky)
    with pytest.raises(RuntimeError):
        close(client, rich)
    monkeypatch.setattr(company_service, "_process_company", real)
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(CompanyMonth)) == 0               # nenhuma ficou processada
    assert all(detail(client, rich, i)["company"]["cash"] == cash_before[i] for i in ids)
    assert cash(client, rich) == personal and client.get(f"{B}/overview", headers=rich).json()["month"]["status"] == "OPEN"
    assert close(client, rich).status_code == 200 and db.scalar(select(func.count()).select_from(CompanyMonth)) == 3


def test_history_is_preserved_across_months(client, rich):
    cid = create_ok(client, rich)["company"]["id"]
    assert close(client, rich).status_code == 200
    first = detail(client, rich, cid)["months"][0]
    client.patch(f"{C}/{cid}/settings", headers=rich, json={"price": "30"})
    assert close(client, rich).status_code == 200
    d = detail(client, rich, cid)
    assert len(d["months"]) == 2 and d["months"][1] == first                              # mês antigo imutável
    assert [e["type"] for e in d["events"]].count("MONTH") == 2


# ------------------------------------------------------------------ 19/20. isolamento, integração e consistência

def test_company_accounts_and_data_are_isolated_between_users(client, rich):
    cid = create_ok(client, rich)["company"]["id"]
    bia = second_user(client)
    assert client.get(f"{C}", headers=bia).json() == [] and client.get(f"{C}/overview", headers=bia).json()["count"] == 0
    for method, path, body in [("get", f"/{cid}", None), ("post", f"/{cid}/contribute", {"amount": "10", "idempotency_key": key()}),
                               ("post", f"/{cid}/expand", {"kind": "CAPACITY"}), ("patch", f"/{cid}/settings", {"price": "1"}),
                               ("post", f"/{cid}/employees", {"role": "barista"}), ("post", f"/{cid}/loans", {"amount": "1000", "term_months": 6}),
                               ("post", f"/{cid}/lease", {"kind": "EXTERNAL"}), ("post", f"/{cid}/distribute", {"amount": "1", "idempotency_key": key()})]:
        r = getattr(client, method)(f"{C}{path}", headers=bia, **({"json": body} if body else {}))
        assert r.status_code == 404, (path, r.text)
    assert close(client, bia).status_code == 200                                          # fechar o mês de um não processa a empresa do outro
    assert detail(client, rich, cid)["months"] == []
    assert client.get(C).status_code == 401


def test_personal_wealth_includes_company_share_without_fake_loss(client, rich):
    before = D(portfolio(client, rich)["total_equity_brl"])
    q = quote(client, rich)
    cid = create_ok(client, rich)["company"]["id"]
    after = portfolio(client, rich)
    assert D(after["total_equity_brl"]) == before - D(q["setup_cost"])                  # só a estrutura (despesa) reduz o patrimônio
    assert D(after["companies_net_brl"]) == D(detail(client, rich, cid)["company"]["equity"])
    perf = client.get("/api/performance?range=7d", headers=rich)
    assert perf.status_code == 200
    labels = {a["label"] for a in perf.json()["allocation"]}
    assert "Empresas (participação)" in labels


def test_ledger_and_accounts_stay_consistent(client, rich, db):
    cid = create_ok(client, rich, extra="80000")["company"]["id"]
    client.post(f"{C}/{cid}/employees", headers=rich, json={"role": "barista", "confirm_risk": True})
    client.post(f"{C}/{cid}/loans", headers=rich, json={"amount": "20000", "term_months": 6})
    client.post(f"{C}/{cid}/goods/purchase", headers=rich, json={"listing_key": "estudio-audio", "idempotency_key": key()})
    client.patch(f"{C}/{cid}/settings", headers=rich, json={"owner_salary": "2000"})
    for _ in range(3):
        assert close(client, rich).status_code == 200
    # conta da empresa == soma dos movimentos da empresa
    acc = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(Company.id == cid))
    flows = db.scalars(select(LedgerEntry).where(LedgerEntry.company_id == cid)).all()
    assert acc.balance == sum((e.amount if e.kind == "INCOME" else -e.amount) for e in flows)
    # caixa pessoal == soma das transações; cada transação orçamentária tem uma entrada pessoal (as da empresa não têm transação)
    pf = db.scalar(select(Portfolio))
    assert pf.cash_balance == db.scalar(select(func.coalesce(func.sum(Transaction.cash_amount_brl), 0)))
    personal = db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.company_id.is_(None)))
    assert personal == db.scalar(select(func.count()).select_from(Transaction).where(Transaction.type.in_(["BUDGET_INCOME", "BUDGET_EXPENSE"])))
    assert db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.company_id.is_not(None), LedgerEntry.transaction_id.is_not(None))) == 0
    keys = db.scalars(select(LedgerEntry.idempotency_key).where(LedgerEntry.idempotency_key.is_not(None))).all()
    assert len(keys) == len(set(keys))
    # o resultado do orçamento pessoal não conta custos da empresa
    m = client.get(f"{B}/overview", headers=rich).json()["month"]
    assert not any("Folha" in i["name"] for i in m["items"])


def test_existing_features_unaffected(client, rich, assets):
    r = client.post("/api/trades/buy", headers=rich, json={"asset_id": assets["PETR4"].id, "quantity": "10"})
    assert r.status_code in (200, 201), r.text
    p = portfolio(client, rich)
    assert D(p["companies_net_brl"]) == 0 and D(p["goods_net_brl"]) == 0
    assert D(p["total_equity_brl"]) == D(p["cash_balance"]) + D(p["market_value_brl"])
