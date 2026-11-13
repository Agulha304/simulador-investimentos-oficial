from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class ChartLayout(Base):
    """Preferências do gráfico de um usuário para um ativo: indicadores escolhidos e
    desenhos (linhas de tendência, suportes etc.), ancorados em tempo (unix s) e preço."""

    __tablename__ = "chart_layouts"
    __table_args__ = (UniqueConstraint("user_id", "asset_id", name="uq_chart_layout_user_asset"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    indicators: Mapped[list] = mapped_column(JSONB, default=list)
    drawings: Mapped[list] = mapped_column(JSONB, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
