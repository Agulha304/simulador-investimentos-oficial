"""Vida pessoal e família (etapa 4).

Valores categóricos (níveis de estilo de vida, estágio do relacionamento...) ficam em colunas String validadas
em `life_rules`: novos valores entram sem migração. O dinheiro continua só no ledger/orçamento — estas tabelas
guardam o estado pessoal (atributos, pessoas, relações, filhos) e o histórico (`LifeLog`).
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.types import Money


class LifeProfile(Base):
    __tablename__ = "life_profiles"
    __table_args__ = (
        CheckConstraint("health BETWEEN 0 AND 100 AND wellbeing BETWEEN 0 AND 100 AND quality BETWEEN 0 AND 100 "
                        "AND satisfaction BETWEEN 0 AND 100 AND social BETWEEN 0 AND 100", name="ck_life_stats"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(60), default="Você")
    age_years: Mapped[int] = mapped_column(Integer, default=28)
    # atributos 0..100
    health: Mapped[int] = mapped_column(Integer, default=70)
    wellbeing: Mapped[int] = mapped_column(Integer, default=65)
    quality: Mapped[int] = mapped_column(Integer, default=60)
    satisfaction: Mapped[int] = mapped_column(Integer, default=60)
    social: Mapped[int] = mapped_column(Integer, default=40)
    # decisões de estilo de vida (ver life_rules.LEVELS)
    gender: Mapped[str] = mapped_column(String(1), default="N")                 # M | F | N (prefiro não dizer)
    interested_in: Mapped[str] = mapped_column(String(3), default="ANY")        # ANY | M | F — quem você quer conhecer
    career_field: Mapped[str | None] = mapped_column(String(20))
    career_since: Mapped[date | None] = mapped_column(Date)
    last_raise_month: Mapped[date | None] = mapped_column(Date)
    degree_field: Mapped[str | None] = mapped_column(String(20))               # faculdade em andamento
    degree_progress: Mapped[int] = mapped_column(Integer, default=0)
    degree_total: Mapped[int] = mapped_column(Integer, default=0)
    degrees: Mapped[list] = mapped_column(JSON, default=list)                  # áreas em que já se formou
    pending_career: Mapped[dict | None] = mapped_column(JSON)                 # mudança de área combinada para o mês seguinte
    fgts_balance: Mapped[Decimal] = mapped_column(Money(), default=0, server_default="0")          # FGTS acumulado (CLT)
    fgts_release: Mapped[Decimal] = mapped_column(Money(), default=0, server_default="0")          # FGTS sacado para receber neste mês
    career_hours: Mapped[int] = mapped_column(Integer, default=0, server_default="0")             # horas/mês de cursos e empregos extras
    work_level: Mapped[str] = mapped_column(String(16), default="NORMAL")
    food_level: Mapped[str] = mapped_column(String(16), default="NORMAL")
    health_level: Mapped[str] = mapped_column(String(16), default="BASIC")
    leisure_level: Mapped[str] = mapped_column(String(16), default="NORMAL")
    family_time: Mapped[str] = mapped_column(String(16), default="NORMAL")
    # moradia: EXISTING = já tratada pelo orçamento/bens; RENT/SHARED/FAMILY_HOME geram o item `family:housing`
    housing_kind: Mapped[str] = mapped_column(String(16), default="EXISTING")
    housing_cost: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    housing_quality: Mapped[int] = mapped_column(Integer, default=0, server_default="0")        # -3..+3: condição da moradia atual
    housing_desc: Mapped[str | None] = mapped_column(String(160))
    pending_housing_quality: Mapped[int | None] = mapped_column(Integer)
    pending_housing_desc: Mapped[str | None] = mapped_column(String(160))
    pending_housing_kind: Mapped[str | None] = mapped_column(String(16))
    pending_housing_cost: Mapped[Decimal | None] = mapped_column(Money())
    pending_housing_month: Mapped[date | None] = mapped_column(Date)
    pregnancy_due_month: Mapped[date | None] = mapped_column(Date)
    pregnancy_relationship_id: Mapped[int | None] = mapped_column(Integer)
    hours_committed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")   # horas/mês fixas (gestão de temporada)
    hours_used: Mapped[int] = mapped_column(Integer, default=0)            # horas livres gastas no mês corrente
    activity_seq: Mapped[int] = mapped_column(Integer, default=0)          # contador (chaves idempotentes, sorteios)
    last_processed_month: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Person(Base):
    __tablename__ = "people"
    __table_args__ = (Index("ix_people_user", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(60))
    age: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str] = mapped_column(String(1), default="F")
    role: Mapped[str | None] = mapped_column(String(10))                       # MOTHER | FATHER | BROTHER | SISTER (família de origem)
    alive: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    death_age: Mapped[int | None] = mapped_column(Integer)                     # idade em que a pessoa falece (família)
    death_month: Mapped[date | None] = mapped_column(Date)
    personality: Mapped[str] = mapped_column(String(24))
    interests: Mapped[list] = mapped_column(JSON, default=list)
    occupation: Mapped[str] = mapped_column(String(60))
    income: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    assets: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    debts: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    sociability: Mapped[int] = mapped_column(Integer, default=50)          # 0..100
    wants_children: Mapped[int] = mapped_column(Integer, default=50)       # 0..100
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    met_month: Mapped[date] = mapped_column(Date)


class Relationship(Base):
    __tablename__ = "relationships"
    __table_args__ = (
        UniqueConstraint("person_id", name="uq_relationship_person"),
        CheckConstraint("affinity BETWEEN 0 AND 100 AND trust BETWEEN 0 AND 100", name="ck_relationship_range"),
        Index("ix_relationship_user_stage", "user_id", "stage"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(16), default="ACQUAINTANCE")
    affinity: Mapped[int] = mapped_column(Integer, default=20)
    trust: Mapped[int] = mapped_column(Integer, default=20)
    since_month: Mapped[date] = mapped_column(Date)
    stage_since: Mapped[date] = mapped_column(Date)
    ended_month: Mapped[date | None] = mapped_column(Date)
    finance_mode: Mapped[str] = mapped_column(String(12), default="SEPARATE")   # SEPARATE | SHARED
    contribution_pct: Mapped[Decimal] = mapped_column(Money(), default=Decimal("50"))   # % dos custos compartilhados
    interactions_month: Mapped[int] = mapped_column(Integer, default=0)
    last_story: Mapped[str | None] = mapped_column(String(200))             # o que vocês fizeram por último (aviso temporário)
    compat_bonus: Mapped[int] = mapped_column(Integer, default=0)            # cresce com as atividades feitas juntos
    last_interaction_month: Mapped[date | None] = mapped_column(Date)       # base do esfriamento por falta de convivência


class Child(Base):
    __tablename__ = "children"
    __table_args__ = (Index("ix_children_user", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    relationship_id: Mapped[int | None] = mapped_column(ForeignKey("relationships.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(60))
    birth_month: Mapped[date] = mapped_column(Date)
    health: Mapped[int] = mapped_column(Integer, default=85)
    development: Mapped[int] = mapped_column(Integer, default=50)
    school_kind: Mapped[str] = mapped_column(String(10), default="PUBLIC")   # PUBLIC | PRIVATE
    daycare: Mapped[bool] = mapped_column(Boolean, default=False)            # creche (0-2 anos)
    activities: Mapped[bool] = mapped_column(Boolean, default=False)         # extracurriculares
    active: Mapped[bool] = mapped_column(Boolean, default=True)              # False = emancipado (18+)


class LifeLog(Base):
    """Histórico imutável de acontecimentos pessoais e familiares."""
    __tablename__ = "life_log"
    __table_args__ = (Index("ix_life_log_user_month", "user_id", "ref_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    ref_month: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(String(240))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
