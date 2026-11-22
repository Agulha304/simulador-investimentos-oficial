"""Patrimônio no menu de vidas (GET /api/games): sempre o REAL e atual, não a última foto."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import Game, PortfolioSnapshot
from backend.models import Portfolio
from backend.services import historical_market, ledger_service, portfolio_service
from backend.models import TransactionSource
from tests.test_budget import second_user
from tests.test_games import GM, gh, new_game

D = Decimal


def _listed(client, h, gid):
    return next(g for g in client.get(GM, headers=h).json()["games"] if g["id"] == gid)


def _panel(client, h, game):
    return D(client.get("/api/portfolio", headers=gh(h, game)).json()["total_equity_brl"])


def _silent_deposit(game_id, amount):
    """Mexe no saldo SEM tirar foto (simula vida criada, jogada e abandonada sem snapshot posterior)."""
    with SessionLocal() as s:
        g = s.get(Game, game_id)
        pid = s.scalar(select(Portfolio.id).where(Portfolio.user_id == g.world_user_id))
        ledger_service.deposit(s, pid, D(amount), source=TransactionSource.SYSTEM, idempotency_key=f"t:{game_id}:{amount}", note="t")
        s.commit()


def test_abandoned_life_shows_real_equity_not_snapshot(client, auth_headers):
    life = new_game(client, auth_headers, "LIFE", "Vida")
    assert D(life["equity_brl"]) == D("100000.00")
    _silent_deposit(life["id"], "7000")
    with SessionLocal() as s:                      # a última foto continua no valor inicial
        assert {str(x.equity_brl) for x in s.scalars(select(PortfolioSnapshot))} == {"100000.00"}
    g = _listed(client, auth_headers, life["id"])
    assert D(g["equity_brl"]) == D("107000.00")
    assert D(g["equity_brl"]) == _panel(client, auth_headers, life)        # mesma fonte do painel dentro da partida


def test_equity_after_purchase_matches_panel(client, auth_headers, assets):
    life = new_game(client, auth_headers, "LIFE", "Vida")
    r = client.post("/api/trades/buy", headers=gh(auth_headers, life), json={"asset_id": assets["PETR4"].id, "quantity": "100"})
    assert r.status_code in (200, 201), r.text
    g = _listed(client, auth_headers, life["id"])
    assert D(g["equity_brl"]) == _panel(client, auth_headers, life)


def test_training_equity_uses_prices_of_the_game_date(client, auth_headers, assets):
    g = new_game(client, auth_headers, "TRAINING", start_date="2024-01-01")
    h = gh(auth_headers, g)
    assert client.post("/api/trades/buy", headers=h, json={"asset_id": assets["PETR4"].id, "quantity": "100"}).status_code in (200, 201)
    jan, _ = historical_market.price_at("PETR4.SA", date(2024, 1, 1))
    assert jan != D("40")
    listed = _listed(client, auth_headers, g["id"])
    cash = D(client.get("/api/portfolio", headers=h).json()["cash_balance"])
    assert D(listed["equity_brl"]) == cash + (100 * jan).quantize(D("0.01"))
    assert D(listed["equity_brl"]) == _panel(client, auth_headers, g)
    # avançar a data muda o preço histórico e, com ele, o patrimônio listado
    assert client.post(f"{GM}/{g['id']}/training/date", headers=auth_headers, json={"date": "2024-06-01"}).status_code == 200
    assert D(_listed(client, auth_headers, g["id"])["equity_brl"]) == _panel(client, auth_headers, g)


def test_failure_falls_back_to_last_snapshot(client, auth_headers, monkeypatch):
    life = new_game(client, auth_headers, "LIFE", "Vida")
    t = new_game(client, auth_headers, "TRAINING", "Treino", start_date="2024-01-01")
    _silent_deposit(life["id"], "7000")

    def boom(*a, **k):
        raise RuntimeError("falha de cotação")
    monkeypatch.setattr(portfolio_service, "build_summary", boom)
    r = client.get(GM, headers=auth_headers)
    assert r.status_code == 200
    assert {g["id"]: g["equity_brl"] for g in r.json()["games"]} == {life["id"]: "100000.00", t["id"]: "100000.00"}


def test_equity_is_isolated_between_users(client, auth_headers):
    mine = new_game(client, auth_headers, "LIFE", "Minha")
    other = second_user(client)
    theirs = new_game(client, other, "LIFE", "Dela")
    _silent_deposit(mine["id"], "1000")
    _silent_deposit(theirs["id"], "50000")
    assert {g["id"]: D(g["equity_brl"]) for g in client.get(GM, headers=auth_headers).json()["games"]} == {mine["id"]: D("101000.00")}
    assert {g["id"]: D(g["equity_brl"]) for g in client.get(GM, headers=other).json()["games"]} == {theirs["id"]: D("150000.00")}
