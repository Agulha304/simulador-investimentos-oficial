"""Carreira de artista: perfil (instrumento, habilidades, fama) e itens (canais, bandas, obras, contratos, decisões, pagamentos)."""
from datetime import date

from sqlalchemy import JSON, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class ArtistProfile(Base):
    __tablename__ = "artist_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_artist_profiles_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    instrument: Mapped[str | None] = mapped_column(String(20))
    skills: Mapped[dict] = mapped_column(JSON, default=dict)          # music, acting, painting, influencer (0..100)
    fame: Mapped[dict] = mapped_column(JSON, default=dict)            # idem
    data: Mapped[dict] = mapped_column(JSON, default=dict)            # aplicações do mês etc.


class ArtistItem(Base):
    """kind: CHANNEL | BAND | WORK | JOB | OFFER | DECISION | PAYOUT | APP. `data` guarda os detalhes de cada tipo."""
    __tablename__ = "artist_items"
    __table_args__ = (Index("ix_artist_items_user_kind", "user_id", "kind", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    name: Mapped[str] = mapped_column(String(120), default="")
    created_month: Mapped[date] = mapped_column(Date)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
