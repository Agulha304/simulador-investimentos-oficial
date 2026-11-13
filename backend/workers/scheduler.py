"""APScheduler: registro central dos workers periódicos.

Cada fase registra seus jobs aqui (market, stop loss/take profit,
distribuições, renda fixa). Os jobs devem ser idempotentes — a proteção
final contra duplicidade é a `idempotency_key` única em Transaction.
"""
import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from backend.config import get_settings
from backend.workers import distribution_worker, fixed_income_worker, performance_worker, risk_worker

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
    _scheduler.add_job(distribution_worker.discover, "interval", hours=6, id="distribution_discover",
                       next_run_time=datetime.now(UTC) + timedelta(minutes=1), replace_existing=True)
    _scheduler.add_job(fixed_income_worker.sync, "interval", hours=6, id="fixed_income_sync",
                       next_run_time=datetime.now(UTC) + timedelta(minutes=1), replace_existing=True)
    _scheduler.add_job(fixed_income_worker.process_events, "interval", minutes=15, id="fixed_income_events",
                       next_run_time=datetime.now(UTC) + timedelta(minutes=3), replace_existing=True)
    _scheduler.add_job(performance_worker.snapshot, "interval", minutes=30, id="performance_snapshot",
                       next_run_time=datetime.now(UTC) + timedelta(minutes=4), replace_existing=True)
    _scheduler.add_job(distribution_worker.pay, "interval", minutes=15, id="distribution_pay",
                       next_run_time=datetime.now(UTC) + timedelta(minutes=2), replace_existing=True)
    _scheduler.start()
    log.info("scheduler iniciado com jobs: %s", [j.id for j in _scheduler.get_jobs()])
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("scheduler finalizado")
    _scheduler = None
