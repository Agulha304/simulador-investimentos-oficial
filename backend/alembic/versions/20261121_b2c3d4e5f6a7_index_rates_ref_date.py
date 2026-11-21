"""indice em index_rates(ref_date): a unique (index_name, ref_date) começa por index_name e não atende filtros só por data

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_index_rates_ref_date ON index_rates (ref_date)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_index_rates_ref_date")
