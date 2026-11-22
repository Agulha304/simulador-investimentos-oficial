"""tentar ter um filho: cooldown mensal, recusa recente e contador de tentativas

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
"""
from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE life_profiles ADD COLUMN IF NOT EXISTS last_child_try_month DATE")
    op.execute("ALTER TABLE life_profiles ADD COLUMN IF NOT EXISTS last_child_refusal_month DATE")
    op.execute("ALTER TABLE life_profiles ADD COLUMN IF NOT EXISTS child_tries INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE life_profiles DROP COLUMN IF EXISTS child_tries")
    op.execute("ALTER TABLE life_profiles DROP COLUMN IF EXISTS last_child_refusal_month")
    op.execute("ALTER TABLE life_profiles DROP COLUMN IF EXISTS last_child_try_month")
