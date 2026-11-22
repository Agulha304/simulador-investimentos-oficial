from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class PasswordResetToken(Base):
    """Token de redefinição de senha. Guarda SOMENTE o hash SHA-256 do token (o valor em claro só vai por e-mail)."""
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    request_ip: Mapped[str | None] = mapped_column(String(64))


class PasswordResetRequest(Base):
    """Registro de pedidos de "esqueci a senha" para o rate limit (chave = hash de 'email:<x>' ou 'ip:<x>'; vale p/ e-mails inexistentes também)."""
    __tablename__ = "password_reset_requests"
    __table_args__ = (Index("ix_password_reset_requests_key_created", "key_hash", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
