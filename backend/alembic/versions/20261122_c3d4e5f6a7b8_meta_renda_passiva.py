"""meta de renda passiva mensal no perfil de investidor

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""
import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE investor_profiles ADD COLUMN IF NOT EXISTS passive_goal NUMERIC(20, 2)")


def downgrade() -> None:
    op.execute("ALTER TABLE investor_profiles DROP COLUMN IF EXISTS passive_goal")
