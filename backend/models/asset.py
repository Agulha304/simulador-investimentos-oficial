from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.enums import AssetClass, Currency
from backend.models.types import StrEnumType


class Asset(Base):
    """Ativo negociável de mercado (ações, ETFs, FIIs, REITs, cripto...).

    Uma única tabela para todas as classes; o que for específico de um tipo
    vai em `extra` (JSONB). Renda fixa terá modelo próprio (FixedIncomeProduct),
    pois sua dinâmica (fluxo de caixa, indexador, liquidez) é diferente.
    """

    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("symbol", "exchange", name="uq_asset_symbol_exchange"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)          # ex.: PETR4, AAPL, BTC
    name: Mapped[str] = mapped_column(String(200))
    asset_class: Mapped[AssetClass] = mapped_column(StrEnumType(AssetClass, "asset_class"), index=True)
    exchange: Mapped[str] = mapped_column(String(32))                    # B3, NASDAQ, NYSE, CRYPTO
    country: Mapped[str | None] = mapped_column(String(2))               # BR, US
    currency: Mapped[Currency] = mapped_column(StrEnumType(Currency, "currency"))
    provider_symbol: Mapped[str] = mapped_column(String(64))             # símbolo na fonte de dados (PETR4.SA, BTC-USD)
    allows_fractional: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
