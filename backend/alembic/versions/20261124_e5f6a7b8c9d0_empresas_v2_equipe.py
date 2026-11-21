"""empresas v2 (fase 2): equipe (regime, escala, escolaridade), candidatos bloqueados e conformidade

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

EVENT_TYPES = ["CREATED", "CAPITAL", "HIRE", "FIRE", "STOCK", "EXPANSION", "LEASE", "LOAN", "DISTRIBUTION", "EQUIPMENT", "SETTINGS",
               "MONTH", "CLOSED"]


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def upgrade() -> None:
    # funcionários existentes: CLT, escala 5x2, ensino médio, sem anos de experiência registrados e sem nome
    op.add_column("employees", sa.Column("name", sa.String(80), nullable=False, server_default=""))
    op.add_column("employees", sa.Column("regime", _enum("employee_regime", "CLT", "PJ"), nullable=False, server_default="CLT"))
    op.add_column("employees", sa.Column("schedule", _enum("employee_schedule", "6x1", "5x2", "12x36", "4x3"),
                                         nullable=False, server_default="5x2"))
    op.add_column("employees", sa.Column("education", _enum("employee_education", "FUNDAMENTAL", "MEDIO", "TECNICO", "SUPERIOR", "POS"),
                                         nullable=False, server_default="MEDIO"))
    op.add_column("employees", sa.Column("experience_years", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "company_candidate_blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.String(80), nullable=False),
        sa.Column("ref_month", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(10), nullable=False),
        sa.UniqueConstraint("company_id", "candidate_id", name="uq_candidate_block"),
    )
    op.create_index("ix_company_candidate_blocks_company_id", "company_candidate_blocks", ["company_id"])
    op.add_column("company_months", sa.Column("irregular", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("company_months", sa.Column("fines", sa.Numeric(20, 2), nullable=False, server_default="0"))
    # novo tipo de evento da linha do tempo: COMPLIANCE (CHECK de enum não nativo precisa ser recriado)
    op.drop_constraint("company_event_type", "company_events", type_="check")
    op.create_check_constraint("company_event_type", "company_events",
                               "type IN (" + ", ".join(f"'{v}'" for v in EVENT_TYPES + ["COMPLIANCE"]) + ")")


def downgrade() -> None:
    op.execute("DELETE FROM company_events WHERE type = 'COMPLIANCE'")
    op.drop_constraint("company_event_type", "company_events", type_="check")
    op.create_check_constraint("company_event_type", "company_events", "type IN (" + ", ".join(f"'{v}'" for v in EVENT_TYPES) + ")")
    op.drop_column("company_months", "fines")
    op.drop_column("company_months", "irregular")
    op.drop_index("ix_company_candidate_blocks_company_id", table_name="company_candidate_blocks")
    op.drop_table("company_candidate_blocks")
    for col in ("experience_years", "education", "schedule", "regime", "name"):
        op.drop_column("employees", col)
