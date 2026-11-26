"""mundo: países/câmbio, faculdades reais, intercâmbio, trabalho remoto e compra de empresas

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
"""
from alembic import op

revision = "a9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE life_profiles ADD COLUMN IF NOT EXISTS degree_uni VARCHAR(24)")
    op.execute("ALTER TABLE life_profiles ADD COLUMN IF NOT EXISTS degree_unis JSON NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE life_profiles ADD COLUMN IF NOT EXISTS uni_attempts JSON NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE life_profiles ADD COLUMN IF NOT EXISTS country VARCHAR(2) NOT NULL DEFAULT 'BR'")
    op.execute("ALTER TABLE life_profiles ADD COLUMN IF NOT EXISTS abroad_since DATE")
    op.execute("ALTER TABLE life_profiles ADD COLUMN IF NOT EXISTS one_offs JSON NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE career_jobs ADD COLUMN IF NOT EXISTS country VARCHAR(2) NOT NULL DEFAULT 'BR'")
    op.execute("ALTER TABLE career_jobs ADD COLUMN IF NOT EXISTS work_mode VARCHAR(6) NOT NULL DEFAULT 'ONSITE'")
    op.execute("ALTER TABLE career_jobs ADD COLUMN IF NOT EXISTS net_local NUMERIC(14,2)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS country VARCHAR(2) NOT NULL DEFAULT 'BR'")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS acquired_from VARCHAR(80)")
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS work_mode VARCHAR(6) NOT NULL DEFAULT 'ONSITE'")
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS country VARCHAR(2) NOT NULL DEFAULT 'BR'")
    op.execute("""
        CREATE TABLE IF NOT EXISTS life_exchanges (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            program_key VARCHAR(40) NOT NULL,
            country VARCHAR(2) NOT NULL,
            field VARCHAR(20) NOT NULL,
            months_total INTEGER NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            points INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(10) NOT NULL DEFAULT 'ACTIVE',
            start_month DATE NOT NULL,
            end_month DATE,
            upfront_brl NUMERIC(14,2) NOT NULL DEFAULT 0,
            detail JSON NOT NULL DEFAULT '{}',
            CONSTRAINT ck_life_exchanges_status CHECK (status IN ('ACTIVE', 'DONE', 'CANCELED'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_life_exchanges_user_id ON life_exchanges (user_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS acquisition_deals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            target_key VARCHAR(60) NOT NULL,
            target JSON NOT NULL,
            status VARCHAR(8) NOT NULL DEFAULT 'OPEN',
            rounds INTEGER NOT NULL DEFAULT 0,
            ask NUMERIC(14,2) NOT NULL,
            last_offer NUMERIC(14,2),
            first_month DATE NOT NULL,
            closed_month DATE,
            price NUMERIC(14,2),
            buyer_company_id INTEGER,
            log JSON NOT NULL DEFAULT '[]',
            CONSTRAINT uq_acquisition_deals_target UNIQUE (user_id, target_key),
            CONSTRAINT ck_acquisition_deals_status CHECK (status IN ('OPEN', 'DONE', 'WALKED'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_acquisition_deals_user_id ON acquisition_deals (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS acquisition_deals")
    op.execute("DROP TABLE IF EXISTS life_exchanges")
    for t, cols in (("employees", ("country", "work_mode")), ("companies", ("acquired_from", "country")),
                    ("career_jobs", ("net_local", "work_mode", "country")),
                    ("life_profiles", ("one_offs", "abroad_since", "country", "uni_attempts", "degree_unis", "degree_uni"))):
        for c in cols:
            op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS {c}")
