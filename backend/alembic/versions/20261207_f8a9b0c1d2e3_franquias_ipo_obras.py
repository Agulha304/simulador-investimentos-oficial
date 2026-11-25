"""franquias, abertura de capital (IPO) e imóveis com prazo (escritura/obra)

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""
from alembic import op

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE goods ADD COLUMN IF NOT EXISTS available_month DATE")
    op.execute("ALTER TABLE goods ADD COLUMN IF NOT EXISTS construction_plan VARCHAR(40)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS franchise_appeal NUMERIC(5,2) NOT NULL DEFAULT 0")
    op.execute("""
        CREATE TABLE IF NOT EXISTS company_franchises (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(80) NOT NULL,
            location VARCHAR(32) NOT NULL,
            status VARCHAR(8) NOT NULL DEFAULT 'OPEN',
            signed_month DATE NOT NULL,
            opens_month DATE NOT NULL,
            viability NUMERIC(4,3) NOT NULL DEFAULT 1,
            royalty_pct NUMERIC(5,2) NOT NULL,
            initial_fee NUMERIC(14,2) NOT NULL DEFAULT 0,
            total_royalties NUMERIC(14,2) NOT NULL DEFAULT 0,
            closed_month DATE,
            closed_reason VARCHAR(160),
            CONSTRAINT ck_company_franchises_status CHECK (status IN ('OPEN', 'CLOSED'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_company_franchises_company_status ON company_franchises (company_id, status)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS company_listings (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            ticker VARCHAR(8) NOT NULL,
            status VARCHAR(10) NOT NULL DEFAULT 'PENDING',
            shares_total BIGINT NOT NULL DEFAULT 0,
            float_pct NUMERIC(5,2) NOT NULL,
            valuation NUMERIC(14,2) NOT NULL DEFAULT 0,
            ipo_price NUMERIC(14,4) NOT NULL DEFAULT 0,
            price NUMERIC(14,4) NOT NULL DEFAULT 0,
            proceeds NUMERIC(14,2) NOT NULL DEFAULT 0,
            applied_month DATE NOT NULL,
            lists_month DATE NOT NULL,
            listed_month DATE,
            prev_owner_share NUMERIC(5,2) NOT NULL DEFAULT 100,
            history JSON NOT NULL DEFAULT '[]',
            CONSTRAINT uq_company_listings_company UNIQUE (company_id),
            CONSTRAINT ck_company_listings_status CHECK (status IN ('PENDING', 'LISTED', 'DELISTED'))
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS company_listings")
    op.execute("DROP TABLE IF EXISTS company_franchises")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS franchise_appeal")
    op.execute("ALTER TABLE goods DROP COLUMN IF EXISTS construction_plan")
    op.execute("ALTER TABLE goods DROP COLUMN IF EXISTS available_month")
