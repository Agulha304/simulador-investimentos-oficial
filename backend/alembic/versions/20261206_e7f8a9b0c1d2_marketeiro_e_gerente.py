"""marketeiro e gerente opcionais das empresas

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
"""
from alembic import op

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS company_aides (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            kind VARCHAR(10) NOT NULL,
            level VARCHAR(6) NOT NULL,
            status VARCHAR(8) NOT NULL DEFAULT 'ACTIVE',
            hired_month DATE NOT NULL,
            ended_month DATE,
            settings JSON NOT NULL DEFAULT '{}',
            CONSTRAINT uq_company_aides_company_kind UNIQUE (company_id, kind),
            CONSTRAINT ck_company_aides_kind CHECK (kind IN ('MARKETER', 'MANAGER')),
            CONSTRAINT ck_company_aides_level CHECK (level IN ('LOW', 'MID', 'HIGH')),
            CONSTRAINT ck_company_aides_status CHECK (status IN ('ACTIVE', 'ENDED'))
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS company_aides")
