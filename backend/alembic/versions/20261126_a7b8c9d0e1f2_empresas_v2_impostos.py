"""empresas v2 (fase 3b): impostos reais (regime e detalhamento por tributo no demonstrativo mensal)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""
import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # meses antigos ficam NULL (sem detalhamento); o regime das empresas antigas é tratado como Simples no código
    op.add_column("company_months", sa.Column("tax_regime", sa.String(20), nullable=True))
    op.add_column("company_months", sa.Column("tax_breakdown", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("company_months", "tax_breakdown")
    op.drop_column("company_months", "tax_regime")
