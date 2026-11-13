import logging
import time

from sqlalchemy.orm import Session

from backend.core.dates import today_br
from backend.database import SessionLocal
from backend.services import fixed_income_catalog, fixed_income_service, index_data

log = logging.getLogger(__name__)
_last_sync = 0.0


def sync_all(db: Session, today=None, *, min_interval: float = 0.0) -> bool:
    """Atualiza índices (Banco Central), Tesouro Direto e ofertas de exemplo. Cada etapa é independente:
    se uma fonte cair, as outras continuam. `min_interval` evita consultas repetidas em sequência."""
    global _last_sync
    if min_interval and time.monotonic() - _last_sync < min_interval:
        return False
    _last_sync = time.monotonic()
    today = today or today_br()
    try:
        index_data.sync(db, today)
    except Exception:
        db.rollback()
        log.exception("falha ao sincronizar índices")
    try:
        fixed_income_catalog.sync_treasury(db, today)
    except Exception:
        db.rollback()
        log.warning("falha ao sincronizar o Tesouro Direto", exc_info=True)
    fixed_income_catalog.deactivate_expired(db, today)
    fixed_income_catalog.seed_samples(db, today, index_data.load(db))
    return True


def sync() -> None:
    with SessionLocal() as db:
        sync_all(db)


def process_events() -> None:
    """Paga cupons e vencimentos devidos."""
    with SessionLocal() as db:
        n = fixed_income_service.process_due_events(db, index_data.load(db), today_br())
    if n:
        log.info("renda fixa: %s evento(s) pago(s)", n)
