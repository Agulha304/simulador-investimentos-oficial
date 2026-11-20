"""Engine e sessão do SQLAlchemy."""
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import get_settings


class Base(DeclarativeBase):
    pass


# pool pequeno: o pooler do Supabase limita conexões; pre_ping descarta conexões fechadas pelo pooler
engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=1800, future=True)
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
