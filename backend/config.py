"""Configuração central lida do ambiente / arquivo .env na raiz do projeto."""
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # "production" liga as checagens de segurança de check_production() (segredo JWT forte etc.)
    environment: str = "development"

    database_url: str = "postgresql+psycopg://simulador@localhost:5433/simulador"
    test_database_url: str = "postgresql+psycopg://simulador@localhost:5433/simulador_test"

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720

    initial_balance: Decimal = Decimal("100000.00")
    scheduler_enabled: bool = True
    risk_check_interval_seconds: int = 120   # Stop Loss / Take Profit

    # Usados SOMENTE se ainda não houver dados dos índices no banco (primeira execução / sem rede).
    fallback_cdi_annual: Decimal = Decimal("13.65")     # % a.a.
    fallback_selic_annual: Decimal = Decimal("13.75")   # % a.a.
    fallback_ipca_monthly: Decimal = Decimal("0.40")    # % a.m.
    fallback_igpm_monthly: Decimal = Decimal("0.40")    # % a.m.

    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    @field_validator("database_url", "test_database_url", mode="before")
    @classmethod
    def _use_psycopg_driver(cls, v):
        """Provedores (Render, Neon, Railway...) entregam postgres:// ou postgresql://; o SQLAlchemy precisa do driver."""
        if isinstance(v, str):
            for prefix in ("postgres://", "postgresql://"):
                if v.startswith(prefix):
                    return "postgresql+psycopg://" + v[len(prefix):]
        return v

    def check_production(self) -> None:
        """Em produção, recusa subir com configuração insegura."""
        if self.environment.lower() != "production":
            return
        weak = {"dev-secret-change-me", "troque-este-valor", ""}
        if self.jwt_secret in weak or len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET fraco ou padrão: defina um segredo aleatório com 32+ caracteres "
                               "(python -c \"import secrets; print(secrets.token_urlsafe(48))\").")
        if "localhost" in self.database_url or "127.0.0.1" in self.database_url:
            raise RuntimeError("DATABASE_URL aponta para localhost em produção.")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
