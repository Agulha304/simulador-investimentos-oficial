"""empresas v2: novo segmento AGRIBUSINESS (Agronegócio)

`companies.segment` é um Enum NÃO nativo (VARCHAR + CHECK `company_segment`): o CHECK precisa ser recriado com o novo valor.
ADITIVO e REAPLICÁVEL: usa DROP CONSTRAINT IF EXISTS e recria o CHECK com a lista completa; nenhuma linha existente é alterada.
(Os valores de contratos de fornecedores, briefing do contratador e demais campos não mudam: nada nas colunas de fornecedores é tocado.)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
"""
from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None

SEGMENTS = ["RESTAURANT", "CAFE", "CLOTHING", "SUPERMARKET", "WORKSHOP", "TECH", "AGENCY", "INDUSTRY", "CONSTRUCTION", "TRANSPORT",
            "REAL_ESTATE_AGENCY", "ECOMMERCE"]


def _recreate(values: list[str]) -> None:
    op.execute("ALTER TABLE companies DROP CONSTRAINT IF EXISTS company_segment")
    op.create_check_constraint("company_segment", "companies", "segment IN (" + ", ".join(f"'{v}'" for v in values) + ")")


def upgrade() -> None:
    _recreate(SEGMENTS + ["AGRIBUSINESS"])


def downgrade() -> None:
    op.execute("DELETE FROM companies WHERE segment = 'AGRIBUSINESS'")
    _recreate(SEGMENTS)
