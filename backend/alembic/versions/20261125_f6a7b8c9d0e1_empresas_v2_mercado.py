"""empresas v2 (fase 3a): relevância, mudança de endereço e vendas zeradas

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""
import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("relevance", sa.Numeric(5, 2), nullable=False, server_default="0"))
    op.add_column("companies", sa.Column("relocated_on", sa.Date(), nullable=True))
    op.add_column("company_months", sa.Column("relevance_end", sa.Numeric(5, 2), nullable=False, server_default="0"))
    op.add_column("company_months", sa.Column("zero_sales", sa.Boolean(), nullable=False, server_default="false"))
    # empresas que já existiam não recomeçam do zero: entram com relevância média (as novas começam em 0)
    op.execute("UPDATE companies SET relevance = 30")


def downgrade() -> None:
    op.drop_column("company_months", "zero_sales")
    op.drop_column("company_months", "relevance_end")
    op.drop_column("companies", "relocated_on")
    op.drop_column("companies", "relevance")
