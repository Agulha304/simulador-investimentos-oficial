"""Progressão (etapa 6): objetivos, conquistas e relatórios mensais.

* `Goal`: acompanhado automaticamente no fechamento; só conclui depois de SUSTENTAR a condição por N meses.
* `Achievement`: registrada uma única vez (única por usuário/chave) e NUNCA removida — vender um bem ou fechar uma
  empresa não apaga conquistas históricas.
* `MonthReport`: retrato imutável de cada mês fechado, montado com dados reais; os relatórios anuais somam estas linhas.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_goal_user_key"), Index("ix_goals_user_status", "user_id", "status"))

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(10))                 # FINANCIAL | BUSINESS | PERSONAL
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(240), default="")
    metric: Mapped[str] = mapped_column(String(32))
    comparator: Mapped[str] = mapped_column(String(3), default="GTE")      # GTE | LTE
    target: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    sustain_months: Mapped[int] = mapped_column(Integer, default=1)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    current: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(8), default="ACTIVE")     # ACTIVE | DONE
    origin: Mapped[str] = mapped_column(String(10), default="SYSTEM")    # SCENARIO | USER | SYSTEM
    created_month: Mapped[date | None] = mapped_column(Date)
    done_month: Mapped[date | None] = mapped_column(Date)
    last_eval_month: Mapped[date | None] = mapped_column(Date)


class Achievement(Base):
    __tablename__ = "achievements"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_achievement_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(40))
    unlocked_month: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MonthReport(Base):
    __tablename__ = "month_reports"
    __table_args__ = (UniqueConstraint("user_id", "ref_month", name="uq_month_report_user_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    ref_month: Mapped[date] = mapped_column(Date)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
