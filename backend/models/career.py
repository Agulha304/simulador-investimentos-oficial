"""Carreira: empregos (CLT/PJ), educação (cursos e faculdades), currículo, candidaturas e freelas."""
from datetime import date

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal

from backend.database import Base
from backend.models.types import Money


class CareerJob(Base):
    """Um emprego (atual ou antigo). `recurring_item_id` aponta o salário no orçamento; `legacy` = o emprego inicial (salários sem vínculo)."""
    __tablename__ = "career_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(80))
    employer: Mapped[str] = mapped_column(String(80))
    field: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(4), default="CLT")                 # CLT | PJ
    level: Mapped[int] = mapped_column(Integer, default=0)
    net: Mapped[Decimal] = mapped_column(Money())                               # salário líquido mensal na contratação
    vr: Mapped[Decimal] = mapped_column(Money(), default=0)                     # vale-refeição/alimentação mensal (só CLT)
    health_plan: Mapped[bool] = mapped_column(Boolean, default=False)
    hours: Mapped[int] = mapped_column(Integer, default=0)                      # horas/mês de tempo livre que consome (PJ extra)
    start_month: Mapped[date] = mapped_column(Date)
    end_month: Mapped[date | None] = mapped_column(Date)                        # último mês trabalhado
    end_reason: Mapped[str | None] = mapped_column(String(12))                  # QUIT | REPLACED
    recurring_item_id: Mapped[int | None] = mapped_column(Integer)
    legacy: Mapped[bool] = mapped_column(Boolean, default=False)
    in_resume: Mapped[bool] = mapped_column(Boolean, default=True)


class Education(Base):
    """Curso ou faculdade (histórico de educação)."""
    __tablename__ = "career_education"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    field: Mapped[str] = mapped_column(String(20))                              # área ou "geral"
    kind: Mapped[str] = mapped_column(String(8), default="COURSE")              # COURSE | DEGREE
    months_total: Mapped[int] = mapped_column(Integer, default=1)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    cost_month: Mapped[Decimal] = mapped_column(Money(), default=0)
    hours: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(8), default="ACTIVE")            # ACTIVE | DONE | DROPPED
    start_month: Mapped[date] = mapped_column(Date)
    end_month: Mapped[date | None] = mapped_column(Date)
    in_resume: Mapped[bool] = mapped_column(Boolean, default=True)


class JobApplication(Base):
    __tablename__ = "career_applications"
    __table_args__ = (UniqueConstraint("user_id", "offer_key", name="uq_application_offer"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ref_month: Mapped[date] = mapped_column(Date)
    offer_key: Mapped[str] = mapped_column(String(60))
    offer: Mapped[dict] = mapped_column(JSON)
    chance: Mapped[int] = mapped_column(Integer)                                # % na hora de se candidatar
    status: Mapped[str] = mapped_column(String(10))                             # APPROVED | REJECTED | ACCEPTED


class Gig(Base):
    __tablename__ = "career_gigs"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_gig_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ref_month: Mapped[date] = mapped_column(Date, index=True)
    key: Mapped[str] = mapped_column(String(60))
    field: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(80))
    hours: Mapped[int] = mapped_column(Integer)
    pay: Mapped[Decimal] = mapped_column(Money())
