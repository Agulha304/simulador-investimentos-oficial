"""extensao unaccent

Revision ID: 0c1c86075cfb
Revises: b29292c608db
Create Date: 2026-11-13 18:06:43.230354
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0c1c86075cfb'
down_revision: str | None = 'b29292c608db'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")


def downgrade() -> None:
    pass  # extensão mantida: pode ser usada por outros objetos
