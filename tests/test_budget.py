"""Orçamento mensal, ledger de movimentações e ciclo mensal (etapa 1 do simulador de vida financeira)."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.core.dates import today_br
from backend.models import LedgerEntry, Portfolio, SimMonth, Transaction
from backend.services import budget_service as bs
from backend.services import finance_ledger

D = Decimal
B = "/api/budget"


def cash(client, h) -> Decimal:
    return D(client.get("/api/portfolio", headers=h).json()["cash_balance"])


def overview(client, h):
    r = client.get(f"{B}/overview", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def cat_id(client, h, name, kind="EXPENSE"):
    cats = client.get(f"{B}/categories", headers=h).json()
    return next(c["id"] for c in cats if c["name"] == name and c["kind"] == kind)


def add_recurring(client, h, name, amount, category="Moradia", kind="EXPENSE", **kw):
    r = client.post(f"{B}/items", headers=h, json={
        "name": name, "kind": kind, "category_id": cat_id(client, h, category, kind),
        "planned_amount": str(amount), "recurring": True, **kw})
    assert r.status_code == 201, r.text
    return next(i for i in r.json()["items"] if i["name"] == name)


def post_entry(client, h, kind, amount, category, **kw):
    r = client.post(f"{B}/entries", headers=h, json={
        "kind": kind, "amount": str(amount), "category_id": cat_id(client, h, category, kind), **kw})
    assert r.status_code == 201, r.text
    return r.json()


def close(client, h, ref=None):
    ref = ref or overview(client, h)["month"]["ref_month"][:7]
    return client.post(f"{B}/close", headers=h, json={"ref_month": ref, "confirm": True})


def second_user(client):
    r = client.post("/api/auth/register", json={"email": "bia@example.com", "name": "Bia", "password": "segredo123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ------------------------------------------------------------------ 1. criação do orçamento

def test_first_access_creates_open_month_categories_and_account(client, auth_headers):
    o = overview(client, auth_headers)
    assert o["month"]["status"] == "OPEN"
    assert o["month"]["ref_month"] == today_br().replace(day=1).isoformat()
    assert D(o["account"]["balance"]) == cash(client, auth_headers) == D(o["month"]["opening_balance"])
    cats = client.get(f"{B}/categories", headers=auth_headers).json()
    assert {"Moradia", "Alimentação", "Dívidas", "Outros"} <= {c["name"] for c in cats if c["kind"] == "EXPENSE"}
    assert {"Salário", "Renda extra", "Aluguéis recebidos"} <= {c["name"] for c in cats if c["kind"] == "INCOME"}
    assert overview(client, auth_headers)["month"]["items"] == []        # nada fictício: começa vazio


def test_categories_are_editable_and_unique(client, auth_headers):
    r = client.post(f"{B}/categories", headers=auth_headers, json={"name": "Pets", "kind": "EXPENSE"})
    assert r.status_code == 201
    assert client.post(f"{B}/categories", headers=auth_headers, json={"name": "Pets", "kind": "EXPENSE"}).status_code == 409
    r = client.patch(f"{B}/categories/{r.json()['id']}", headers=auth_headers, json={"name": "Animais", "active": False})
    assert r.json()["name"] == "Animais" and r.json()["active"] is False


def test_example_template_is_optional_and_editable(client, auth_headers):
    r = client.post(f"{B}/example", headers=auth_headers)
    assert r.status_code == 201
    assert {i["name"] for i in r.json()["items"]} >= {"Aluguel", "Supermercado"}
    assert client.post(f"{B}/example", headers=auth_headers).status_code == 409


# ------------------------------------------------------------------ planejado ≠ realizado

def test_planned_amount_does_not_touch_balance(client, auth_headers):
    before = cash(client, auth_headers)
    item = add_recurring(client, auth_headers, "Alimentação mensal", "500.00", category="Alimentação")
    assert cash(client, auth_headers) == before
    assert D(item["realized"]) == 0 and D(item["remaining"]) == D("500.00")
    m = overview(client, auth_headers)["month"]
    assert D(m["planned_expense"]) == D("500.00") and D(m["realized_expense"]) == 0


# ------------------------------------------------------------------ 4/5/6. receitas, despesas, saldo

def test_register_income_and_expense_updates_balance_and_remaining(client, auth_headers):
    start = cash(client, auth_headers)
    food = add_recurring(client, auth_headers, "Alimentação", "500.00", category="Alimentação")
    post_entry(client, auth_headers, "INCOME", "3000.00", "Salário")
    post_entry(client, auth_headers, "EXPENSE", "200.00", "Alimentação", budget_item_id=food["id"])
    assert cash(client, auth_headers) == start + D("2800.00")
    m = overview(client, auth_headers)["month"]
    assert D(m["realized_income"]) == D("3000.00") and D(m["realized_expense"]) == D("200.00")
    item = next(i for i in m["items"] if i["id"] == food["id"])
    assert D(item["realized"]) == D("200.00") and D(item["remaining"]) == D("300.00")
    assert D(m["result"]) == D("2800.00")


def test_expense_over_balance_is_rejected(client, auth_headers):
    r = client.post(f"{B}/entries", headers=auth_headers, json={
        "kind": "EXPENSE", "amount": "99999999.00", "category_id": cat_id(client, auth_headers, "Outros")})
    assert r.status_code == 422
    assert client.get(f"{B}/entries", headers=auth_headers).json() == []


def test_entry_idempotency_key_replays_without_double_charge(client, auth_headers):
    start = cash(client, auth_headers)
    key = uuid.uuid4().hex
    a = post_entry(client, auth_headers, "EXPENSE", "100.00", "Lazer", idempotency_key=key)
    b = post_entry(client, auth_headers, "EXPENSE", "100.00", "Lazer", idempotency_key=key)
    assert a["id"] == b["id"]
    assert cash(client, auth_headers) == start - D("100.00")


def test_entry_must_be_in_open_month_and_validates_input(client, auth_headers):
    bad = client.post(f"{B}/entries", headers=auth_headers, json={
        "kind": "EXPENSE", "amount": "10", "category_id": cat_id(client, auth_headers, "Lazer"),
        "entry_date": "2001-01-10"})
    assert bad.status_code == 400
    wrong_kind = client.post(f"{B}/entries", headers=auth_headers, json={
        "kind": "INCOME", "amount": "10", "category_id": cat_id(client, auth_headers, "Lazer")})
    assert wrong_kind.status_code == 400
    assert client.post(f"{B}/entries", headers=auth_headers, json={
        "kind": "EXPENSE", "amount": "0", "category_id": cat_id(client, auth_headers, "Lazer")}).status_code == 422


def test_reversal_corrects_without_deleting_history(client, auth_headers):
    start = cash(client, auth_headers)
    e = post_entry(client, auth_headers, "EXPENSE", "80.00", "Lazer")
    r = client.post(f"{B}/entries/{e['id']}/reverse", headers=auth_headers)
    assert r.status_code == 201 and r.json()["origin"] == "REVERSAL" and r.json()["reverses_id"] == e["id"]
    assert cash(client, auth_headers) == start
    entries = client.get(f"{B}/entries", headers=auth_headers).json()
    assert len(entries) == 2 and next(x for x in entries if x["id"] == e["id"])["reversed"] is True
    assert D(overview(client, auth_headers)["month"]["realized_expense"]) == 0
    assert client.post(f"{B}/entries/{e['id']}/reverse", headers=auth_headers).status_code == 409
    assert client.post(f"{B}/entries/{r.json()['id']}/reverse", headers=auth_headers).status_code == 409


def test_ledger_entries_link_to_cash_transactions(client, auth_headers, db):
    post_entry(client, auth_headers, "INCOME", "1000.00", "Renda extra")
    e = db.scalar(select(LedgerEntry))
    tx = db.get(Transaction, e.transaction_id)
    assert tx.type.value == "BUDGET_INCOME" and tx.cash_amount_brl == D("1000.00")
    assert e.dest_account_id is not None and e.source_account_id is None


# ------------------------------------------------------------------ 2/3. recorrência e histórico

def test_changing_recurring_value_preserves_past_months(client, auth_headers):
    rent = add_recurring(client, auth_headers, "Aluguel", "1500.00")
    month1 = overview(client, auth_headers)["month"]["ref_month"]
    assert close(client, auth_headers).status_code == 200

    o2 = overview(client, auth_headers)
    rent2 = next(i for i in o2["month"]["items"] if i["name"] == "Aluguel")
    assert D(rent2["planned_amount"]) == D("1500.00")                       # herdou o valor vigente
    r = client.patch(f"{B}/items/{rent2['id']}", headers=auth_headers, json={"planned_amount": "2000.00"})
    assert r.status_code == 200
    assert close(client, auth_headers).status_code == 200

    # mês 1 permanece com R$ 1.500; mês 2 cobrou R$ 2.000; mês 3 já nasce com R$ 2.000
    m1 = client.get(f"{B}/months/{month1[:7]}", headers=auth_headers).json()
    assert D(m1["realized_expense"]) == D("1500.00")
    assert D(next(i for i in m1["items"] if i["name"] == "Aluguel")["planned_amount"]) == D("1500.00")
    m2 = client.get(f"{B}/months/{o2['month']['ref_month'][:7]}", headers=auth_headers).json()
    assert D(m2["realized_expense"]) == D("2000.00")
    o3 = overview(client, auth_headers)
    assert D(next(i for i in o3["month"]["items"] if i["name"] == "Aluguel")["planned_amount"]) == D("2000.00")
    assert rent["recurring"] is True


def test_change_only_this_month_does_not_alter_future(client, auth_headers):
    add_recurring(client, auth_headers, "Internet", "100.00", category="Comunicação")
    item = overview(client, auth_headers)["month"]["items"][0]
    client.patch(f"{B}/items/{item['id']}", headers=auth_headers, json={"planned_amount": "250.00", "apply_to_future": False})
    assert close(client, auth_headers).status_code == 200
    nxt = overview(client, auth_headers)["month"]["items"][0]
    assert D(nxt["planned_amount"]) == D("100.00")


def test_frequency_quarterly_only_appears_every_three_months(client, auth_headers):
    add_recurring(client, auth_headers, "Seguro", "300.00", category="Outros", frequency="QUARTERLY")
    seen = []
    for _ in range(4):
        seen.append(any(i["name"] == "Seguro" for i in overview(client, auth_headers)["month"]["items"]))
        assert close(client, auth_headers).status_code == 200
    assert seen == [True, False, False, True]


def test_remove_future_expense_stops_recurrence(client, auth_headers):
    item = add_recurring(client, auth_headers, "Streaming", "50.00", category="Lazer")
    r = client.delete(f"{B}/items/{item['id']}", headers=auth_headers)
    assert r.status_code == 200 and r.json()["items"] == []
    assert close(client, auth_headers).status_code == 200
    assert overview(client, auth_headers)["month"]["items"] == []


def test_cannot_remove_item_with_entries(client, auth_headers):
    item = add_recurring(client, auth_headers, "Mercado", "400.00", category="Alimentação")
    post_entry(client, auth_headers, "EXPENSE", "100.00", "Alimentação", budget_item_id=item["id"])
    assert client.delete(f"{B}/items/{item['id']}", headers=auth_headers).status_code == 409


def test_recurring_end_month_stops_items(client, auth_headers):
    this_month = today_br().replace(day=1)
    add_recurring(client, auth_headers, "Parcela", "100.00", category="Dívidas", end_month=f"{this_month:%Y-%m}")
    assert close(client, auth_headers).status_code == 200
    assert overview(client, auth_headers)["month"]["items"] == []


# ------------------------------------------------------------------ 7/8/9. fechamento

def test_close_month_charges_recurring_creates_next_and_carries_balance(client, auth_headers):
    add_recurring(client, auth_headers, "Salário", "5000.00", category="Salário", kind="INCOME")
    add_recurring(client, auth_headers, "Aluguel", "1500.00")
    start = cash(client, auth_headers)
    prev = overview(client, auth_headers)
    assert D(prev["close"]["carried_balance"]) == start + D("3500.00")
    assert prev["close"]["can_close"] and set(prev["close"]["pending"]) == {"Salário", "Aluguel"}

    r = close(client, auth_headers)
    assert r.status_code == 200
    nxt = r.json()["month"]
    assert nxt["status"] == "OPEN"
    assert nxt["ref_month"] == bs.shift_month(today_br().replace(day=1), 1).isoformat()
    assert cash(client, auth_headers) == start + D("3500.00")
    assert D(nxt["opening_balance"]) == start + D("3500.00")
    assert {i["name"] for i in nxt["items"]} == {"Salário", "Aluguel"}
    assert all(D(i["realized"]) == 0 for i in nxt["items"])                # novo mês: nada cobrado ainda

    months = client.get(f"{B}/months", headers=auth_headers).json()
    closed = next(m for m in months if m["status"] == "CLOSED")
    assert D(closed["income"]) == D("5000.00") and D(closed["expense"]) == D("1500.00")
    assert D(closed["closing_balance"]) == start + D("3500.00") and D(closed["opening_balance"]) == start


def test_close_requires_confirmation(client, auth_headers):
    ref = overview(client, auth_headers)["month"]["ref_month"][:7]
    r = client.post(f"{B}/close", headers=auth_headers, json={"ref_month": ref, "confirm": False})
    assert r.status_code == 400
    assert overview(client, auth_headers)["month"]["status"] == "OPEN"


def test_manually_paid_recurring_is_not_charged_again_on_close(client, auth_headers):
    rent = add_recurring(client, auth_headers, "Aluguel", "1500.00")
    start = cash(client, auth_headers)
    post_entry(client, auth_headers, "EXPENSE", "1500.00", "Moradia", budget_item_id=rent["id"])
    assert close(client, auth_headers).status_code == 200
    assert cash(client, auth_headers) == start - D("1500.00")


# ------------------------------------------------------------------ 10/11. duplicidade

def test_closing_twice_is_rejected_without_new_charges(client, auth_headers):
    add_recurring(client, auth_headers, "Aluguel", "1500.00")
    ref = overview(client, auth_headers)["month"]["ref_month"][:7]
    assert close(client, auth_headers, ref).status_code == 200
    after_first = cash(client, auth_headers)
    again = close(client, auth_headers, ref)
    assert again.status_code == 409
    assert cash(client, auth_headers) == after_first


def test_recurring_unique_per_month_in_database(client, auth_headers, db):
    add_recurring(client, auth_headers, "Aluguel", "1500.00")
    assert close(client, auth_headers).status_code == 200
    entry = db.scalar(select(LedgerEntry).where(LedgerEntry.origin == "RECURRING"))
    month = db.get(SimMonth, db.scalar(select(SimMonth.id).where(SimMonth.status == "CLOSED")))
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):                                   # mesmo item + mesmo mês, chave diferente
        finance_ledger.post_entry(
            db, entry.user_id, kind=entry.kind, amount=entry.amount, description="duplicada",
            ref_month=month.ref_month, entry_date=month.ref_month, origin=entry.origin,
            recurring_item_id=entry.recurring_item_id, idempotency_key="outra-chave")
    db.rollback()
    assert db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.origin == "RECURRING")) == 1


def test_concurrent_style_replay_charges_once(client, auth_headers):
    add_recurring(client, auth_headers, "Aluguel", "1500.00")
    start = cash(client, auth_headers)
    ref = overview(client, auth_headers)["month"]["ref_month"][:7]
    codes = [close(client, auth_headers, ref).status_code for _ in range(3)]
    assert codes == [200, 409, 409]
    assert cash(client, auth_headers) == start - D("1500.00")


# ------------------------------------------------------------------ 12. atomicidade

def test_error_during_close_leaves_nothing_applied(client, auth_headers, db, monkeypatch):
    add_recurring(client, auth_headers, "Salário", "5000.00", category="Salário", kind="INCOME")
    add_recurring(client, auth_headers, "Aluguel", "1500.00")
    start = cash(client, auth_headers)
    real = finance_ledger.post_entry
    calls = {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("falha simulada no meio do fechamento")
        return real(*a, **kw)

    monkeypatch.setattr(finance_ledger, "post_entry", flaky)
    with pytest.raises(RuntimeError):
        close(client, auth_headers)
    monkeypatch.undo()

    db.expire_all()
    assert cash(client, auth_headers) == start
    assert db.scalar(select(func.count()).select_from(LedgerEntry)) == 0
    assert db.scalar(select(func.count()).select_from(SimMonth)) == 1
    assert overview(client, auth_headers)["month"]["status"] == "OPEN"
    assert close(client, auth_headers).status_code == 200                   # e depois fecha normalmente


def test_insufficient_funds_blocks_close_and_changes_nothing(client, auth_headers):
    add_recurring(client, auth_headers, "Mansão", "99999999.00")
    start = cash(client, auth_headers)
    o = overview(client, auth_headers)
    assert o["close"]["can_close"] is False and D(o["close"]["shortfall"]) > 0
    assert close(client, auth_headers).status_code == 422
    assert cash(client, auth_headers) == start
    assert overview(client, auth_headers)["month"]["status"] == "OPEN"


# ------------------------------------------------------------------ investimentos, patrimônio e sumário

def test_planned_investment_and_free_balance(client, auth_headers):
    add_recurring(client, auth_headers, "Aluguel", "1000.00")
    r = client.patch(f"{B}/months/current", headers=auth_headers, json={"planned_investment": "500.00"})
    assert r.status_code == 200
    m = r.json()
    assert D(m["planned_investment"]) == D("500.00")
    assert D(m["free_after_investment"]) == D(m["projected_closing_balance"]) - D("500.00")


def test_close_summary_reports_investments_made_in_the_month(client, auth_headers, assets):
    overview(client, auth_headers)                      # abre o mês antes da compra (compras anteriores não contam)
    r = client.post("/api/trades/buy", headers=auth_headers, json={"asset_id": assets["PETR4"].id, "quantity": "10"})
    assert r.status_code in (200, 201), r.text
    o = overview(client, auth_headers)
    assert D(o["month"]["invested"]) > 0 and D(o["close"]["invested"]) == D(o["month"]["invested"])
    assert close(client, auth_headers).status_code == 200
    closed = next(m for m in client.get(f"{B}/months", headers=auth_headers).json() if m["status"] == "CLOSED")
    assert D(closed["invested"]) > 0


def test_budget_income_counts_as_wealth_and_investing_still_works(client, auth_headers, assets):
    before = client.get("/api/portfolio", headers=auth_headers).json()
    post_entry(client, auth_headers, "INCOME", "1000.00", "Salário")
    after = client.get("/api/portfolio", headers=auth_headers).json()
    assert D(after["total_equity_brl"]) == D(before["total_equity_brl"]) + D("1000.00")
    assert D(after["pnl_brl"]) == D(before["pnl_brl"]) + D("1000.00")      # decisão: receitas contam como patrimônio
    assert D(after["total_deposits_brl"]) == D(before["total_deposits_brl"])
    r = client.post("/api/trades/buy", headers=auth_headers, json={"asset_id": assets["PETR4"].id, "quantity": "5"})
    assert r.status_code in (200, 201), r.text
    sell = client.post("/api/trades/sell", headers=auth_headers, json={"asset_id": assets["PETR4"].id, "quantity": "5"})
    assert sell.status_code in (200, 201), sell.text


# ------------------------------------------------------------------ 13. isolamento e permissões

def test_endpoints_require_authentication(client):
    for method, path in [("get", "/overview"), ("get", "/months"), ("get", "/categories"), ("get", "/entries"),
                         ("post", "/close"), ("post", "/entries"), ("post", "/items"), ("post", "/example")]:
        assert getattr(client, method)(f"{B}{path}").status_code == 401, path


def test_users_cannot_see_or_change_each_others_data(client, auth_headers):
    item = add_recurring(client, auth_headers, "Aluguel", "1500.00")
    entry = post_entry(client, auth_headers, "EXPENSE", "50.00", "Lazer")
    bia = second_user(client)

    assert overview(client, bia)["month"]["items"] == []
    assert client.get(f"{B}/entries", headers=bia).json() == []
    assert client.patch(f"{B}/items/{item['id']}", headers=bia, json={"planned_amount": "1.00"}).status_code == 404
    assert client.delete(f"{B}/items/{item['id']}", headers=bia).status_code == 404
    assert client.post(f"{B}/entries/{entry['id']}/reverse", headers=bia).status_code == 404
    other_cat = cat_id(client, auth_headers, "Lazer")
    r = client.post(f"{B}/entries", headers=bia, json={"kind": "EXPENSE", "amount": "5", "category_id": other_cat})
    assert r.status_code == 404
    assert client.post(f"{B}/items", headers=bia, json={
        "name": "x", "kind": "EXPENSE", "category_id": other_cat, "planned_amount": "5"}).status_code == 404
    # fechar o mês de um não afeta o outro
    assert close(client, bia).status_code == 200
    assert overview(client, auth_headers)["month"]["status"] == "OPEN"
    own = client.get(f"{B}/months", headers=auth_headers).json()
    assert len(own) == 1 and own[0]["status"] == "OPEN"


def test_existing_user_without_budget_gets_set_up_lazily(client, auth_headers, db):
    assert db.scalar(select(func.count()).select_from(SimMonth)) == 0          # usuários antigos: nada migrado à força
    o = overview(client, auth_headers)
    assert D(o["month"]["opening_balance"]) == db.scalar(select(Portfolio.cash_balance))
