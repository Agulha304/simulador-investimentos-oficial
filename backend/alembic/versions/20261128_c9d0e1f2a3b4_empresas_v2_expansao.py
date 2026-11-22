"""empresas v2 (fase 5): expansão em níveis, filiais (`company_units`), qualidade, campanhas, imprevistos

- `companies`: marketing_boost, capacity_boost (níveis efetivos; empresas antigas: = capacity_level), storage_boost, quality (50),
  suspended_until (despejo), incident_shield_until (conserto premium).
- `company_months.units_detail`: resultado do mês por unidade.
- `company_units`: filiais. Empresas antigas com `units` > 1 ganham (units - 1) filiais abertas equivalentes às "unidades" do modelo
  anterior (mesmo local e relevância da empresa, viabilidade 1, aluguel = o aluguel de referência (`default_rent`) do segmento/local/porte da empresa: o modelo antigo cobrava o contrato
  + default_rent x (units - 1), então o total é preservado).
- `company_expansions`: aportes executados (resultado para a idempotência).

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""
import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("marketing_boost", sa.Numeric(5, 3), nullable=False, server_default="0.12"))
    op.add_column("companies", sa.Column("capacity_boost", sa.Numeric(5, 3), nullable=False, server_default="0"))
    op.add_column("companies", sa.Column("storage_boost", sa.Numeric(5, 3), nullable=False, server_default="0"))
    op.add_column("companies", sa.Column("quality", sa.Numeric(5, 2), nullable=False, server_default="50"))
    op.add_column("companies", sa.Column("suspended_until", sa.Date(), nullable=True))
    op.add_column("companies", sa.Column("incident_shield_until", sa.Date(), nullable=True))
    op.execute("UPDATE companies SET capacity_boost = capacity_level")
    op.add_column("company_months", sa.Column("units_detail", sa.JSON(), nullable=True))
    op.create_table(
        "company_units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False, server_default="BRANCH"),
        sa.Column("name", sa.String(80), nullable=False, server_default=""),
        sa.Column("location", sa.String(32), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False, server_default="PHYSICAL"),
        sa.Column("site_mode", sa.String(20), nullable=True),
        sa.Column("site_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("monthly_rent", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("relevance", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("viability", sa.Numeric(4, 3), nullable=False, server_default="1"),
        sa.Column("status", sa.String(8), nullable=False, server_default="OPEN"),
        sa.Column("opened_month", sa.Date(), nullable=False),
        sa.Column("closed_month", sa.Date(), nullable=True),
        sa.Column("closed_reason", sa.String(160), nullable=True),
        sa.Column("cumulative_result", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("investment", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_company_units_status"),
        sa.CheckConstraint("kind IN ('HQ', 'BRANCH')", name="ck_company_units_kind"),
    )
    op.create_index("ix_company_units_company_status", "company_units", ["company_id", "status"])
    op.create_table(
        "company_expansions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("ref_month", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("tier", sa.String(8), nullable=False),
        sa.Column("option_key", sa.String(40), nullable=False),
        sa.Column("outcome", sa.String(8), nullable=False),
        sa.Column("cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("message", sa.String(400), nullable=False),
        sa.Column("effects", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_company_expansions_idem"),
    )
    op.create_index("ix_company_expansions_company_id", "company_expansions", ["company_id"])
    # unidades do modelo antigo (contador `units`) viram filiais equivalentes
    _convert_legacy_units()


def _convert_legacy_units() -> None:
    from backend.services import company_rules as rules

    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, CAST(segment AS TEXT), location, CAST(channel AS TEXT), CAST(size AS TEXT), units, relevance, "
        "COALESCE(last_processed_month, founded_on) FROM companies WHERE units > 1")).all()
    for cid, segment, location, channel, size, units, relevance, opened in rows:
        seg = next((x for x in rules.SEGMENTS.values() if x.key.value == segment), None)
        try:
            rent = rules.default_rent(seg, location, rules.CompanySize(size)) if seg else rules.D(0)
        except Exception:                                                  # dado legado imprevisto: não derruba a migration
            rent = rules.D(0)
        for n in range(1, units):
            conn.execute(sa.text(
                "INSERT INTO company_units (company_id, kind, name, location, channel, site_mode, site_value, monthly_rent, relevance, "
                "viability, status, opened_month, cumulative_result, investment) "
                "VALUES (:c, 'BRANCH', :n, :loc, :ch, NULL, 0, :rent, :rel, 1, 'OPEN', :op, 0, 0)"),
                {"c": cid, "n": f"Filial {n + 1}", "loc": location, "ch": channel, "rent": rent, "rel": relevance, "op": opened})


def downgrade() -> None:
    op.drop_table("company_expansions")
    op.drop_index("ix_company_units_company_status", table_name="company_units")
    op.drop_table("company_units")
    op.drop_column("company_months", "units_detail")
    for col in ("incident_shield_until", "suspended_until", "quality", "storage_boost", "capacity_boost", "marketing_boost"):
        op.drop_column("companies", col)
