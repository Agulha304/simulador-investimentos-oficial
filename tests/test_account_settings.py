"""Configurações da conta: categorias de receitas e despesas valem para todas as partidas."""
from backend.database import SessionLocal
from sqlalchemy import select

from backend.models import BudgetCategory, Game
from tests.test_budget import second_user

A = "/api/account/categories"


def game(client, h, name="P"):
    g = client.post("/api/games", headers=h, json={"kind": "LIFE", "name": name}).json()
    return g, {**h, "X-Game-Id": str(g["id"])}


def world_cats(client, h):
    return {(c["kind"], c["name"]): c["active"] for c in client.get("/api/budget/categories", headers=h).json()}


def test_defaults_listed_and_new_games_inherit_account_choices(client, auth_headers):
    cats = client.get(A, headers=auth_headers).json()
    names = {(c["kind"], c["name"]) for c in cats}
    assert ("EXPENSE", "Lazer") in names and ("INCOME", "Salário") in names and all(c["active"] for c in cats)
    lazer = next(c for c in cats if c["name"] == "Lazer")
    assert client.patch(f"{A}/{lazer['id']}", headers=auth_headers, json={"active": False}).json()["active"] is False
    g, h = game(client, auth_headers)
    assert world_cats(client, h)[("EXPENSE", "Lazer")] is False and world_cats(client, h)[("EXPENSE", "Moradia")] is True


def test_changes_propagate_to_existing_games(client, auth_headers):
    g1, h1 = game(client, auth_headers, "A")
    g2, h2 = game(client, auth_headers, "B")
    cats = client.get(A, headers=auth_headers).json()
    mer = next(c for c in cats if c["name"] == "Alimentação")
    client.patch(f"{A}/{mer['id']}", headers=auth_headers, json={"active": False})
    new = client.post(A, headers=auth_headers, json={"name": "Pets", "kind": "EXPENSE"})
    assert new.status_code == 201
    client.patch(f"{A}/{next(c for c in cats if c['name'] == 'Vestuário')['id']}", headers=auth_headers, json={"name": "Roupas"})
    for h in (h1, h2):
        w = world_cats(client, h)
        assert w[("EXPENSE", "Alimentação")] is False and w[("EXPENSE", "Pets")] is True
        assert ("EXPENSE", "Roupas") in w and ("EXPENSE", "Vestuário") not in w
    assert client.post(A, headers=auth_headers, json={"name": "Pets", "kind": "EXPENSE"}).status_code == 409
    assert client.post(A, headers=auth_headers, json={"name": "x", "kind": "ZZZ"}).status_code == 400


def test_categories_are_read_only_inside_a_game(client, auth_headers):
    g, h = game(client, auth_headers)
    cat = client.get("/api/budget/categories", headers=h).json()[0]
    assert client.patch(f"/api/budget/categories/{cat['id']}", headers=h, json={"active": False}).status_code == 409
    assert client.post("/api/budget/categories", headers=h, json={"name": "Nova", "kind": "EXPENSE"}).status_code == 409
    assert client.get("/api/budget/categories", headers=h).status_code == 200


def test_account_categories_are_private_to_each_account(client, auth_headers):
    other = second_user(client)
    mine = client.get(A, headers=auth_headers).json()
    client.patch(f"{A}/{mine[0]['id']}", headers=auth_headers, json={"active": False})
    assert all(c["active"] for c in client.get(A, headers=other).json())
    assert client.patch(f"{A}/{mine[0]['id']}", headers=other, json={"active": False}).status_code == 404
    assert client.get(A).status_code in (401, 403)
