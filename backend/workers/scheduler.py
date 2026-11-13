"""APScheduler: registro central dos workers periódicos.

Cada fase registra seus jobs aqui (market, stop loss/take profit,
distribuições, renda fixa). Os jobs devem ser idempotentes — a proteção
final contra duplicidade é a `idempotency_key` única em Transaction.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from backend.config import get_settings
from backend.workers import risk_worker

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def heartbeat() -> None:
    log.debug("scheduler ativo")


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler
    _scheduler = BackgroundScheduler(
        timezone="America/Sao_Paulo",
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60},
    )
    _scheduler.add_job(heartbeat, "interval", minutes=5, id="heartbeat", replace_existing=True)
    _scheduler.add_job(risk_worker.run, "interval", seconds=get_settings().risk_check_interval_seconds,
                       id="stop_loss_take_profit", replace_existing=True)
    _scheduler.start()
    log.info("scheduler iniciado com jobs: %s", [j.id for j in _scheduler.get_jobs()])
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("scheduler finalizado")
    _scheduler = None
