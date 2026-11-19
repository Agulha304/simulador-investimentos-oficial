"""Economia simulada, eventos e partida (etapas 5 e 6).

* `GameProfile`: modo de jogo, cenário e SEMENTE do mundo. Toda aleatoriedade vem de `hash01(seed, ...)`:
  a mesma semente reproduz exatamente o mesmo cenário (testes). Usuários com a mesma semente compartilham
  as mesmas condições econômicas de mundo.
* `EconomyState`: uma linha por usuário e mês (única) — variáveis macro e índices de preços acumulados.
  Imutável depois de criada: é o histórico econômico.
* `WorldEvent`: eventos com duração, intensidade e efeitos; únicos por (usuário, chave, mês de início).
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class GameProfile(Base):
    __tablename__ = "game_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    mode: Mapped[str] = mapped_column(String(12), default="FREE")                 # FREE | CAREER
    scenario_key: Mapped[str | None] = mapped_column(String(40))
    economy_mode: Mapped[str] = mapped_column(String(10), default="STATIC")       # STATIC | DYNAMIC
    seed: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict] = mapped_column(JSON, default=dict)                      # parâmetros iniciais usados
    started_month: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EconomyState(Base):
    __tablename__ = "economy_states"
    __table_args__ = (UniqueConstraint("user_id", "ref_month", name="uq_economy_state_user_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    ref_month: Mapped[date] = mapped_column(Date)
    inflation: Mapped[Decimal] = mapped_column(Numeric(8, 4))        # % ao ano (geral)
    interest: Mapped[Decimal] = mapped_column(Numeric(8, 4))         # taxa básica, % ao ano
    unemployment: Mapped[Decimal] = mapped_column(Numeric(8, 4))     # %
    growth: Mapped[Decimal] = mapped_column(Numeric(8, 4))           # PIB, % ao ano
    demand: Mapped[Decimal] = mapped_column(Numeric(8, 4))           # demanda agregada (100 = normal)
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 4))       # confiança do consumidor 0..100
    monthly_changes: Mapped[dict] = mapped_column(JSON, default=dict)   # categoria -> variação do mês (%)
    indices: Mapped[dict] = mapped_column(JSON, default=dict)           # categoria -> índice acumulado (base 1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorldEvent(Base):
    __tablename__ = "world_events"
    __table_args__ = (
        UniqueConstraint("user_id", "key", "start_month", name="uq_world_event_user_key_start"),
        CheckConstraint("end_month >= start_month", name="ck_world_event_period"),
        Index("ix_world_events_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(400))
    category: Mapped[str] = mapped_column(String(12))            # ECONOMIC | PERSONAL | BUSINESS
    scope: Mapped[str] = mapped_column(String(10))               # WORLD | SECTOR | USER | COMPANY
    sector: Mapped[str | None] = mapped_column(String(32))       # segmento afetado (escopo SECTOR/COMPANY)
    company_id: Mapped[int | None] = mapped_column(Integer)
    positive: Mapped[bool] = mapped_column(default=True)
    intensity: Mapped[int] = mapped_column(Integer, default=1)   # 1 leve, 2 moderada, 3 forte
    start_month: Mapped[date] = mapped_column(Date)
    end_month: Mapped[date] = mapped_column(Date)                # último mês de efeito (inclusive)
    effects: Mapped[dict] = mapped_column(JSON, default=dict)
    # PENDING (aguarda decisão) | ACTIVE | ENDED
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")
    options: Mapped[list] = mapped_column(JSON, default=list)    # decisões: [{key,label,hint}] (resultados não revelados)
    choice: Mapped[str | None] = mapped_column(String(30))
    outcome: Mapped[str | None] = mapped_column(String(300))     # texto do resultado após a decisão
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
