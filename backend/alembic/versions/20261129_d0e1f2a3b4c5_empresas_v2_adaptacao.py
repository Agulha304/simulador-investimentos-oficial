"""empresas v2: período de adaptação de conformidade (`companies.compliance_grace_months`)

Empresas ATIVAS já existentes ganham 3 meses de tolerância (sem zerar vendas nem multa por falta de Contador/Advogado/Limpeza,
só aviso). Empresas novas começam com 0.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""
import sqlalchemy as sa
from alembic import op

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("compliance_grace_months", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE companies SET compliance_grace_months = 3 WHERE CAST(status AS TEXT) = 'ACTIVE'")


def downgrade() -> None:
    op.drop_column("companies", "compliance_grace_months")
