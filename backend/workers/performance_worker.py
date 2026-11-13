import logging

from backend.database import SessionLocal
from backend.services import performance_service

log = logging.getLogger(__name__)


def snapshot() -> None:
    """Registra a foto horária do patrimônio de todas as carteiras (alimenta gráficos e ranking)."""
    with SessionLocal() as db:
        n = performance_service.snapshot_all(db)
    log.info("snapshots de patrimônio: %s carteira(s)", n)
