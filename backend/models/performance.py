from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.types import Money


class PortfolioSnapshot(Base):
    """Foto do patrimônio de uma carteira (no máximo uma por hora). Alimenta o gráfico de evolução,
    o benchmark contra o CDI e o ranking.

    `wealth_brl` = patrimônio − aportes virtuais EXTRAS (depósitos além do saldo inicial). É a base do
    ranking e da rentabilidade: depositar mais dinheiro fictício não vira "lucro" nem sobe no ranking."""

    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "bucket", name="uq_snapshot_portfolio_bucket"),
        Index("ix_snapshot_portfolio_taken", "portfolio_id", "taken_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True))        # hora cheia (UTC)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cash_brl: Mapped[Decimal] = mapped_column(Money())
    assets_brl: Mapped[Decimal] = mapped_column(Money())
    fixed_income_brl: Mapped[Decimal] = mapped_column(Money())
    equity_brl: Mapped[Decimal] = mapped_column(Money())
    net_deposits_brl: Mapped[Decimal] = mapped_column(Money())
    initial_brl: Mapped[Decimal] = mapped_column(Money())                     # saldo inicial (depósito do sistema)
    wealth_brl: Mapped[Decimal] = mapped_column(Money())


class LessonProgress(Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_lesson_progress_user_lesson"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[str] = mapped_column(String(40))
    best_score: Mapped[int] = mapped_column(default=0)                        # % de acertos (0-100)
    attempts: Mapped[int] = mapped_column(default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
