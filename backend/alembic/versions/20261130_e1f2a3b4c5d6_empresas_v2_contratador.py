"""empresas v2: contratador (headhunter) opcional, histórico trabalhista e limites de contrato de fornecedor

Tudo ADITIVO e seguro para dados existentes (colunas com default/NULL; tabelas novas) e REAPLICÁVEL (cada passo confere se já existe).
- `employees.lawsuit_history` (0 = sem processos anteriores; funcionários antigos ficam em 0).
- `company_suppliers`: max_monthly_spend, volume_cap, min_reliability, max_lead_days (NULL = sem limite) e spend_used (gasto do mês).
- `company_recruiters` (um por empresa) e `company_recruiter_runs` (relatórios idempotentes das operações do contratador).

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""
import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _add(table: str, column: sa.Column) -> None:
    if column.name not in _cols(table):
        op.add_column(table, column)


def upgrade() -> None:
    _add("employees", sa.Column("lawsuit_history", sa.Integer(), nullable=False, server_default="0"))
    _add("company_suppliers", sa.Column("max_monthly_spend", sa.Numeric(16, 2), nullable=True))
    _add("company_suppliers", sa.Column("volume_cap", sa.Numeric(16, 3), nullable=True))
    _add("company_suppliers", sa.Column("min_reliability", sa.Numeric(4, 3), nullable=True))
    _add("company_suppliers", sa.Column("max_lead_days", sa.Integer(), nullable=True))
    _add("company_suppliers", sa.Column("spend_used", sa.Numeric(16, 2), nullable=False, server_default="0"))
    if "company_recruiters" not in _tables():
        op.create_table(
            "company_recruiters",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("tier", sa.String(8), nullable=False),
            sa.Column("status", sa.String(8), nullable=False, server_default="ACTIVE"),
            sa.Column("hired_month", sa.Date(), nullable=False),
            sa.Column("ended_month", sa.Date(), nullable=True),
            sa.Column("settings", sa.JSON(), nullable=True),
            sa.Column("last_key", sa.String(100), nullable=True),
            sa.UniqueConstraint("company_id", name="uq_company_recruiters_company"),
            sa.CheckConstraint("tier IN ('BASIC', 'PRO', 'ELITE')", name="ck_company_recruiters_tier"),
            sa.CheckConstraint("status IN ('ACTIVE', 'ENDED')", name="ck_company_recruiters_status"),
        )
    if "company_recruiter_runs" not in _tables():
        op.create_table(
            "company_recruiter_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("idempotency_key", sa.String(100), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("ref_month", sa.Date(), nullable=False),
            sa.Column("report", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("company_id", "idempotency_key", name="uq_company_recruiter_runs_idem"),
        )


def downgrade() -> None:
    op.drop_table("company_recruiter_runs")
    op.drop_table("company_recruiters")
    for col in ("spend_used", "max_lead_days", "min_reliability", "volume_cap", "max_monthly_spend"):
        op.drop_column("company_suppliers", col)
    op.drop_column("employees", "lawsuit_history")
