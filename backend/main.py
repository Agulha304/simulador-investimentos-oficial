"""Ponto de entrada da API.  Rodar: uvicorn backend.main:app --reload"""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from backend.dependencies import game_clock
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.core.logging import setup_logging
from backend.database import SessionLocal, check_connection
from backend.routers import account, assets, auth, budget, career, companies, debt, invest_plan, distributions, economy, engagement, fixed_income, games, goods, health, life, media, portfolio, progress, trades
from backend.core.dates import today_br
from backend.services import fixed_income_catalog, index_data
from backend.services.asset_catalog import seed_assets
from backend.workers.scheduler import shutdown_scheduler, start_scheduler

settings = get_settings()
settings.check_production()
setup_logging(settings.log_level)
log = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        check_connection()
        log.info("conexão com o banco OK")
        with SessionLocal() as db:
            seed_assets(db)
            fixed_income_catalog.seed_samples(db, today_br(), index_data.load(db))
    except Exception as exc:  # noqa: BLE001
        log.error("não foi possível conectar ao banco: %s", exc)
    if settings.scheduler_enabled:
        start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title="Simulador de Investimentos",
    description="Simulador educacional — nenhuma operação envolve dinheiro real.",
    version="0.9.0",
    lifespan=lifespan,
    dependencies=[Depends(game_clock)],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ServerTimingMiddleware:
    """ASGI puro (sem BaseHTTPMiddleware: sem task extra nem buffer por request). Header `Server-Timing` com o nº de
    queries e o tempo no banco da requisição; comprime (gzip) só as respostas JSON da API."""

    def __init__(self, inner):
        import starlette.middleware.gzip as _gz
        self.inner = inner
        self.gz = _gz.GZipMiddleware(inner, minimum_size=1024)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.inner(scope, receive, send)
        import time
        from backend.database import query_stats
        stats = [0, 0.0]
        tok = query_stats.set(stats)
        t0 = time.perf_counter()

        async def send_wrapped(msg):
            if msg["type"] == "http.response.start":
                headers = list(msg.get("headers", []))
                headers.append((b"server-timing", f'db;dur={stats[1]:.0f};desc="{stats[0]} queries", total;dur={(time.perf_counter()-t0)*1000:.0f}'.encode()))
                msg = {**msg, "headers": headers}
            await send(msg)
        path = scope.get("path", "")
        target = self.gz if path.startswith("/api/") and not path.startswith("/api/media") else self.inner
        try:
            await target(scope, receive, send_wrapped)
        finally:
            query_stats.reset(tok)


API_PREFIX = "/api"
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(portfolio.router, prefix=API_PREFIX)
app.include_router(distributions.router, prefix=API_PREFIX)
app.include_router(assets.router, prefix=API_PREFIX)
app.include_router(trades.router, prefix=API_PREFIX)
app.include_router(fixed_income.router, prefix=API_PREFIX)
app.include_router(media.router, prefix=API_PREFIX)
app.include_router(budget.router, prefix=API_PREFIX)
app.include_router(goods.router, prefix=API_PREFIX)
app.include_router(companies.router, prefix=API_PREFIX)
app.include_router(life.router, prefix=API_PREFIX)
app.include_router(games.router, prefix=API_PREFIX)
app.include_router(account.router, prefix=API_PREFIX)
app.include_router(debt.router, prefix=API_PREFIX)
app.include_router(invest_plan.router, prefix=API_PREFIX)
app.include_router(career.router, prefix=API_PREFIX)
app.include_router(economy.router, prefix=API_PREFIX)
app.include_router(progress.game_router, prefix=API_PREFIX)
app.include_router(progress.router, prefix=API_PREFIX)
for _r in (engagement.performance_router, engagement.ranking_router, engagement.learn_router):
    app.include_router(_r, prefix=API_PREFIX)


# --- site (React) servido pelo próprio backend: dá para hospedar tudo num único serviço (ex.: Render) -------------------
# Só ativa se frontend/dist existir (a imagem Docker gera). /api/* continua sendo a API; o resto cai no index.html (rotas do React).
from pathlib import Path  # noqa: E402

from fastapi import HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_FRONT = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if (_FRONT / "index.html").is_file():
    if (_FRONT / "assets").is_dir():
        class _ImmutableAssets(StaticFiles):
            """Arquivos do Vite têm hash no nome: o navegador pode guardá-los por 1 ano sem revalidar."""
            def file_response(self, *a, **k):
                r = super().file_response(*a, **k)
                r.headers["Cache-Control"] = "public, max-age=31536000, immutable"
                return r

        app.mount("/assets", _ImmutableAssets(directory=_FRONT / "assets"), name="site-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def _site(full_path: str):
        if full_path.startswith("api/") or full_path in ("docs", "openapi.json", "redoc"):
            raise HTTPException(404, "Não encontrado")
        f = (_FRONT / full_path).resolve()
        if full_path and f.is_file() and _FRONT.resolve() in f.parents:
            return FileResponse(f, headers={"Cache-Control": "public, max-age=3600"})
        return FileResponse(_FRONT / "index.html", headers={"Cache-Control": "no-cache"})   # sempre revalida (ETag): pega o deploy novo

app.add_middleware(ServerTimingMiddleware)
