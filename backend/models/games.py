"""Partidas salvas. Cada partida é um MUNDO isolado: um usuário-sombra (`User.is_game_world`) dono de sua carteira,
orçamento, bens, empresas, vida e economia. Todos os serviços já funcionam por `user_id`, então a partida reaproveita
tudo sem duplicar nada; a conta real só aponta para as suas partidas."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (Index("ix_games_account", "account_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    world_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    kind: Mapped[str] = mapped_column(String(10))                       # LIFE | TRAINING
    name: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")   # ACTIVE | ARCHIVED
    config: Mapped[dict] = mapped_column(JSON, default=dict)            # treino: {"market_date": "YYYY-MM-01", "start_date": ...}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccountCategory(Base):
    """Categorias de orçamento da CONTA (configurações da conta): valem para todas as partidas, atuais e futuras."""
    __tablename__ = "account_categories"
    __table_args__ = (UniqueConstraint("account_id", "kind", "name", name="uq_account_category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8))                       # INCOME | EXPENSE
    name: Mapped[str] = mapped_column(String(60))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
