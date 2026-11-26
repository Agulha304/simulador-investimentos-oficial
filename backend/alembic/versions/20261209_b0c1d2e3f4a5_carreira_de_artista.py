"""carreira de artista: perfil e itens (canais, bandas, obras, contratos, decisões e pagamentos)

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
"""
from alembic import op

revision = "b0c1d2e3f4a5"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS artist_profiles (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            instrument VARCHAR(20),
            skills JSON NOT NULL DEFAULT '{}',
            fame JSON NOT NULL DEFAULT '{}',
            data JSON NOT NULL DEFAULT '{}',
            CONSTRAINT uq_artist_profiles_user UNIQUE (user_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS artist_items (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind VARCHAR(10) NOT NULL,
            status VARCHAR(12) NOT NULL DEFAULT 'ACTIVE',
            name VARCHAR(120) NOT NULL DEFAULT '',
            created_month DATE NOT NULL,
            data JSON NOT NULL DEFAULT '{}'
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_artist_items_user_kind ON artist_items (user_id, kind, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS artist_items")
    op.execute("DROP TABLE IF EXISTS artist_profiles")
