"""pedido de aumento por emprego: cada emprego tem o seu intervalo de 6 meses

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
"""
from alembic import op

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE career_jobs ADD COLUMN IF NOT EXISTS raise_asked_month DATE")
    # quem já pediu aumento antes: o intervalo vale para os empregos em andamento (comportamento anterior)
    op.execute("""UPDATE career_jobs SET raise_asked_month = lp.raise_asked_month
                  FROM life_profiles lp
                  WHERE lp.user_id = career_jobs.user_id AND lp.raise_asked_month IS NOT NULL
                    AND career_jobs.end_month IS NULL AND career_jobs.raise_asked_month IS NULL""")


def downgrade() -> None:
    op.execute("ALTER TABLE career_jobs DROP COLUMN IF EXISTS raise_asked_month")
