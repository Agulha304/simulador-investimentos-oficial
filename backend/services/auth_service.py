"""Cadastro e autenticação de usuários."""
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.core.security import hash_password, verify_password
from backend.models import Portfolio, TransactionSource, User
from backend.services import ledger_service

log = logging.getLogger(__name__)


class EmailAlreadyRegisteredError(Exception):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == normalize_email(email)))


def register_user(db: Session, *, email: str, name: str, password: str) -> User:
    """Cria usuário + carteira + depósito do saldo inicial, atomicamente."""
    if get_user_by_email(db, email):
        raise EmailAlreadyRegisteredError(email)

    user = User(email=normalize_email(email), name=name.strip(), password_hash=hash_password(password))
    db.add(user)
    db.flush()

    portfolio = Portfolio(user_id=user.id)
    db.add(portfolio)
    db.flush()

    ledger_service.deposit(
        db, portfolio.id, get_settings().initial_balance,
        source=TransactionSource.SYSTEM,
        idempotency_key=f"initial-deposit:portfolio:{portfolio.id}",
        note="Saldo virtual inicial",
    )
    db.commit()
    db.refresh(user)
    try:                                   # o novo usuário já aparece no ranking e no gráfico de evolução
        from backend.services import performance_service, portfolio_service
        performance_service.take_snapshot(db, portfolio_service.load_portfolio(db, portfolio.id))
    except Exception:
        db.rollback()
        log.exception("snapshot inicial não registrado (carteira %s)", portfolio.id)
    log.info("usuário criado id=%s portfolio=%s", user.id, portfolio.id)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if user and verify_password(password, user.password_hash):
        return user
    return None
