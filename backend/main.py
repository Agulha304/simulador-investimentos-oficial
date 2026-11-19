"""Ponto de entrada da API.  Rodar: uvicorn backend.main:app --reload"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.core.logging import setup_logging
from backend.database import SessionLocal, check_connection
from backend.routers import assets, auth, budget, distributions, goods, engagement, fixed_income, health, media, portfolio, trades
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
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
for _r in (engagement.performance_router, engagement.ranking_router, engagement.learn_router):
    app.include_router(_r, prefix=API_PREFIX)
