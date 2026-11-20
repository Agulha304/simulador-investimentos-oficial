from tests.conftest import credit
"""Bens, imóveis, financiamentos e patrimônio (etapa 2) integrados ao orçamento, ao ledger e ao fechamento do mês."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.models import (
    Good, GoodValue, InstallmentStatus, LedgerEntry, Loan, LoanInstallment, Occupancy, Portfolio, RealEstateDetails,
    SimMonth, Transaction,
)
from backend.services import goods_rules as rules
from backend.services import goods_service

D = Decimal
G = "/api/goods"
B = "/api/budget"

CAR = "carro-hatch-novo"        # R$ 82 mil, financiável, depreciação
HOUSE = "apto-bh-2q"            # R$ 540 mil, residencial
LAND = "terreno-atibaia"
GUITAR = "guitarra-vintage"


def portfolio(client, h):
    return client.get("/api/portfolio", headers=h).json()


def cash(client, h) -> Decimal:
    return D(portfolio(client, h)["cash_balance"])


def fund(client, h, amount="3000000"):
    credit(client, h, amount)


def listing(client, h, key):
    return next(x for x in client.get(f"{G}/market", headers=h).json() if x["key"] == key)


def buy(client, h, key, **kw):
    body = {"listing_key": key, "idempotency_key": uuid.uuid4().hex, **kw}
    return client.post(f"{G}/purchase", headers=h, json=body)


def buy_ok(client, h, key, **kw):
    r = buy(client, h, key, **kw)
    assert r.status_code == 201, r.text
    return r.json()


def overview(client, h):
    r = client.get(f"{B}/overview", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def close(client, h):
    ref = overview(client, h)["month"]["ref_month"][:7]
    return client.post(f"{B}/close", headers=h, json={"ref_month": ref, "confirm": True})


def detail(client, h, gid):
    return client.get(f"{G}/{gid}", headers=h).json()


def second_user(client):
    r = client.post("/api/auth/register", json={"email": "bia@example.com", "name": "Bia", "password": "segredo123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def open_month(db):
    return db.scalar(select(SimMonth).where(SimMonth.status == "OPEN"))


# ------------------------------------------------------------------ mercado

def test_market_lists_filters_and_prices(client, auth_headers):
    allm = client.get(f"{G}/market", headers=auth_headers).json()
    assert len(allm) >= 25 and {x["category"] for x in allm} >= {"RESIDENTIAL", "CAR", "INSTRUMENT", "ANTIQUE"}
    cars = client.get(f"{G}/market?category=CAR", headers=auth_headers).json()
    assert cars and all(x["category"] == "CAR" for x in cars)
    cheap = client.get(f"{G}/market?max_price=10000", headers=auth_headers).json()
    assert cheap == [] or all(D(x["price"]) <= 10000 for x in cheap)
    assert [x["key"] for x in client.get(f"{G}/market?q=leblon", headers=auth_headers).json()] == ["apto-rj-3q"]
    car = listing(client, auth_headers, CAR)
    assert car["financing"]["max_term_months"] == 60 and car["owned"] is False
    assert listing(client, auth_headers, GUITAR)["financing"] is None


def test_market_requires_auth(client):
    assert client.get(f"{G}/market").status_code == 401
    assert client.post(f"{G}/purchase", json={}).status_code == 401


# ------------------------------------------------------------------ 1. compra à vista

def test_buy_cash_moves_money_and_keeps_wealth_except_fees(client, auth_headers):
    before = portfolio(client, auth_headers)
    car = listing(client, auth_headers, CAR)
    price, fee = D(car["price"]), D(car["purchase_fee"])
    d = buy_ok(client, auth_headers, CAR)
    after = portfolio(client, auth_headers)
    assert D(after["cash_balance"]) == D(before["cash_balance"]) - price - fee
    assert D(d["good"]["current_value"]) == price and D(d["good"]["acquisition_cost"]) == price + fee
    # patrimônio cai só nas taxas (o bem entra no patrimônio): comprar não vira prejuízo falso
    assert D(after["total_equity_brl"]) == D(before["total_equity_brl"]) - fee
    assert D(after["goods_net_brl"]) == price
    entries = {e["description"]: e for e in client.get(f"{B}/entries", headers=auth_headers).json()}
    assert entries[f"Compra: {d['good']['name']}"]["capital"] is True
    assert entries[f"Taxas e impostos da compra: {d['good']['name']}"]["capital"] is False
    assert [v["source"] for v in d["values"]] == ["PURCHASE"] and d["events"][0]["type"] == "PURCHASE"
    assert listing(client, auth_headers, CAR)["owned"] is True


def test_purchase_is_idempotent_and_unique(client, auth_headers):
    key = uuid.uuid4().hex
    a = buy(client, auth_headers, CAR, idempotency_key=key)
    start = cash(client, auth_headers)
    b = buy(client, auth_headers, CAR, idempotency_key=key)
    assert a.status_code == b.status_code == 201 and a.json()["good"]["id"] == b.json()["good"]["id"]
    assert cash(client, auth_headers) == start
    assert buy(client, auth_headers, CAR).status_code == 409                 # já possui este bem


def test_purchase_without_funds_changes_nothing(client, auth_headers, db):
    start = cash(client, auth_headers)
    r = buy(client, auth_headers, "apto-rj-3q")                              # R$ 1,85 mi > saldo
    assert r.status_code == 422
    assert cash(client, auth_headers) == start
    assert db.scalar(select(func.count()).select_from(Good)) == 0
    assert db.scalar(select(func.count()).select_from(LedgerEntry)) == 0


def test_purchase_validations(client, auth_headers):
    assert buy(client, auth_headers, "nao-existe").status_code == 404
    assert buy(client, auth_headers, GUITAR, financed=True, down_payment="100", term_months=12).status_code == 400
    fund(client, auth_headers)
    assert buy(client, auth_headers, HOUSE, financed=True, down_payment="1000", term_months=360).status_code == 400   # entrada mínima
    assert buy(client, auth_headers, HOUSE, financed=True, down_payment="200000", term_months=999).status_code == 422
    assert buy(client, auth_headers, CAR, financed=True, down_payment="20000", term_months=120).status_code == 400    # acima do prazo máximo do carro (60)
    assert buy(client, auth_headers, CAR, extra_costs="-1").status_code == 422


# ------------------------------------------------------------------ 2/12/13. financiamento

@pytest.mark.parametrize("system", ["PRICE", "SAC"])
def test_buy_financed_schedule_and_cash(client, auth_headers, db, system):
    fund(client, auth_headers)
    before = portfolio(client, auth_headers)
    house = listing(client, auth_headers, HOUSE)
    price, fee = D(house["price"]), D(house["purchase_fee"])
    down = D(house["financing"]["min_down_payment"])
    d = buy_ok(client, auth_headers, HOUSE, financed=True, down_payment=str(down), term_months=360, system=system)
    after = portfolio(client, auth_headers)
    assert D(after["cash_balance"]) == D(before["cash_balance"]) - down - fee
    loan = d["loan"]
    assert D(loan["principal"]) == price - down and loan["system"] == system and len(loan["installments"]) == 360
    assert sum(D(i["amortization"]) for i in loan["installments"]) == D(loan["principal"])    # amortização fecha o principal
    assert all(D(i["payment"]) == D(i["interest"]) + D(i["amortization"]) for i in loan["installments"])
    assert D(loan["installments"][-1]["balance_after"]) == 0
    # patrimônio: bem − dívida; só entrada e taxas saíram do caixa, a dívida é abatida do valor do bem
    assert D(after["goods_net_brl"]) == D(d["good"]["current_value"]) - (price - down)
    assert D(after["total_equity_brl"]) == D(before["total_equity_brl"]) - fee
    if system == "SAC":
        assert D(loan["installments"][0]["amortization"]) == D(loan["installments"][5]["amortization"])
        assert D(loan["installments"][0]["payment"]) > D(loan["installments"][-1]["payment"])
    else:
        pays = {D(i["payment"]) for i in loan["installments"][:-1]}
        assert max(pays) - min(pays) <= D("0.02")
    assert db.scalar(select(func.count()).select_from(LoanInstallment)) == 360


def test_installments_processed_on_close_separating_interest_and_principal(client, auth_headers, db):
    fund(client, auth_headers)
    d = buy_ok(client, auth_headers, HOUSE, financed=True, down_payment="110000", term_months=120)
    gid = d["good"]["id"]
    inst1 = d["loan"]["installments"][0]
    first = overview(client, auth_headers)
    assert not any(i["source"] for i in first["month"]["items"] if i["source"] and "loan:" in i["source"])   # 1ª parcela só no mês seguinte
    assert close(client, auth_headers).status_code == 200

    o2 = overview(client, auth_headers)
    items = [i for i in o2["month"]["items"] if i["source"] and i["source"].startswith("loan:")]
    assert {i["capital"] for i in items} == {False, True}                    # juros = despesa; amortização = patrimonial
    start = cash(client, auth_headers)
    assert close(client, auth_headers).status_code == 200
    # parcela 1 foi cobrada (juros + amortização) no fechamento do mês 2
    after = detail(client, auth_headers, gid)
    assert after["loan"]["paid_installments"] == 1
    assert D(after["loan"]["balance"]) == D(inst1["balance_after"])
    assert cash(client, auth_headers) < start
    ledger = [e for e in after["entries"] if e["origin"] == "ASSET" and "financiamento" in e["description"].lower()]
    kinds = {e["capital"]: D(e["amount"]) for e in ledger}
    assert kinds[False] == D(inst1["interest"]) and kinds[True] == D(inst1["amortization"])
    assert db.scalar(select(func.count()).select_from(LoanInstallment).where(
        LoanInstallment.status == InstallmentStatus.PAID)) == 1


def test_balance_keeps_dropping_each_month(client, auth_headers):
    fund(client, auth_headers)
    d = buy_ok(client, auth_headers, HOUSE, financed=True, down_payment="150000", term_months=60)
    gid, insts = d["good"]["id"], d["loan"]["installments"]
    for n in (0, 1, 2, 3):                                                    # compra + 3 fechamentos
        assert close(client, auth_headers).status_code == 200
        paid = max(0, n)                                                      # a parcela 1 vence no mês seguinte à compra
        expected = insts[paid - 1]["balance_after"] if paid else d["loan"]["principal"]
        assert D(detail(client, auth_headers, gid)["loan"]["balance"]) == D(expected)


# ------------------------------------------------------------------ 3/4. venda

def test_sell_cash_good_result_and_wealth(client, auth_headers):
    d = buy_ok(client, auth_headers, CAR)
    gid = d["good"]["id"]
    q = client.get(f"{G}/{gid}/sale-quote", headers=auth_headers).json()
    start = cash(client, auth_headers)
    eq = D(portfolio(client, auth_headers)["total_equity_brl"])
    r = client.post(f"{G}/{gid}/sell", headers=auth_headers, json={})
    assert r.status_code == 200, r.text
    sold = r.json()
    assert sold["good"]["status"] == "SOLD" and D(sold["good"]["current_value"]) == 0
    assert cash(client, auth_headers) == start + D(q["net_cash"])
    assert D(sold["good"]["sale_result"]) == D(q["result"]) < 0               # carro vendido por menos do que custou
    assert D(portfolio(client, auth_headers)["goods_net_brl"]) == 0
    assert D(portfolio(client, auth_headers)["total_equity_brl"]) == eq - D(q["fees"])
    assert sold["events"][0]["type"] == "SALE" and any(v["source"] == "SALE" for v in sold["values"])


def test_cannot_sell_twice_or_sell_foreign_good(client, auth_headers):
    gid = buy_ok(client, auth_headers, CAR)["good"]["id"]
    assert client.post(f"{G}/{gid}/sell", headers=auth_headers, json={}).status_code == 200
    after_first = cash(client, auth_headers)
    assert client.post(f"{G}/{gid}/sell", headers=auth_headers, json={}).status_code == 409
    assert cash(client, auth_headers) == after_first
    bia = second_user(client)
    other = buy_ok(client, auth_headers, GUITAR)["good"]["id"]
    assert client.post(f"{G}/{other}/sell", headers=bia, json={}).status_code == 404
    assert client.get(f"{G}/{other}", headers=bia).status_code == 404
    assert client.get(f"{G}", headers=bia).json() == []


def test_sell_financed_good_pays_off_debt(client, auth_headers, db):
    fund(client, auth_headers)
    d = buy_ok(client, auth_headers, HOUSE, financed=True, down_payment="150000", term_months=240)
    gid = d["good"]["id"]
    q = client.get(f"{G}/{gid}/sale-quote?sale_price=600000", headers=auth_headers).json()
    assert D(q["loan_payoff"]) == D(d["loan"]["principal"]) and D(q["net_cash"]) == D("600000") - D(q["fees"]) - D(q["loan_payoff"])
    start = cash(client, auth_headers)
    r = client.post(f"{G}/{gid}/sell", headers=auth_headers, json={"sale_price": "600000"})
    assert r.status_code == 200
    assert cash(client, auth_headers) == start + D(q["net_cash"])
    out = r.json()
    assert out["loan"]["status"] == "SETTLED" and D(out["loan"]["balance"]) == 0
    assert all(i["status"] == "CANCELLED" for i in out["loan"]["installments"])
    assert D(portfolio(client, auth_headers)["goods_net_brl"]) == 0
    assert db.scalar(select(func.count()).select_from(LoanInstallment).where(LoanInstallment.status == "PENDING")) == 0


def test_sell_requires_money_for_debt_payoff(client, auth_headers, db):
    fund(client, auth_headers)
    d = buy_ok(client, auth_headers, HOUSE, financed=True, down_payment="110000", term_months=360)
    gid = d["good"]["id"]
    db_cash = db.scalar(select(Portfolio))
    db_cash.cash_balance = D("100.00")                                         # sem caixa
    db.commit()
    r = client.post(f"{G}/{gid}/sell", headers=auth_headers, json={"sale_price": "1000"})   # vende por quase nada
    assert r.status_code == 422
    assert detail(client, auth_headers, gid)["good"]["status"] == "ACTIVE"


# ------------------------------------------------------------------ 5/6. imóveis e moradia

def test_buy_property_creates_details_costs_and_budget_items(client, auth_headers):
    fund(client, auth_headers)
    d = buy_ok(client, auth_headers, HOUSE)
    re = d["real_estate"]
    assert re["property_type"] == "apartment" and D(re["area_m2"]) == 68 and re["bedrooms"] == 2
    assert re["occupancy"] == "VACANT"
    assert {c["kind"] for c in d["costs"]} == {"IPTU", "CONDO", "MAINTENANCE"}
    gid = d["good"]["id"]
    assert close(client, auth_headers).status_code == 200                    # custos começam no mês seguinte à compra
    items = [i for i in overview(client, auth_headers)["month"]["items"] if i["source"] and i["source"].startswith(f"good:{gid}:cost")]
    assert len(items) == 3 and all(not i["capital"] for i in items)
    assert all(i["source"] for i in items)                                   # gerados pelo bem


def test_generated_items_cannot_be_edited_in_budget(client, auth_headers):
    fund(client, auth_headers)
    buy_ok(client, auth_headers, HOUSE)
    assert close(client, auth_headers).status_code == 200
    item = next(i for i in overview(client, auth_headers)["month"]["items"] if i["source"])
    assert client.patch(f"{B}/items/{item['id']}", headers=auth_headers, json={"planned_amount": "1.00"}).status_code == 409
    assert client.delete(f"{B}/items/{item['id']}", headers=auth_headers).status_code == 409


def test_owner_occupied_stops_rent_keeps_history_and_adds_costs(client, auth_headers):
    fund(client, auth_headers)
    cat = next(c["id"] for c in client.get(f"{B}/categories", headers=auth_headers).json() if c["name"] == "Moradia")
    r = client.post(f"{B}/items", headers=auth_headers, json={
        "name": "Aluguel residencial", "kind": "EXPENSE", "category_id": cat, "planned_amount": "1500", "recurring": True})
    assert r.status_code == 201
    assert close(client, auth_headers).status_code == 200                      # mês 1 paga o aluguel
    gid = buy_ok(client, auth_headers, HOUSE)["good"]["id"]
    cands = client.get(f"{G}/housing-candidates", headers=auth_headers).json()
    assert [c["name"] for c in cands] == ["Aluguel residencial"]
    r = client.post(f"{G}/{gid}/occupancy", headers=auth_headers, json={
        "mode": "OWNER_OCCUPIED", "end_recurring_item_ids": [cands[0]["id"]]})
    assert r.status_code == 200 and r.json()["real_estate"]["occupancy"] == "OWNER_OCCUPIED"
    names = [i["name"] for i in overview(client, auth_headers)["month"]["items"]]
    assert "Aluguel residencial" not in names                                  # mês aberto: previsto removido
    assert close(client, auth_headers).status_code == 200
    o3 = overview(client, auth_headers)
    names3 = [i["name"] for i in o3["month"]["items"]]
    assert "Aluguel residencial" not in names3 and any(n.startswith("IPTU") for n in names3) and any(n.startswith("Condomínio") for n in names3)
    months = client.get(f"{B}/months", headers=auth_headers).json()
    first = min((m for m in months if m["status"] == "CLOSED"), key=lambda m: m["ref_month"])
    assert D(first["expense"]) >= D("1500")                                    # histórico do aluguel preservado
    m1 = client.get(f"{B}/months/{first['ref_month'][:7]}", headers=auth_headers).json()
    assert any(i["name"] == "Aluguel residencial" and D(i["realized"]) == 1500 for i in m1["items"])
    assert client.get(f"{G}/housing-candidates", headers=auth_headers).json() == []


def test_only_one_home_and_only_residential(client, auth_headers):
    fund(client, auth_headers)
    a = buy_ok(client, auth_headers, HOUSE)["good"]["id"]
    b = buy_ok(client, auth_headers, "casa-flo-2q")["good"]["id"]
    assert client.post(f"{G}/{a}/occupancy", headers=auth_headers, json={"mode": "OWNER_OCCUPIED"}).status_code == 200
    assert client.post(f"{G}/{b}/occupancy", headers=auth_headers, json={"mode": "OWNER_OCCUPIED"}).status_code == 200
    assert detail(client, auth_headers, a)["real_estate"]["occupancy"] == "VACANT"
    com = buy_ok(client, auth_headers, "sala-sp-comercial")["good"]["id"]
    assert client.post(f"{G}/{com}/occupancy", headers=auth_headers, json={"mode": "OWNER_OCCUPIED"}).status_code == 400
    assert client.post(f"{G}/{b}/occupancy", headers=auth_headers, json={"mode": "RENTED"}).status_code == 400
    land = buy_ok(client, auth_headers, LAND)["good"]["id"]
    assert client.post(f"{G}/{land}/occupancy", headers=auth_headers, json={"mode": "LISTED_FOR_RENT"}).status_code == 400
    assert client.post(f"{G}/{CAR}/occupancy", headers=auth_headers, json={"mode": "VACANT"}).status_code == 422


# ------------------------------------------------------------------ 7/8/9. aluguel e vacância

def _rent_out(client, h, db, monkeypatch=None):
    fund(client, h)
    gid = buy_ok(client, h, HOUSE)["good"]["id"]
    r = client.post(f"{G}/{gid}/occupancy", headers=h, json={"mode": "LISTED_FOR_RENT", "monthly_rent": "2800"})
    assert r.status_code == 200
    return gid


def test_listed_property_has_no_rent_until_tenant_arrives(client, auth_headers, db):
    gid = _rent_out(client, auth_headers, db)
    assert not any(i["source"] and i["source"].endswith(":rent") for i in overview(client, auth_headers)["month"]["items"])
    d = detail(client, auth_headers, gid)
    assert d["real_estate"]["occupancy"] == "LISTED_FOR_RENT" and D(d["real_estate"]["monthly_rent"]) == D("2800")


def test_rent_received_at_close_once_with_tax(client, auth_headers, db, monkeypatch):
    gid = _rent_out(client, auth_headers, db)
    monkeypatch.setattr(rules, "hash01", lambda *a: 0.0)                       # inquilino chega no próximo mês
    assert close(client, auth_headers).status_code == 200                      # mês 1: sem aluguel; abre mês 2 já alugado
    d = detail(client, auth_headers, gid)
    assert d["real_estate"]["occupancy"] == "RENTED" and any(e["type"] == "RENTED" for e in d["events"])
    o = overview(client, auth_headers)
    rent = next(i for i in o["month"]["items"] if i["source"] == f"good:{gid}:rent")
    tax = next(i for i in o["month"]["items"] if i["source"] == f"good:{gid}:rent_tax")
    assert D(rent["planned_amount"]) == D("2800") and D(tax["planned_amount"]) == D("40.56")      # IR progressivo (carnê-leão): 2.800 × 7,5% − 169,44
    monkeypatch.setattr(rules, "hash01", lambda *a: 0.99)                      # sem vacância nem mudanças de valor
    start = cash(client, auth_headers)
    assert close(client, auth_headers).status_code == 200
    delta = cash(client, auth_headers) - start
    costs = sum(D(i["planned_amount"]) for i in o["month"]["items"] if i["source"] and i["source"].startswith(f"good:{gid}:cost"))
    assert delta == D("2800") - D("40.56") - costs
    d2 = detail(client, auth_headers, gid)
    assert sum(1 for e in d2["entries"] if e["description"].startswith("Aluguel recebido")) == 1
    assert D(d2["income_total"]) == D("2800")


def test_vacancy_interrupts_rent(client, auth_headers, db, monkeypatch):
    gid = _rent_out(client, auth_headers, db)
    monkeypatch.setattr(rules, "hash01", lambda *a: 0.0)
    assert close(client, auth_headers).status_code == 200                      # alugado
    assert close(client, auth_headers).status_code == 200                      # inquilino sai (0.0 < prob. de saída)
    d = detail(client, auth_headers, gid)
    assert any(e["type"] == "VACATED" for e in d["events"])
    # anunciado de novo, e (com 0.0) alugado outra vez no mesmo fechamento; força a vacância mantendo o ruído alto
    monkeypatch.setattr(rules, "hash01", lambda *a: 0.99)
    row = db.scalar(select(RealEstateDetails).where(RealEstateDetails.good_id == gid))
    db.refresh(row)
    assert row.occupancy in (Occupancy.RENTED, Occupancy.LISTED_FOR_RENT)
    o = overview(client, auth_headers)
    has_rent = any(i["source"] == f"good:{gid}:rent" for i in o["month"]["items"])
    assert has_rent == (row.occupancy == Occupancy.RENTED)
    if row.occupancy == Occupancy.LISTED_FOR_RENT:
        assert not has_rent                                                       # vacância: sem aluguel previsto
        before = cash(client, auth_headers)
        assert close(client, auth_headers).status_code == 200
        assert cash(client, auth_headers) <= before                               # só custos, nenhum recebimento


def test_vacancy_state_roll_is_deterministic(client, auth_headers, db):
    gid = _rent_out(client, auth_headers, db)
    assert close(client, auth_headers).status_code == 200
    state = detail(client, auth_headers, gid)["real_estate"]["occupancy"]
    assert state == ("RENTED" if rules.hash01("fill", gid, open_month(db).ref_month.isoformat()) < min(
        0.9, max(0.1, rules.FILL_BASE_PROB * float(rules.market_rent(rules.GoodCategory.RESIDENTIAL, D(detail(client, auth_headers, gid)["good"]["current_value"])) / D("2800")))) else "LISTED_FOR_RENT")


# ------------------------------------------------------------------ 10. manutenção e custos

def test_maintenance_expense_and_idempotency(client, auth_headers):
    gid = buy_ok(client, auth_headers, CAR)["good"]["id"]
    start = cash(client, auth_headers)
    key = uuid.uuid4().hex
    r1 = client.post(f"{G}/{gid}/maintenance", headers=auth_headers, json={"amount": "850.50", "description": "Troca de freios", "idempotency_key": key})
    r2 = client.post(f"{G}/{gid}/maintenance", headers=auth_headers, json={"amount": "850.50", "description": "Troca de freios", "idempotency_key": key})
    assert r1.status_code == r2.status_code == 201
    assert cash(client, auth_headers) == start - D("850.50")
    d = r1.json()
    assert D(d["expense_total"]) >= D("850.50") and any(e["type"] == "MAINTENANCE" for e in d["events"])
    entry = next(e for e in client.get(f"{B}/entries", headers=auth_headers).json() if e["description"] == "Troca de freios")
    assert entry["capital"] is False and entry["origin"] == "ASSET"
    assert client.post(f"{G}/{gid}/maintenance", headers=auth_headers, json={"amount": "0"}).status_code == 422


def test_vehicle_costs_and_editing_a_cost(client, auth_headers):
    d = buy_ok(client, auth_headers, CAR, usage_km_month=1200)
    gid = d["good"]["id"]
    kinds = {c["kind"] for c in d["costs"]}
    assert {"FUEL", "INSURANCE", "IPVA", "LICENSING", "MAINTENANCE"} <= kinds
    assert d["vehicle_usage_km_month"] == 1200
    fuel = next(c for c in d["costs"] if c["kind"] == "FUEL")
    assert D(fuel["amount"]) == (D(1200) / D(11) * rules.FUEL_PRICE_PER_LITER).quantize(D("0.01"))
    assert next(c for c in d["costs"] if c["kind"] == "IPVA")["frequency"] == "ANNUAL"
    r = client.patch(f"{G}/{gid}/costs/{fuel['id']}", headers=auth_headers, json={"amount": "999.99"})
    assert r.status_code == 200
    r = client.post(f"{G}/{gid}/costs", headers=auth_headers, json={"kind": "PARKING", "amount": "250", "frequency": "MONTHLY"})
    assert r.status_code == 201 and any(c["kind"] == "PARKING" for c in r.json()["costs"])


# ------------------------------------------------------------------ 11/14. valorização e histórico

def test_values_update_on_close_by_category_without_rewriting_history(client, auth_headers, db):
    fund(client, auth_headers)
    car = buy_ok(client, auth_headers, CAR)["good"]["id"]
    house = buy_ok(client, auth_headers, HOUSE)["good"]["id"]
    guitar = buy_ok(client, auth_headers, GUITAR)["good"]["id"]
    start = {i: D(detail(client, auth_headers, i)["good"]["current_value"]) for i in (car, house, guitar)}
    for _ in range(6):
        assert close(client, auth_headers).status_code == 200
    now = {i: D(detail(client, auth_headers, i)["good"]["current_value"]) for i in (car, house, guitar)}
    assert now[car] < start[car] * D("0.96")                                   # carro deprecia
    assert now[house] != start[house] and now[car] != now[guitar]              # regras distintas por categoria
    hist = detail(client, auth_headers, car)["values"]
    assert [v["source"] for v in hist] == ["PURCHASE"] + ["MONTHLY"] * 6 and D(hist[0]["value"]) == start[car]
    assert db.scalar(select(func.count()).select_from(GoodValue).where(GoodValue.good_id == car)) == 7


def test_valuation_is_deterministic_and_rules_are_configurable(client, auth_headers, db):
    rule = rules.DEFAULT_RULES[rules.GoodCategory.CAR]
    from datetime import date
    a = rules.monthly_factor(rule, "good:1", date(2027, 1, 1))
    assert a == rules.monthly_factor(rule, "good:1", date(2027, 1, 1))
    from backend.models import ValuationRule
    db.add(ValuationRule(category="CAR", monthly_drift_pct=D("5"), volatility_pct=D("0"), uncertainty_pct=D("1")))
    db.commit()
    gid = buy_ok(client, auth_headers, CAR)["good"]["id"]
    price = D(detail(client, auth_headers, gid)["good"]["current_value"])
    assert close(client, auth_headers).status_code == 200
    assert D(detail(client, auth_headers, gid)["good"]["current_value"]) == (price * D("1.05")).quantize(D("0.01"))


def test_appraisal_range_reflects_uncertainty(client, auth_headers):
    fund(client, auth_headers)
    cheap = detail(client, auth_headers, buy_ok(client, auth_headers, CAR)["good"]["id"])["appraisal"]
    risky = detail(client, auth_headers, buy_ok(client, auth_headers, "moeda-rara")["good"]["id"])["appraisal"]
    assert D(cheap["low"]) < D(cheap["estimate"]) < D(cheap["high"])
    assert D(risky["uncertainty_pct"]) > D(cheap["uncertainty_pct"])


def test_sold_good_keeps_full_history(client, auth_headers):
    gid = buy_ok(client, auth_headers, CAR)["good"]["id"]
    assert close(client, auth_headers).status_code == 200
    assert client.post(f"{G}/{gid}/sell", headers=auth_headers, json={}).status_code == 200
    d = detail(client, auth_headers, gid)
    assert [e["type"] for e in reversed(d["events"])] == ["PURCHASE", "SALE"]
    assert [v["source"] for v in d["values"]] == ["PURCHASE", "MONTHLY", "SALE"]
    assert len(d["entries"]) >= 3 and d["good"]["status"] == "SOLD"
    assert [g["id"] for g in client.get(f"{G}?status=SOLD", headers=auth_headers).json()] == [gid]
    assert client.get(f"{G}?status=ACTIVE", headers=auth_headers).json() == []
    # bem vendido não gera mais custos nem pode ser vendido/alterado
    assert not any(i["source"] and f"good:{gid}:" in i["source"] for i in overview(client, auth_headers)["month"]["items"])
    assert client.post(f"{G}/{gid}/maintenance", headers=auth_headers, json={"amount": "10"}).status_code == 409


def test_write_off_without_cash_and_not_with_debt(client, auth_headers):
    fund(client, auth_headers)
    g1 = buy_ok(client, auth_headers, GUITAR)["good"]["id"]
    start = cash(client, auth_headers)
    r = client.post(f"{G}/{g1}/write-off", headers=auth_headers, json={"reason": "Roubo"})
    assert r.status_code == 200 and r.json()["good"]["status"] == "LOST" and cash(client, auth_headers) == start
    g2 = buy_ok(client, auth_headers, HOUSE, financed=True, down_payment="150000", term_months=120)["good"]["id"]
    assert client.post(f"{G}/{g2}/write-off", headers=auth_headers, json={}).status_code == 409


# ------------------------------------------------------------------ 15/16. fechamento sem duplicar e consistência

def test_close_does_not_duplicate_asset_effects(client, auth_headers, db, monkeypatch):
    fund(client, auth_headers)
    gid = buy_ok(client, auth_headers, HOUSE, financed=True, down_payment="150000", term_months=120)["good"]["id"]
    client.post(f"{G}/{gid}/occupancy", headers=auth_headers, json={"mode": "LISTED_FOR_RENT", "monthly_rent": "2800"})
    monkeypatch.setattr(rules, "hash01", lambda *a: 0.99)
    assert close(client, auth_headers).status_code == 200
    ref = overview(client, auth_headers)["month"]["ref_month"][:7]
    month = open_month(db)
    goods_service.sync_month(db, month.user_id, month)                         # sincronizar várias vezes não duplica
    goods_service.sync_month(db, month.user_id, month)
    db.commit()
    n_items = len(overview(client, auth_headers)["month"]["items"])
    assert close(client, auth_headers).status_code == 200
    again = client.post(f"{B}/close", headers=auth_headers, json={"ref_month": ref, "confirm": True})
    assert again.status_code == 409
    keys = db.scalars(select(LedgerEntry.idempotency_key).where(LedgerEntry.origin == "ASSET")).all()
    assert len(keys) == len(set(keys)) and n_items >= 4
    assert db.scalar(select(func.count()).select_from(LoanInstallment).where(LoanInstallment.status == "PAID")) == 1


def test_error_during_close_rolls_back_goods_effects(client, auth_headers, db, monkeypatch):
    fund(client, auth_headers)
    gid = buy_ok(client, auth_headers, HOUSE, financed=True, down_payment="150000", term_months=120)["good"]["id"]
    assert close(client, auth_headers).status_code == 200
    start = cash(client, auth_headers)
    before_entries = db.scalar(select(func.count()).select_from(LedgerEntry))
    real = goods_service.advance_to_month

    def boom(*a, **kw):
        raise RuntimeError("falha no meio do fechamento")

    monkeypatch.setattr(goods_service, "advance_to_month", boom)
    with pytest.raises(RuntimeError):
        close(client, auth_headers)
    monkeypatch.setattr(goods_service, "advance_to_month", real)
    db.expire_all()
    assert cash(client, auth_headers) == start
    assert db.scalar(select(func.count()).select_from(LedgerEntry)) == before_entries
    assert detail(client, auth_headers, gid)["loan"]["paid_installments"] == 0
    assert close(client, auth_headers).status_code == 200                      # e depois fecha normalmente
    assert detail(client, auth_headers, gid)["loan"]["paid_installments"] == 1


def test_budget_and_ledger_stay_consistent(client, auth_headers, db, monkeypatch):
    fund(client, auth_headers)
    monkeypatch.setattr(rules, "hash01", lambda *a: 0.99)
    buy_ok(client, auth_headers, CAR)
    gid = buy_ok(client, auth_headers, HOUSE, financed=True, down_payment="150000", term_months=120)["good"]["id"]
    client.post(f"{G}/{gid}/maintenance", headers=auth_headers, json={"amount": "300"})
    for _ in range(3):
        assert close(client, auth_headers).status_code == 200
    # caixa = soma de todas as transações; cada transação orçamentária tem exatamente uma entrada de ledger
    pf = db.scalar(select(Portfolio))
    assert pf.cash_balance == db.scalar(select(func.coalesce(func.sum(Transaction.cash_amount_brl), 0)))
    tx_budget = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.type.in_(["BUDGET_INCOME", "BUDGET_EXPENSE"])))
    assert tx_budget == db.scalar(select(func.count()).select_from(LedgerEntry))
    assert db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.transaction_id.is_(None))) == 0
    # resultado do orçamento não conta compra/amortização (patrimoniais) como despesa
    first = min((m for m in client.get(f"{B}/months", headers=auth_headers).json() if m["status"] == "CLOSED"),
                key=lambda m: m["ref_month"])
    detail1 = client.get(f"{B}/months/{first['ref_month'][:7]}", headers=auth_headers).json()
    assert D(detail1["capital_out"]) > 0
    assert D(first["expense"]) == D(detail1["realized_expense"]) < D(detail1["capital_out"])


def test_wealth_overview_aggregates(client, auth_headers):
    fund(client, auth_headers)
    assert client.get(f"{G}/overview", headers=auth_headers).json()["count"] == 0
    buy_ok(client, auth_headers, CAR)
    gid = buy_ok(client, auth_headers, HOUSE, financed=True, down_payment="150000", term_months=120)["good"]["id"]
    client.post(f"{G}/{gid}/occupancy", headers=auth_headers, json={"mode": "OWNER_OCCUPIED"})
    assert close(client, auth_headers).status_code == 200
    assert close(client, auth_headers).status_code == 200                      # a 1ª parcela vence no mês seguinte à compra
    o = client.get(f"{G}/overview", headers=auth_headers).json()
    assert o["count"] == 2 and D(o["total_value"]) > D(o["total_acquisition_cost"]) * D("0.9")
    assert D(o["debts"]) == D(detail(client, auth_headers, gid)["loan"]["balance"]) and D(o["net_worth"]) == D(o["total_value"]) - D(o["debts"])
    assert D(o["monthly_expense"]) > 0 and D(o["monthly_debt_service"]) > 0
    assert {c["category"] for c in o["by_category"]} == {"CAR", "RESIDENTIAL"}
    assert len(o["series"]) == 3 and D(o["series"][-1]["debts"]) < D(o["series"][0]["debts"])
    assert D(portfolio(client, auth_headers)["goods_net_brl"]) == D(o["net_worth"])


def test_existing_investing_flow_unaffected(client, auth_headers, assets):
    r = client.post("/api/trades/buy", headers=auth_headers, json={"asset_id": assets["PETR4"].id, "quantity": "10"})
    assert r.status_code in (200, 201), r.text
    p = portfolio(client, auth_headers)
    assert D(p["goods_net_brl"]) == 0 and D(p["total_equity_brl"]) == D(p["cash_balance"]) + D(p["market_value_brl"])
    buy_ok(client, auth_headers, CAR)
    assert D(portfolio(client, auth_headers)["market_value_brl"]) == D(p["market_value_brl"])
    perf = client.get("/api/performance?range=7d", headers=auth_headers)
    assert perf.status_code == 200


# ------------------------------------------------------------------ impostos brasileiros e hospedagem de temporada

def _buy_listing(client, h, key, **kw):
    r = client.post(f"{G}/purchase", headers=h, json={"listing_key": key, "idempotency_key": __import__("uuid").uuid4().hex, **kw})
    assert r.status_code == 201, r.text
    return r.json()["good"]["id"]


def test_purchase_pays_brazilian_taxes_by_city(client, auth_headers):
    from tests.conftest import credit
    credit(client, auth_headers, "5000000")
    listings = {x["key"]: x for x in client.get(f"{G}/market", headers=auth_headers).json()}
    sp, gram = listings["apto-sp-studio"], listings["chale-gramado"]
    names = {b["name"]: b for b in sp["fee_breakdown"]}
    assert names["ITBI"]["rate_pct"] == "3.0" and names["Escritura e registro"]["rate_pct"] == "1.0"
    assert D(sp["purchase_fee"]) == D(sp["price"]) * D("0.04")                      # SP: 3% + 1%
    assert D(gram["purchase_fee"]) == D(gram["price"]) * D("0.03")                  # Gramado: 2% + 1%
    car = listings["carro-hatch-novo"]
    assert [b["name"] for b in car["fee_breakdown"]] == ["Transferência e vistoria"]
    gid = _buy_listing(client, auth_headers, "apto-sp-studio")
    d = client.get(f"{G}/{gid}", headers=auth_headers).json()
    iptu = next(c for c in d["costs"] if c["kind"] == "IPTU")
    assert D(iptu["amount"]) == (D(d["good"]["current_value"]) * D("0.010") / 12).quantize(D("0.01"))   # IPTU de SP: 1%/ano


def test_capital_gains_tax_on_sale_and_exemptions(client, auth_headers):
    from tests.conftest import credit
    credit(client, auth_headers, "9000000")
    gid = _buy_listing(client, auth_headers, "apto-rj-3q")
    _buy_listing(client, auth_headers, "casa-poa-4q")                                # dois imóveis: sem isenção de imóvel único
    from backend.database import SessionLocal
    from backend.models import Good
    with SessionLocal() as s:
        g = s.get(Good, gid)
        g.current_value = g.acquisition_cost + D("1000000")                         # valorizou R$ 1 milhão
        s.commit()
    q = client.get(f"{G}/{gid}/sale-quote", headers=auth_headers).json()
    assert D(q["capital_gains_tax"]) == D("150000.00") and "15%" in q["tax_note"]
    assert D(q["fees"]) == D(q["brokerage"]) + D(q["capital_gains_tax"])
    sold = client.post(f"{G}/{gid}/sell", headers=auth_headers, json={}).json()
    tx = client.get(f"{G}/taxes/summary", headers=auth_headers).json()
    kinds = {i["tax"]: D(i["amount"]) for i in tx["items"]}
    assert kinds["IR sobre ganho de capital (venda)"] == D("150000.00") and "ITBI, escritura e transferência (compra)" in kinds
    assert D(tx["total"]) == sum(kinds.values())
    assert D(sold["good"]["sale_result"]) < D("1000000") - D("150000")


def test_sole_residential_property_up_to_440k_is_exempt_and_small_movable_sales_too(client, auth_headers):
    from tests.conftest import credit
    from backend.database import SessionLocal
    from backend.models import Good
    credit(client, auth_headers, "2000000")
    gid = _buy_listing(client, auth_headers, "casa-popular-poa")
    with SessionLocal() as s:
        g = s.get(Good, gid)
        g.current_value = D("430000")
        s.commit()
    assert D(client.get(f"{G}/{gid}/sale-quote", headers=auth_headers).json()["capital_gains_tax"]) == 0
    v = _buy_listing(client, auth_headers, "violao-aco")
    with SessionLocal() as s:
        g = s.get(Good, v)
        g.current_value = g.acquisition_cost + D("3000")
        s.commit()
    assert D(client.get(f"{G}/{v}/sale-quote", headers=auth_headers).json()["capital_gains_tax"]) == 0      # abaixo de R$ 35 mil


def test_catalog_is_much_bigger_and_grouped(client, auth_headers):
    items = client.get(f"{G}/market", headers=auth_headers).json()
    by = {}
    for i in items:
        by.setdefault(i["category"], 0)
        by[i["category"]] += 1
    realty = by.get("RESIDENTIAL", 0) + by.get("COMMERCIAL", 0) + by.get("LAND", 0)
    vehicles = by.get("CAR", 0) + by.get("MOTORCYCLE", 0)
    goods = sum(v for k, v in by.items() if k not in ("RESIDENTIAL", "COMMERCIAL", "LAND", "CAR", "MOTORCYCLE"))
    assert realty >= 25 and vehicles >= 18 and goods >= 25 and len({i["key"] for i in items}) == len(items)


def test_short_stay_earns_more_than_fixed_rent_but_needs_time_or_a_manager(client, auth_headers):
    from tests.conftest import credit
    from tests.test_budget import close, overview
    credit(client, auth_headers, "6000000")
    fixed = _buy_listing(client, auth_headers, "flat-salvador")
    stay = _buy_listing(client, auth_headers, "chale-gramado")
    client.get("/api/life", headers=auth_headers)                                   # cria o perfil de vida (tempo livre)
    # aluguel fixo mensal
    r = client.post(f"{G}/{fixed}/occupancy", headers=auth_headers, json={"mode": "LISTED_FOR_RENT", "monthly_rent": "2400"})
    assert r.status_code == 200, r.text
    # temporada: gestão própria consome horas livres do mês
    free_before = client.get("/api/life", headers=auth_headers).json()["attributes"]["free_hours_left"]
    r = client.post(f"{G}/{stay}/occupancy", headers=auth_headers, json={"mode": "SHORT_STAY", "management": "SELF"})
    assert r.status_code == 200, r.text
    d = r.json()["real_estate"]
    assert d["occupancy"] == "SHORT_STAY" and D(d["nightly_rate"]) == D(d["market_nightly"]) and d["management_hours"] == 14
    assert client.get("/api/life", headers=auth_headers).json()["attributes"]["free_hours_left"] == free_before - 14
    items = {i["source"]: i for i in overview(client, auth_headers)["month"]["items"] if i.get("source")}
    inc = D(items[f"good:{stay}:stay"]["planned_amount"])
    assert inc > 0 and f"good:{stay}:stay_iss" in items and f"good:{stay}:stay_platform" in items and f"good:{stay}:stay_clean" in items
    assert f"good:{stay}:stay_manager" not in items                                  # sem gestor contratado
    # com gestor contratado: sem horas, mas 20% da receita vai para ele
    r = client.post(f"{G}/{stay}/occupancy", headers=auth_headers, json={"mode": "SHORT_STAY", "management": "HIRED", "nightly_rate": r.json()["real_estate"]["nightly_rate"]})
    assert r.status_code == 200 and r.json()["real_estate"]["management_hours"] == 0
    assert client.get("/api/life", headers=auth_headers).json()["attributes"]["free_hours_left"] == free_before
    items = {i["source"]: i for i in overview(client, auth_headers)["month"]["items"] if i.get("source")}
    assert D(items[f"good:{stay}:stay_manager"]["planned_amount"]) == (D(items[f"good:{stay}:stay"]["planned_amount"]) * D("0.2")).quantize(D("0.01"))
    # rende mais que o aluguel fixo, mesmo depois de custos e impostos (e sem vacância de inquilino)
    net_stay = sum(D(items[k]["planned_amount"]) * (1 if items[k]["kind"] == "INCOME" else -1) for k in items if k.startswith(f"good:{stay}:stay") or k == f"good:{stay}:rent_tax")
    assert net_stay > D("2400") * D("0.9"), net_stay
    # o mês seguinte gera nova ocupação (calculada uma vez) e a série fica no detalhe
    assert close(client, auth_headers).status_code == 200
    det = client.get(f"{G}/{stay}", headers=auth_headers).json()["real_estate"]
    assert len(det["stay_months"]) >= 2 and all(m["nights"] >= 0 for m in det["stay_months"])


def test_short_stay_only_for_houses_and_apartments_and_self_management_can_run_out_of_time(client, auth_headers):
    from tests.conftest import credit
    credit(client, auth_headers, "9000000")
    land = _buy_listing(client, auth_headers, "terreno-atibaia")
    assert client.post(f"{G}/{land}/occupancy", headers=auth_headers, json={"mode": "SHORT_STAY"}).status_code in (400, 422)
    shop = _buy_listing(client, auth_headers, "sala-sp-comercial")
    assert client.post(f"{G}/{shop}/occupancy", headers=auth_headers, json={"mode": "SHORT_STAY"}).status_code == 400
    client.put("/api/life/choices", headers=auth_headers, json={"work_level": "INTENSE", "family_time": "HIGH"})        # pouco tempo livre
    ids = [_buy_listing(client, auth_headers, k) for k in ("flat-salvador", "chale-gramado", "casa-praia-flo", "apto-fortaleza-3q")]
    ratings = []
    for i in ids:
        client.post(f"{G}/{i}/occupancy", headers=auth_headers, json={"mode": "SHORT_STAY", "management": "SELF"})
    free = client.get("/api/life", headers=auth_headers).json()["attributes"]
    assert free["free_hours_left"] == 0                                              # 4 × 14h > tempo disponível
    from tests.test_budget import close
    assert close(client, auth_headers).status_code == 200
    d = client.get(f"{G}/{ids[0]}", headers=auth_headers).json()["real_estate"]
    assert "sem tempo" in d["stay_months"][0]["note"] and d["str_rating"] < 70       # na virada do mês a nota cai sem tempo para atender


def test_move_in_stops_paying_rent_and_progressive_rent_tax(client, auth_headers):
    from tests.conftest import credit
    from tests.test_budget import add_recurring, overview
    credit(client, auth_headers, "9000000")
    rent_item = add_recurring(client, auth_headers, "Aluguel", 1800, category="Moradia")
    gid = _buy_listing(client, auth_headers, "apto-bh-2q")
    cand = client.get(f"{G}/housing-candidates", headers=auth_headers).json()
    assert cand and any(c["name"] == "Aluguel" for c in cand)
    r = client.post(f"{G}/{gid}/occupancy", headers=auth_headers, json={"mode": "OWNER_OCCUPIED", "end_recurring_item_ids": [c["id"] for c in cand if c["name"] == "Aluguel"]})
    assert r.status_code == 200 and r.json()["real_estate"]["occupancy"] == "OWNER_OCCUPIED"
    names = [i["name"] for i in overview(client, auth_headers)["month"]["items"]]
    assert "Aluguel" not in names                                                    # parou de pagar aluguel
