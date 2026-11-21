"""empresas v2 (fase 1): canal, terreno e remoção de business_type

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # empresas existentes: ponto físico alugado (como já funcionavam); localizações antigas continuam válidas
    # (resolvidas em company_rules.resolve_location para o local equivalente do segmento).
    op.add_column("companies", sa.Column(
        "channel", sa.Enum("ONLINE", "PHYSICAL", name="company_channel", native_enum=False, create_constraint=True, length=32),
        nullable=False, server_default="PHYSICAL"))
    op.add_column("companies", sa.Column(
        "site_mode", sa.Enum("BUY", "RENT", name="company_site_mode", native_enum=False, create_constraint=True, length=32),
        nullable=True))
    op.add_column("companies", sa.Column("site_value", sa.Numeric(20, 2), nullable=False, server_default="0"))
    op.execute("UPDATE companies SET site_mode = 'RENT'")
    op.drop_column("companies", "business_type")


def downgrade() -> None:
    op.add_column("companies", sa.Column("business_type", sa.String(length=60), nullable=False, server_default=""))
    op.drop_column("companies", "site_value")
    op.drop_column("companies", "site_mode")
    op.drop_column("companies", "channel")
