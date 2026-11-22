"""Cadastro e autenticação de usuários."""
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.core.security import hash_password, verify_password
from backend.models import PasswordResetRequest, PasswordResetToken, Portfolio, TransactionSource, User
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


# ----------------------------------------------------------------- esqueci minha senha
RESET_TOKEN_TTL = timedelta(hours=1)
RESET_MAX_PER_EMAIL = 3      # pedidos por e-mail por hora (conta e-mails inexistentes também: não revela nada)
RESET_MAX_PER_IP = 10        # pedidos por IP por hora
RESET_WINDOW = timedelta(hours=1)


class ResetRateLimitedIPError(Exception):
    pass


class InvalidResetTokenError(Exception):
    pass


def _now() -> datetime:      # ponto único de relógio (os testes trocam)
    return datetime.now(UTC)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hit(db: Session, key: str, limit: int, now: datetime) -> bool:
    """Registra o pedido e diz se ainda está dentro do limite. Tabela (e não memória) => vale entre instâncias/reinícios."""
    h = _sha256(key)
    since = now - RESET_WINDOW
    count = db.scalar(select(func.count()).select_from(PasswordResetRequest)
                      .where(PasswordResetRequest.key_hash == h, PasswordResetRequest.created_at > since)) or 0
    db.add(PasswordResetRequest(key_hash=h, created_at=now))
    return count < limit


def request_password_reset(db: Session, email: str, ip: str | None) -> tuple[User, str] | None:
    """Retorna (usuário, token em claro) se um e-mail deve ser enviado; None caso contrário (inexistente / limitado).
    Levanta ResetRateLimitedIPError se o IP estourou o limite. O chamador responde SEMPRE a mesma mensagem genérica."""
    now = _now()
    db.execute(delete(PasswordResetRequest).where(PasswordResetRequest.created_at <= now - RESET_WINDOW))
    ip_ok = _hit(db, f"ip:{ip or 'desconhecido'}", RESET_MAX_PER_IP, now)
    email_ok = _hit(db, f"email:{normalize_email(email)}", RESET_MAX_PER_EMAIL, now)
    if not ip_ok:
        db.commit()
        raise ResetRateLimitedIPError()
    user = get_user_by_email(db, email) if email_ok else None
    if user is None or user.is_game_world:
        db.commit()
        return None
    db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
               .values(used_at=now))                                    # invalida os anteriores
    token = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(user_id=user.id, token_hash=_sha256(token), expires_at=now + RESET_TOKEN_TTL,
                              created_at=now, request_ip=(ip or None) and ip[:64]))
    db.commit()
    return user, token


def reset_password(db: Session, token: str, new_password: str) -> None:
    """Valida hash/expiração/uso único, troca a senha e invalida todos os tokens do usuário. Erro único p/ qualquer falha."""
    now = _now()
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == _sha256(token.strip())).with_for_update())
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise InvalidResetTokenError()
    user = db.get(User, row.user_id)
    if user is None:
        raise InvalidResetTokenError()
    user.password_hash = hash_password(new_password)
    db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
               .values(used_at=now))
    db.commit()
    log.info("senha redefinida user=%s", user.id)
