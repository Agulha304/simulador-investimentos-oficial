"""indices de performance: taken_at, transactions(asset_id, created_at) e FKs sem indice

Revision ID: a1b2c3d4e5f6
Revises: c0ffee5afe01
"""
import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "c0ffee5afe01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_snapshot_taken_at ON portfolio_snapshots (taken_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_snapshot_portfolio_taken_desc ON portfolio_snapshots (portfolio_id, taken_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_transactions_asset_created ON transactions (asset_id, created_at)")
    # Postgres não indexa FKs sozinho: cria índice para toda FK cuja coluna inicial ainda não é coberta por um índice.
    insp = sa.inspect(op.get_bind())
    for table in insp.get_table_names():
        indexed = {ix["column_names"][0] for ix in insp.get_indexes(table) if ix["column_names"]}
        for uc in insp.get_unique_constraints(table):
            indexed.add(uc["column_names"][0])
        pk = insp.get_pk_constraint(table).get("constrained_columns") or []
        if pk:
            indexed.add(pk[0])
        for fk in insp.get_foreign_keys(table):
            col = fk["constrained_columns"][0]
            if col not in indexed:
                op.execute(f'CREATE INDEX IF NOT EXISTS ix_{table}_{col}_fk ON "{table}" ("{col}")')
                indexed.add(col)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_snapshot_taken_at")
    op.execute("DROP INDEX IF EXISTS ix_snapshot_portfolio_taken_desc")
    op.execute("DROP INDEX IF EXISTS ix_transactions_asset_created")
