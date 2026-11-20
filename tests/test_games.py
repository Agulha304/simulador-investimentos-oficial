"""Partidas salvas, mundos isolados, modo treino com mercado histórico e recomendações de aulas."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import Game, User
from backend.services import historical_market
from tests.test_budget import second_user

D = Decimal
GM = "/api/games"


def new_game(client, h, kind="TRAINING", name="Minha partida", **kw):
    r = client.post(GM, headers=h, json={"kind": kind, "name": name, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def gh(h, game):
    return {**h, "X-Game-Id": str(game["id"])}


def cash(client, h):
    return D(client.get("/api/portfolio", headers=h).json()["cash_balance"])


def test_games_are_isolated_worlds_and_listed_with_account(client, auth_headers):
    t = new_game(client, auth_headers, "TRAINING", "Treino 1", start_date="2024-01-01")
    life = new_game(client, auth_headers, "LIFE", "Vida 1")
    lst = client.get(GM, headers=auth_headers).json()
    assert lst["account"]["name"] == "Ana" and {g["name"] for g in lst["games"]} == {"Treino 1", "Vida 1"}
    assert lst["lessons"]["total"] > 0 and len(lst["achievements"]) == 14
    assert t["market_date"] == "2024-01-01" and life["kind"] == "LIFE"
    # cada mundo tem carteira própria; a conta continua com a dela
    client.post("/api/auth/register", json={"email": "z@example.com", "name": "Z", "password": "segredo123"})
    assert cash(client, auth_headers) == D("100000.00")
    assert cash(client, gh(auth_headers, t)) == D("100000.00") and cash(client, gh(auth_headers, life)) == D("100000.00")
    r = client.post(f"{GM}/{t['id']}/training/money", headers=auth_headers, json={"amount": "5000"})
    assert r.status_code == 200
    assert cash(client, gh(auth_headers, t)) == D("105000.00") and cash(client, gh(auth_headers, life)) == D("100000.00")
    assert cash(client, auth_headers) == D("100000.00")
    with SessionLocal() as s:
        w = s.get(User, s.get(Game, t["id"]).world_user_id)
        assert w.is_game_world and w.email.endswith("@partidas.invalid")


def test_other_accounts_cannot_see_or_use_a_game(client, auth_headers):
    g = new_game(client, auth_headers, "TRAINING", start_date="2024-01-01")
    other = second_user(client)
    assert client.get(f"{GM}/{g['id']}", headers=other).status_code == 404
    assert client.get("/api/portfolio", headers={**other, "X-Game-Id": str(g["id"])}).status_code == 404
    assert client.post(f"{GM}/{g['id']}/training/advance", headers=other, json={"months": 1}).status_code == 404
    assert client.get(GM, headers=other).json()["games"] == []
    assert client.get(GM).status_code in (401, 403)


def test_archive_hides_game_and_blocks_its_header(client, auth_headers):
    g = new_game(client, auth_headers, "LIFE")
    assert client.post(f"{GM}/{g['id']}/archive", headers=auth_headers).json()["status"] == "ARCHIVED"
    assert client.get(GM, headers=auth_headers).json()["games"] == []
    assert client.get("/api/portfolio", headers=gh(auth_headers, g)).status_code == 404
    r = client.patch(f"{GM}/{new_game(client, auth_headers, 'LIFE', 'A')['id']}", headers=auth_headers, json={"name": "Renomeada"})
    assert r.json()["name"] == "Renomeada"
    assert client.post(GM, headers=auth_headers, json={"kind": "XYZ", "name": "n"}).status_code == 400
    assert client.post(GM, headers=auth_headers, json={"kind": "LIFE", "name": " "}).status_code in (400, 422)


def test_training_prices_come_from_real_history_of_the_chosen_date(client, auth_headers, assets):
    g = new_game(client, auth_headers, "TRAINING", start_date="2024-01-01")
    h = gh(auth_headers, g)
    jan, _ = historical_market.price_at("PETR4.SA", date(2024, 1, 1))
    feb, prev = historical_market.price_at("PETR4.SA", date(2024, 2, 1))
    assert prev == jan and jan != feb
    q = client.get(f"/api/assets/{assets['PETR4'].id}/quote", headers=h).json()
    assert D(q["price"]) == jan                                                      # não é o preço de hoje (R$ 40)
    r = client.post("/api/trades/buy", headers=h, json={"asset_id": assets["PETR4"].id, "quantity": "100"})
    assert r.status_code == 201, r.text
    assert cash(client, h) == D("100000.00") - jan * 100
    before = D(client.get("/api/portfolio", headers=h).json()["total_equity_brl"])
    adv = client.post(f"{GM}/{g['id']}/training/advance", headers=auth_headers, json={"months": 1})
    assert adv.status_code == 200 and adv.json()["market_date"] == "2024-02-01"
    after = D(client.get("/api/portfolio", headers=h).json()["total_equity_brl"])
    assert after - before == (feb - jan) * 100                                       # a variação real do mês
    # a conta (sem partida) continua vendo preços de hoje
    assert D(client.get(f"/api/assets/{assets['PETR4'].id}/quote", headers=auth_headers).json()["price"]) == D("40")


def test_time_travel_and_limits(client, auth_headers, assets):
    g = new_game(client, auth_headers, "TRAINING", start_date="2024-02-01")
    back = client.post(f"{GM}/{g['id']}/training/date", headers=auth_headers, json={"date": "2023-12-15"})
    assert back.status_code == 200 and back.json()["market_date"] == "2023-12-01"
    assert client.post(f"{GM}/{g['id']}/training/date", headers=auth_headers, json={"date": "2001-01-01"}).status_code == 400
    assert client.post(f"{GM}/{g['id']}/training/date", headers=auth_headers, json={"date": "2999-01-01"}).status_code == 400
    # avançar até o presente é permitido; passar do presente não
    today = date.today()
    client.post(f"{GM}/{g['id']}/training/date", headers=auth_headers, json={"date": today.isoformat()})
    r = client.post(f"{GM}/{g['id']}/training/advance", headers=auth_headers, json={"months": 1})
    assert r.status_code == 409 and "presente" in r.text
    assert client.post(f"{GM}/{g['id']}/training/advance", headers=auth_headers, json={"months": 99}).status_code == 422


def test_asset_that_did_not_exist_yet_is_unavailable(client, auth_headers, assets):
    g = new_game(client, auth_headers, "TRAINING", start_date="2020-01-01")
    r = client.get(f"/api/assets/{assets['PETR4'].id}/quote", headers=gh(auth_headers, g))
    assert r.status_code in (502, 503, 404), r.text


def test_training_only_actions_refuse_life_games(client, auth_headers):
    g = new_game(client, auth_headers, "LIFE")
    assert client.post(f"{GM}/{g['id']}/training/advance", headers=auth_headers, json={"months": 1}).status_code == 409
    assert client.post(f"{GM}/{g['id']}/training/money", headers=auth_headers, json={"amount": "10"}).status_code == 409


def test_life_game_runs_the_whole_simulator_inside_its_world(client, auth_headers):
    g = new_game(client, auth_headers, "LIFE", "Minha vida")
    h = gh(auth_headers, g)
    r = client.post("/api/game/start", headers=h, json={"mode": "CAREER", "scenario": "young_pro", "seed": 3})
    assert r.status_code == 200, r.text
    ov = client.get("/api/progress/overview", headers=h).json()
    assert ov["scenario"] == "young_pro"
    # a conta e outra partida não foram tocadas
    other = new_game(client, auth_headers, "LIFE", "Outra")
    assert client.get("/api/progress/overview", headers=gh(auth_headers, other)).json()["scenario"] is None
    assert client.get("/api/progress/overview", headers=auth_headers).json()["mode"] == "FREE"
    lst = {x["name"]: x for x in client.get(GM, headers=auth_headers).json()["games"]}
    assert lst["Minha vida"]["scenario"] == "young_pro" and lst["Minha vida"]["started"] is True


def test_ranking_counts_game_worlds_for_their_owner(client, auth_headers, assets):
    t = new_game(client, auth_headers, "TRAINING", start_date="2024-01-01")
    v = new_game(client, auth_headers, "LIFE", "V")
    assert client.post("/api/game/start", headers=gh(auth_headers, v), json={"mode": "RANKED", "seed": 1}).status_code == 200      # só o modo ranqueado entra no ranking de patrimônio
    for board in ("return", "wealth"):
        j = client.get(f"/api/ranking?board={board}&period=all", headers=auth_headers).json()
        assert j["participants"] == 1 and j["entries"][0]["is_me"] is True, (board, j)


def test_performance_recommends_lessons_for_what_the_player_is_doing_wrong(client, auth_headers, assets):
    g = new_game(client, auth_headers, "TRAINING", start_date="2024-01-01")
    h = gh(auth_headers, g)
    j = client.get("/api/performance?range=all", headers=h).json()
    ids = [x["lesson_id"] for x in j["recommended_lessons"]]
    assert "m1-l4" in ids and all(x["reason"] and x["title"] for x in j["recommended_lessons"])
    r_btc = client.post("/api/trades/buy", headers=h, json={"asset_id": assets["BTC"].id, "quantity": "0.05"})
    assert r_btc.status_code == 201
    j = client.get("/api/performance?range=all", headers=h).json()
    ids = [x["lesson_id"] for x in j["recommended_lessons"]]
    assert "m5-l2" in ids and "m7-l1" in ids and "m1-l4" not in ids
