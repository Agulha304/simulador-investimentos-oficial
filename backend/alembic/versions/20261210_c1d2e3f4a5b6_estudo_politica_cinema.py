"""atributo de estudo e horas de estudo por dia

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
"""
from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE life_profiles ADD COLUMN IF NOT EXISTS study DOUBLE PRECISION NOT NULL DEFAULT 20")
    op.execute("ALTER TABLE life_profiles ADD COLUMN IF NOT EXISTS study_hours_day DOUBLE PRECISION NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE life_profiles DROP COLUMN IF EXISTS study_hours_day")
    op.execute("ALTER TABLE life_profiles DROP COLUMN IF EXISTS study")
