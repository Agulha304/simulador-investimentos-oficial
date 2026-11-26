"""CEO como profissional de apoio da empresa

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
"""
from alembic import op

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE company_aides DROP CONSTRAINT IF EXISTS ck_company_aides_kind")
    op.execute("ALTER TABLE company_aides ADD CONSTRAINT ck_company_aides_kind CHECK (kind IN ('MARKETER', 'MANAGER', 'CEO'))")


def downgrade() -> None:
    op.execute("DELETE FROM company_aides WHERE kind = 'CEO'")
    op.execute("ALTER TABLE company_aides DROP CONSTRAINT IF EXISTS ck_company_aides_kind")
    op.execute("ALTER TABLE company_aides ADD CONSTRAINT ck_company_aides_kind CHECK (kind IN ('MARKETER', 'MANAGER'))")
