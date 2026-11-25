"""prazos de abertura e obra: empresas e filiais só operam a partir de um mês

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
"""
from alembic import op

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS opens_month DATE")
    op.execute("ALTER TABLE company_units ADD COLUMN IF NOT EXISTS opens_month DATE")


def downgrade() -> None:
    op.execute("ALTER TABLE company_units DROP COLUMN IF EXISTS opens_month")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS opens_month")
