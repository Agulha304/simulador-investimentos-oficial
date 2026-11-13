import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.database import check_connection

router = APIRouter(tags=["health"])
log = logging.getLogger(__name__)


@router.get("/health")
def health():
    try:
        db_ok = check_connection()
    except Exception as exc:  # noqa: BLE001
        log.error("health: banco indisponível: %s", exc)
        db_ok = False
    body = {"status": "ok" if db_ok else "degraded", "database": "ok" if db_ok else "unavailable"}
    return JSONResponse(body, status_code=200 if db_ok else 503)
