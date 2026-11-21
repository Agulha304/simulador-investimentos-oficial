"""Engine e sessão do SQLAlchemy."""
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import get_settings


class Base(DeclarativeBase):
    pass


# pool pequeno: o pooler do Supabase limita conexões; pre_ping descarta conexões fechadas pelo pooler
# sem pre_ping (era um SELECT 1 = 1 ida-e-volta extra a cada checkout, várias por request); em troca,
# recicla a cada 5 min e usa TCP keepalive para o pooler não derrubar conexões ociosas.
engine = create_engine(
    get_settings().database_url, pool_pre_ping=False, pool_size=8, max_overflow=4, pool_recycle=300, future=True,
    connect_args={"keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 3,
                  "application_name": "simulador"},
)

# diagnóstico: loga queries lentas (> SLOW_QUERY_MS) e conta queries por request
import logging, os, time
from contextvars import ContextVar
from sqlalchemy import event

_log = logging.getLogger("db.slow")
_SLOW_MS = float(os.getenv("SLOW_QUERY_MS", "150"))
query_stats: ContextVar[list | None] = ContextVar("query_stats", default=None)


@event.listens_for(engine, "before_cursor_execute")
def _t0(conn, cursor, statement, parameters, context, executemany):
    context._t0 = time.perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def _t1(conn, cursor, statement, parameters, context, executemany):
    ms = (time.perf_counter() - context._t0) * 1000
    st = query_stats.get()
    if st is not None:
        st[0] += 1
        st[1] += ms
    if ms >= _SLOW_MS:
        _log.warning("slow query %.0fms: %s", ms, " ".join(statement.split())[:300])
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Dependência FastAPI: uma sessão por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_connection() -> bool:
    with engine.connect() as conn:
        return conn.execute(text("SELECT 1")).scalar() == 1
