"""Mundo (país, câmbio, intercâmbio) e aquisições de empresas."""
from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, CheckConstraint, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.types import Money


class Exchange(Base):
    """Intercâmbio do personagem: país, programa, prazo e o que ele custa (convertido pelo câmbio de cada mês)."""

    __tablename__ = "life_exchanges"
    __table_args__ = (CheckConstraint("status IN ('ACTIVE', 'DONE', 'CANCELED')", name="ck_life_exchanges_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    program_key: Mapped[str] = mapped_column(String(40))
    country: Mapped[str] = mapped_column(String(2))
    field: Mapped[str] = mapped_column(String(20))                           # área do currículo ("geral" = pontos gerais)
    months_total: Mapped[int] = mapped_column(Integer)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE", server_default="ACTIVE")
    start_month: Mapped[date] = mapped_column(Date)
    end_month: Mapped[date | None] = mapped_column(Date)
    upfront_brl: Mapped[Decimal] = mapped_column(Money(), default=0)         # passagem, visto, seguro e instalação, já pagos
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class AcquisitionDeal(Base):
    """Negociação para comprar uma empresa. `target` = ficha da empresa-alvo (sorteada pela semente do jogo); `ask` = o que o dono pede agora."""

    __tablename__ = "acquisition_deals"
    __table_args__ = (
        UniqueConstraint("user_id", "target_key", name="uq_acquisition_deals_target"),
        CheckConstraint("status IN ('OPEN', 'DONE', 'WALKED')", name="ck_acquisition_deals_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target_key: Mapped[str] = mapped_column(String(60))
    target: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(8), default="OPEN", server_default="OPEN")
    rounds: Mapped[int] = mapped_column(Integer, default=0)
    ask: Mapped[Decimal] = mapped_column(Money())
    last_offer: Mapped[Decimal | None] = mapped_column(Money())
    first_month: Mapped[date] = mapped_column(Date)
    closed_month: Mapped[date | None] = mapped_column(Date)
    price: Mapped[Decimal | None] = mapped_column(Money())
    buyer_company_id: Mapped[int | None] = mapped_column(Integer)
    log: Mapped[list] = mapped_column(JSON, default=list)
