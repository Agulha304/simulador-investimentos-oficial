import logging

from backend.database import SessionLocal
from backend.services import risk_service

log = logging.getLogger(__name__)


def run() -> None:
    """Job do APScheduler: confere Stop Loss / Take Profit de todas as posições."""
    with SessionLocal() as db:
        n = risk_service.check_all(db)
    if n:
        log.info("SL/TP: %s posição(ões) encerrada(s)", n)
