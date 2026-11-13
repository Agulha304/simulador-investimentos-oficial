from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from backend.content.course import LESSONS_ORDERED
from backend.models import Portfolio, PortfolioSnapshot, Transaction, TransactionType
from backend.services import learn_service, market_data, performance_service, portfolio_service
from tests.test_fixed_income_math import flat_index

D = Decimal
UTC_NOON = lambda y, m, d, h=15: datetime(y, m, d, h, tzinfo=UTC)  # noqa: E731  (15h UTC = 12h em São Paulo)


def snap(equity, wealth, when):
    return PortfolioSnapshot(portfolio_id=1, bucket=when, taken_at=when, cash_brl=D(equity), assets_brl=D(0), fixed_income_brl=D(0),
                             equity_brl=D(equity), net_deposits_brl=D(100000), initial_brl=D(100000), wealth_brl=D(wealth))


def tx(type_, pnl=None, cash=D(0), note=None, when=None):
    return Transaction(type=type_, realized_pnl_brl=None if pnl is None else D(pnl), cash_amount_brl=D(cash), note=note,
                       created_at=when or UTC_NOON(2026, 3, 2), gross_amount_brl=D(0))


def buy(client, h, asset, qty):
    assert client.post("/api/trades/buy", headers=h, json={"asset_id": asset.id, "quantity": str(qty)}).status_code == 201


def perf(client, h, rng="30d"):
    r = client.get(f"/api/performance?range={rng}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ snapshots

def test_snapshot_excludes_extra_deposits_from_wealth(client, auth_headers, db):
    pid = db.scalar(select(Portfolio.id))
    client.post("/api/portfolio/deposit", headers=auth_headers, json={"amount": "5000"})
    s = performance_service.take_snapshot(db, portfolio_service.load_portfolio(db, pid), datetime.now(UTC) + timedelta(hours=1))
    assert (s.equity_brl, s.wealth_brl, s.net_deposits_brl, s.initial_brl) == (D("105000.00"), D("100000.00"), D("105000.00"), D("100000.00"))


def test_snapshots_are_one_per_hour(client, auth_headers, db):
    pid = db.scalar(select(Portfolio.id))
    p = portfolio_service.load_portfolio(db, pid)
    base = datetime.now(UTC).replace(minute=5)
    performance_service.take_snapshot(db, p, base)
    performance_service.take_snapshot(db, p, base + timedelta(minutes=40))          # mesma hora: atualiza
    performance_service.take_snapshot(db, p, base + timedelta(hours=1))
    n = db.scalar(select(func.count()).select_from(PortfolioSnapshot))
    assert n == 2 + (0 if base.hour == datetime.now(UTC).hour else 1)               # + o snapshot do cadastro, se em outra hora


def test_snapshot_is_skipped_when_a_price_is_unavailable(client, auth_headers, assets, db, _fake_market):
    buy(client, auth_headers, assets["PETR4"], 10)
    pid = db.scalar(select(Portfolio.id))
    before = db.scalar(select(func.count()).select_from(PortfolioSnapshot))
    del _fake_market.prices["PETR4.SA"]
    market_data.clear_cache()
    assert performance_service.take_snapshot(db, portfolio_service.load_portfolio(db, pid), datetime.now(UTC) + timedelta(hours=3)) is None
    assert db.scalar(select(func.count()).select_from(PortfolioSnapshot)) == before          # sem foto falsa de queda


def test_snapshot_all_covers_every_portfolio(client, auth_headers, db):
    client.post("/api/auth/register", json={"email": "z@example.com", "name": "Z", "password": "segredo123"})
    assert performance_service.snapshot_all(db) == 2


# ------------------------------------------------------------------ série, benchmark e queda

def test_series_return_cdi_and_drawdown():
    days = [date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4), date(2026, 3, 5)]           # seg a qui
    wealth = ["100000", "101000", "99000", "102000"]
    rows = [snap(w, w, UTC_NOON(d.year, d.month, d.day)) for d, w in zip(days, wealth)]
    s = performance_service.build_series(rows, flat_index())
    assert [p["return_pct"] for p in s] == [D("0.00"), D("1.00"), D("-1.00"), D("2.00")]
    assert [p["cdi_pct"] for p in s] == [D("0.00"), D("0.05"), D("0.10"), D("0.15")]            # 0,05% ao dia útil
    assert [p["drawdown_pct"] for p in s] == [D("0.00"), D("0.00"), D("-1.98"), D("0.00")]
    st = performance_service.series_stats(s)
    assert st["period_return_pct"] == D("2.00") and st["cdi_pct"] == D("0.15") and st["vs_cdi_pp"] == D("1.85")
    assert st["max_drawdown_pct"] == D("-1.98") and st["best_day_pct"] == D("3.03") and st["worst_day_pct"] == D("-1.98")
    assert performance_service.series_stats(s[:1])["period_return_pct"] is None and performance_service.build_series([], flat_index()) == []


def test_downsample_keeps_the_last_snapshot_of_each_day():
    rows = [snap(100, 100, UTC_NOON(2026, 3, 2, 12)), snap(101, 101, UTC_NOON(2026, 3, 2, 18)), snap(105, 105, UTC_NOON(2026, 3, 3, 12))]
    daily = performance_service.downsample(rows, hourly=False)
    assert [r.wealth_brl for r in daily] == [D(101), D(105)] and performance_service.downsample(rows, hourly=True) == rows


# ------------------------------------------------------------------ operações

def test_trade_stats():
    txs = [tx(TransactionType.SELL, "100", note="a"), tx(TransactionType.SELL, "200", note="b"), tx(TransactionType.SELL, "50", note="c"),
           tx(TransactionType.SELL, "-50", note="d"), tx(TransactionType.FIXED_INCOME_REDEEM, "-150", note="Resgate antecipado: CDB X"),
           tx(TransactionType.DIVIDEND, cash="30"), tx(TransactionType.FIXED_INCOME_COUPON, cash="20"),
           tx(TransactionType.BUY), tx(TransactionType.BUY), tx(TransactionType.FIXED_INCOME_APPLY)]
    t = performance_service.trade_stats(txs)
    assert (t["closed_trades"], t["wins"], t["losses"], t["buys"], t["sells"], t["fixed_income_applications"]) == (5, 3, 2, 2, 4, 1)
    assert t["win_rate_pct"] == D("60.00") and t["avg_win_brl"] == D("116.67") and t["avg_loss_brl"] == D("-100.00")
    assert t["payoff_ratio"] == D("1.17") and t["profit_factor"] == D("1.75")                    # 350 / 200
    assert t["total_realized_brl"] == D("150.00") and t["income_total_brl"] == D("50.00")
    assert (t["best_trade_brl"], t["best_trade_label"]) == (D("200.00"), "b")
    assert (t["worst_trade_brl"], t["worst_trade_label"]) == (D("-150.00"), "CDB X")
    empty = performance_service.trade_stats([])
    assert empty["closed_trades"] == 0 and empty["win_rate_pct"] is None and empty["payoff_ratio"] is None and empty["best_trade_brl"] is None


def test_monthly_and_cumulative_results():
    txs = [tx(TransactionType.SELL, "100", when=UTC_NOON(2026, 1, 10)), tx(TransactionType.BUY, when=UTC_NOON(2026, 1, 11)),
           tx(TransactionType.DIVIDEND, cash="10", when=UTC_NOON(2026, 2, 5)), tx(TransactionType.SELL, "-30", when=UTC_NOON(2026, 2, 6))]
    monthly, cum = performance_service.monthly_and_cumulative(txs)
    assert monthly == [{"month": "2026-01", "realized": D("100.00"), "income": D("0.00"), "trades": 2},
                       {"month": "2026-02", "realized": D("-30.00"), "income": D("10.00"), "trades": 1}]
    assert [(c["date"], c["cumulative"]) for c in cum] == [(date(2026, 1, 10), D("100.00")), (date(2026, 2, 5), D("110.00")),
                                                          (date(2026, 2, 6), D("80.00"))]


def test_diversification_score_formula():
    pos = lambda *vals: [{"name": f"A{i}", "value": D(v), "protected": False, "market": True} for i, v in enumerate(vals)]  # noqa: E731
    assert performance_service.diversification([])[0] is None
    assert performance_service.diversification(pos(500))[0] == 0
    assert performance_service.diversification(pos(1, 1, 1, 1))[0] == 75
    assert performance_service.diversification(pos(*[1] * 10))[0] == 90
    score, top = performance_service.diversification(pos(900, 100))
    assert score == 18 and top == {"name": "A0", "pct": D("90.00")}                                # 1 − (0,81 + 0,01)


# ------------------------------------------------------------------ endpoint

def test_requires_auth_and_validates_range(client, auth_headers):
    assert client.get("/api/performance").status_code == 401
    assert client.get("/api/performance?range=2y", headers=auth_headers).status_code == 422


def test_new_account_has_a_meaningful_empty_state(client, auth_headers):
    p = perf(client, auth_headers)
    assert len(p["series"]) == 1 and p["series_stats"]["period_return_pct"] is None
    s = p["summary"]
    assert (s["wealth_brl"], s["pnl_brl"], s["positions"]) == ("100000.00", "0.00", 0) and s["diversification_score"] is None
    assert p["allocation"] == [{"label": "Caixa", "value": "100000.00", "pct": "100.00"}]
    assert p["trades"]["closed_trades"] == 0 and p["trades"]["win_rate_pct"] is None
    assert any("Estamos registrando" in i["text"] for i in p["insights"])
    assert any("parado em caixa" in i["text"] for i in p["insights"])
    assert [a["id"] for a in p["achievements"] if a["unlocked"]] == []


def test_portfolio_composition_and_achievements(client, auth_headers, assets, db):
    buy(client, auth_headers, assets["PETR4"], 10)             # R$ 400
    buy(client, auth_headers, assets["AAPL"], 1)               # R$ 1.560
    assert client.post("/api/trades/buy", headers=auth_headers, json={"asset_id": assets["BTC"].id, "amount_brl": "500"}).status_code == 201
    client.put(f"/api/trades/risk/{assets['PETR4'].id}", headers=auth_headers, json={"stop_loss": "35"})
    p = perf(client, auth_headers)
    labels = {a["label"]: a for a in p["allocation"]}
    assert set(labels) == {"Ações Brasil", "Ações EUA", "Criptomoedas", "Caixa"}
    assert D(labels["Ações EUA"]["value"]) == D("1560.00") and D(labels["Caixa"]["value"]) == D("97540.00")
    assert abs(sum(D(a["pct"]) for a in p["allocation"]) - 100) <= D("0.05") and p["allocation"][0]["label"] == "Caixa"
    assert p["summary"]["positions"] == 3 and p["summary"]["pnl_brl"] == "0.00"                     # compras a mercado não geram lucro
    values = [D("400"), D("1560"), D("500")]
    total = sum(values)
    expected = int(((1 - sum((v / total) ** 2 for v in values)) * 100).quantize(D("1")))
    assert p["summary"]["diversification_score"] == expected and p["summary"]["top_position"]["name"] == "AAPL"
    assert D(p["summary"]["discipline_pct"]) == D("33.33")                                         # 1 de 3 com stop
    got = {a["id"]: a for a in p["achievements"]}
    assert all(got[k]["unlocked"] for k in ("first_buy", "risk_manager", "crypto", "international"))
    assert not got["first_profit"]["unlocked"] and not got["first_income"]["unlocked"] and not got["graduate"]["unlocked"]
    assert got["ten_trades"]["current"] == 3 and got["ten_trades"]["detail"] == "3/10"
    assert got["diversified"]["current"] == 3 and "3 posições em 3 classes" in got["diversified"]["detail"]
    assert any("Só 1 de 3 posições" in i["text"] and i["lesson_id"] == "m7-l2" for i in p["insights"])


def test_concentration_insight_points_to_the_right_lesson(client, auth_headers, assets):
    buy(client, auth_headers, assets["PETR4"], 10)
    ins = perf(client, auth_headers)["insights"]
    conc = next(i for i in ins if "100,00% do que você tem investido está em PETR4" in i["text"])
    assert conc["tone"] == "warn" and conc["lesson_id"] == "m7-l1"


def test_extra_deposit_is_not_profit_in_the_performance_tab(client, auth_headers):
    client.post("/api/portfolio/deposit", headers=auth_headers, json={"amount": "50000"})
    s = perf(client, auth_headers)["summary"]
    assert (s["equity_brl"], s["wealth_brl"], s["pnl_brl"], s["total_return_pct"]) == ("150000.00", "100000.00", "0.00", "0.00")


def test_closed_trades_feed_the_stats_and_achievements(client, auth_headers, assets, _fake_market):
    petr = assets["PETR4"]
    buy(client, auth_headers, petr, 10)
    _fake_market.prices["PETR4.SA"] = ("50", _fake_market.prices["PETR4.SA"][1])
    market_data.clear_cache()
    assert client.post("/api/trades/sell", headers=auth_headers, json={"asset_id": petr.id, "quantity": "10"}).status_code == 201
    p = perf(client, auth_headers)
    t = p["trades"]
    assert (t["closed_trades"], t["wins"], t["losses"], t["total_realized_brl"], t["best_trade_label"]) == (1, 1, 0, "100.00", "PETR4")
    assert p["summary"]["pnl_brl"] == "100.00" and p["summary"]["total_return_pct"] == "0.10"
    assert next(a for a in p["achievements"] if a["id"] == "first_profit")["unlocked"]
    assert next(a for a in p["achievements"] if a["id"] == "green")["unlocked"]
    assert p["monthly"][0]["realized"] == "100.00" and p["realized_cumulative"][-1]["cumulative"] == "100.00"


def test_lessons_unlock_student_achievements(client, auth_headers, db):
    from backend.models import User
    uid = db.scalar(select(User.id))
    for l in LESSONS_ORDERED[:5]:
        learn_service.submit_quiz(db, uid, l.id, [q.correct for q in l.quiz])
    got = {a["id"]: a for a in perf(client, auth_headers)["achievements"]}
    assert got["student"]["unlocked"] and not got["graduate"]["unlocked"] and got["graduate"]["current"] == 5


def test_hourly_resolution_for_short_ranges(client, auth_headers, db):
    pid = db.scalar(select(Portfolio.id))
    now = datetime.now(UTC)
    for h in (2, 3):
        db.add(snap("100000", "100000", (now - timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)))
    db.commit()
    db.query(PortfolioSnapshot).filter(PortfolioSnapshot.portfolio_id == 1).update({"portfolio_id": pid})
    db.commit()
    assert len(perf(client, auth_headers, "1d")["series"]) >= 3          # horário
    assert len(perf(client, auth_headers, "30d")["series"]) == 1         # diário: tudo no mesmo dia


def test_scheduler_registers_snapshot_job():
    from backend.workers.scheduler import shutdown_scheduler, start_scheduler
    sch = start_scheduler()
    try:
        assert "performance_snapshot" in {j.id for j in sch.get_jobs()}
    finally:
        shutdown_scheduler()
