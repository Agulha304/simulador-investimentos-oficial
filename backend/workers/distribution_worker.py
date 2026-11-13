import logging

from backend.database import SessionLocal
from backend.services import distribution_service

log = logging.getLogger(__name__)


def discover() -> None:
    with SessionLocal() as db:
        n = distribution_service.discover(db)
    if n:
        log.info("distribuições: %s direito(s) novo(s) reconhecido(s)", n)


def pay() -> None:
    with SessionLocal() as db:
        n = distribution_service.pay_due(db)
    if n:
        log.info("distribuições: %s pagamento(s) efetuado(s)", n)
