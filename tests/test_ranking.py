from tests.conftest import credit
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update

from backend.models import Portfolio, PortfolioSnapshot, User
from backend.services import performance_service, portfolio_service, ranking_service

D = Decimal


def make_user(client, db, name, email, wealth):
    """Cria o usuário e fixa o patrimônio da foto atual (o resto continua vindo do cadastro)."""
    r = client.post("/api/auth/register", json={"email": email, "name": name, "password": "segredo123"})
    assert r.status_code == 201, r.text
    user = db.scalar(select(User).where(User.email == email))
    pid = db.scalar(select(Portfolio.id).where(Portfolio.user_id == user.id))
    db.execute(update(PortfolioSnapshot).where(PortfolioSnapshot.portfolio_id == pid)
               .values(wealth_brl=D(wealth), equity_brl=D(wealth)))
    db.commit()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, user, pid


def board(client, h, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/api/ranking?{q}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_registration_creates_the_first_snapshot(client, auth_headers, db):
    s = db.scalar(select(PortfolioSnapshot))
    assert s.equity_brl == s.wealth_brl == s.initial_brl == s.net_deposits_brl == D("100000.00")


def test_wealth_board_orders_by_wealth_and_hides_identifiers(client, db):
    ha, _, _ = make_user(client, db, "Ana Souza", "a@example.com", "120000")
    hb, _, _ = make_user(client, db, "Bruno Lima Neto", "b@example.com", "80000")
    hc, _, _ = make_user(client, db, "Carla", "c@example.com", "100000")
    r = board(client, hb, board="wealth")
    assert [(e["rank"], e["nickname"]) for e in r["entries"]] == [(1, "Ana S."), (2, "Carla"), (3, "Bruno N.")]
    assert r["participants"] == 3 and r["me"]["rank"] == 3 and r["me"]["is_me"] and r["me_hidden"] is False
    assert [e["is_me"] for e in r["entries"]] == [False, False, True]
    assert D(r["entries"][0]["wealth_brl"]) == 120000 and D(r["entries"][0]["gain_brl"]) == 20000
    assert "@" not in str(r) and "email" not in str(r) and "user_id" not in str(r)
    assert "Aportes virtuais extras não contam" in r["note"]


def test_return_board_and_ties(client, db):
    ha, _, _ = make_user(client, db, "Ana", "a@example.com", "120000")
    hb, _, _ = make_user(client, db, "Bruno", "b@example.com", "80000")
    r = board(client, ha, board="return")
    assert [(e["nickname"], D(e["return_pct"])) for e in r["entries"]] == [("Ana", D("20.00")), ("Bruno", D("-20.00"))]
    hc, _, _ = make_user(client, db, "Caio", "c@example.com", "120000")
    wealth = board(client, ha, board="wealth")["entries"]
    assert [e["nickname"] for e in wealth[:2]] == ["Ana", "Caio"]                # empate: quem entrou primeiro


def test_extra_virtual_deposits_do_not_climb_the_ranking(client, db):
    ha, ua, pa = make_user(client, db, "Ana", "a@example.com", "100000")
    hb, _, _ = make_user(client, db, "Bruno", "b@example.com", "100500")
    credit(client, ha, "5000000")
    performance_service.take_snapshot(db, portfolio_service.load_portfolio(db, pa))       # foto nova, mesmo horário
    snap = db.scalar(select(PortfolioSnapshot).where(PortfolioSnapshot.portfolio_id == pa))
    db.refresh(snap)
    assert snap.equity_brl == D("5100000.00") and snap.wealth_brl == D("100000.00") and snap.net_deposits_brl == D("5100000.00")
    r = board(client, ha, board="wealth")
    assert r["entries"][0]["nickname"] == "Bruno" and D(r["me"]["wealth_brl"]) == D("100000.00")
    assert D(board(client, ha, board="return")["me"]["return_pct"]) == D("0.00")


def test_privacy_toggle_and_nickname(client, db):
    ha, _, _ = make_user(client, db, "Ana Souza", "a@example.com", "120000")
    hb, _, _ = make_user(client, db, "Bruno", "b@example.com", "80000")
    assert client.get("/api/ranking/settings", headers=ha).json() == {
        "show_in_ranking": True, "nickname": None, "default_nickname": "Ana S."}
    assert client.put("/api/ranking/settings", headers=ha, json={"show_in_ranking": True, "nickname": "A"}).status_code == 422
    assert client.put("/api/ranking/settings", headers=ha, json={"show_in_ranking": True, "nickname": "x" * 25}).status_code == 422
    r = client.put("/api/ranking/settings", headers=ha, json={"show_in_ranking": True, "nickname": "  Rainha dos FIIs "})
    assert r.json()["nickname"] == "Rainha dos FIIs"
    assert board(client, hb, board="wealth")["entries"][0]["nickname"] == "Rainha dos FIIs"

    client.put("/api/ranking/settings", headers=ha, json={"show_in_ranking": False})            # some do ranking
    hidden = board(client, ha, board="wealth")
    assert hidden["me"] is None and hidden["me_hidden"] is True and hidden["participants"] == 1
    assert [e["nickname"] for e in board(client, hb, board="wealth")["entries"]] == ["Bruno"]
    assert client.get("/api/ranking/settings", headers=ha).json()["nickname"] is None             # apelido vazio volta ao padrão


def test_default_nickname_rules():
    assert ranking_service.default_nickname("Ana") == "Ana"
    assert ranking_service.default_nickname("ana maria souza") == "ana S."
    assert ranking_service.default_nickname("João da Silva Pereira") == "João P."
    assert ranking_service.default_nickname("Maximiliano-Alexandrino Costa") == "Maximiliano-Al C."
    assert ranking_service.default_nickname("   ") == "Investidor"


def test_period_boards_use_the_snapshot_before_the_window(client, db):
    ha, _, pa = make_user(client, db, "Ana", "a@example.com", "110000")
    hb, _, pb = make_user(client, db, "Bruno", "b@example.com", "95000")
    hc, _, pc = make_user(client, db, "Caio", "c@example.com", "120000")
    old = datetime.now(UTC) - timedelta(days=10)
    for pid, wealth in ((pa, "100000"), (pb, "100000")):                       # Caio não tem registro antigo
        db.add(PortfolioSnapshot(portfolio_id=pid, bucket=old.replace(minute=0, second=0, microsecond=0), taken_at=old,
                                 cash_brl=D(wealth), assets_brl=0, fixed_income_brl=0, equity_brl=D(wealth),
                                 net_deposits_brl=D("100000"), initial_brl=D("100000"), wealth_brl=D(wealth)))
    db.commit()
    r = board(client, ha, board="return", period="7d")
    got = {e["nickname"]: D(e["return_pct"]) for e in r["entries"]}
    assert got == {"Ana": D("10.00"), "Bruno": D("-5.00"), "Caio": D("0.00")}      # Caio: sem passado, parte da 1ª foto
    assert [e["nickname"] for e in r["entries"]] == ["Ana", "Caio", "Bruno"]
    assert {e["nickname"]: D(e["gain_brl"]) for e in r["entries"]}["Ana"] == D("10000.00")
    assert board(client, ha, board="return", period="30d")["participants"] == 3


def test_limit_keeps_me_even_when_outside_the_top(client, db):
    for i, w in enumerate(["150000", "140000", "130000"]):
        make_user(client, db, f"U{i}", f"u{i}@example.com", w)
    hm, um, _ = make_user(client, db, "Zeca", "z@example.com", "90000")
    r = ranking_service.compute(db, "wealth", "all", um.id, limit=2)
    assert len(r["entries"]) == 2 and r["me"]["rank"] == 4 and r["participants"] == 4
    assert all(not e["is_me"] for e in r["entries"])


def test_validation_and_auth(client, auth_headers):
    assert client.get("/api/ranking").status_code == 401
    assert client.get("/api/ranking?board=xyz", headers=auth_headers).status_code == 422
    assert client.get("/api/ranking?period=1y", headers=auth_headers).status_code == 422
    assert client.put("/api/ranking/settings", json={"show_in_ranking": True}).status_code == 401
