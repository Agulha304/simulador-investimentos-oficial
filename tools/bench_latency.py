"""Mede, por rota, nº de queries, tempo no banco e tempo total (header Server-Timing).
Roda contra o Postgres LOCAL de teste (nunca o Supabase), com mercado falso.
Uso:  .venv/bin/python tools/bench_latency.py [--rtt-ms 155]   (rtt = latência por query ao banco remoto, para estimar)
A coluna 'est' = tempo total + queries × rtt: quanto custaria com o banco a essa distância."""
import os, re, sys, json
os.environ["DATABASE_URL"] = os.environ.get("BENCH_DATABASE_URL", "postgresql+psycopg://simulador@localhost:5433/simulador_test")
assert "supabase" not in os.environ["DATABASE_URL"]
os.environ["SCHEDULER_ENABLED"] = "false"
sys.path.insert(0, os.getcwd())
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text, select
from backend.config import ROOT_DIR
from backend.database import engine, SessionLocal
cfg = Config(str(ROOT_DIR / "alembic.ini")); cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"]); command.upgrade(cfg, "head")
with engine.begin() as c:
    c.execute(text("TRUNCATE users, assets RESTART IDENTITY CASCADE"))
from tests.conftest import FakeProvider
from backend.services import market_data
from backend.main import app
from backend.models import Asset

RTT = float(sys.argv[sys.argv.index("--rtt-ms") + 1]) if "--rtt-ms" in sys.argv else 155.0
market_data.set_provider(FakeProvider())
ROUTES = ["/api/auth/me", "/api/portfolio", "/api/performance?range=30d", "/api/ranking?board=wealth&period=all", "/api/assets?limit=40",
          "/api/learn", "/api/budget/overview", "/api/companies/overview", "/api/goods/overview", "/api/fixed-income/investments",
          "/api/fixed-income/products", "/api/games", "/api/progress/overview", "/api/life", "/api/economy", "/api/career", "/api/portfolio/transactions"]
def st(r):
    m = re.search(r'db;dur=(\d+);desc="(\d+) queries", total;dur=(\d+)', r.headers.get("server-timing", ""))
    return (int(m[2]), int(m[1]), int(m[3])) if m else (0, 0, 0)
out = {}
TRACE = sys.argv[sys.argv.index("--trace") + 1] if "--trace" in sys.argv else None
if TRACE:
    from sqlalchemy import event
    stmts = []
    @event.listens_for(engine, "before_cursor_execute")
    def _tr(conn, cur, st, params, ctx, many):
        stmts.append(" ".join(st.split()))
with TestClient(app) as c:
    r = c.post("/api/auth/register", json={"email": "bench@example.com", "name": "Bench", "password": "segredo123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    with SessionLocal() as db:
        for sym in ("AAPL", "PETR4", "BTC"):
            a = db.scalar(select(Asset).where(Asset.symbol == sym))
            if a: c.post("/api/trades/buy", headers=h, json={"asset_id": a.id, "amount_brl": "1000"})
    if TRACE:
        c.get(TRACE, headers=h); stmts.clear(); c.get(TRACE, headers=h)
        from collections import Counter
        for st_, n in Counter(re.sub(r"\s+", " ", x)[:150] for x in stmts).most_common(): print(f"{n:3d}x {st_}")
        sys.exit()
    print(f"{'rota':44s} {'q':>3s} {'db ms':>6s} {'tot ms':>7s} | 2ª: {'q':>3s} {'tot':>5s} | est c/ RTT={RTT:.0f}ms (1ª / 2ª)")
    for p in ROUTES:
        r1 = c.get(p, headers=h); a = st(r1); r2 = c.get(p, headers=h); b = st(r2)
        out[p] = {"status": r1.status_code, "q1": a[0], "tot1": a[2], "q2": b[0], "tot2": b[2]}
        print(f"{p:44s} {a[0]:3d} {a[1]:6d} {a[2]:7d} |      {b[0]:3d} {b[2]:5d} | {a[2]+a[0]*RTT:7.0f} / {b[2]+b[0]*RTT:7.0f}   [{r1.status_code}]")
if "--json" in sys.argv: json.dump(out, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
