"""esqueci minha senha: tokens de redefinição (somente hash) e registro de pedidos p/ rate limit

Tudo ADITIVO e REAPLICÁVEL (confere se a tabela já existe).

Revision ID: a3b4c5d6e7f8
Revises: e1f2a3b4c5d6
"""
import sqlalchemy as sa
from alembic import op

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "password_reset_tokens" not in _tables():
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("request_ip", sa.String(64), nullable=True),
        )
        op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    if "password_reset_requests" not in _tables():
        op.create_table(
            "password_reset_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("key_hash", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_password_reset_requests_key_created", "password_reset_requests", ["key_hash", "created_at"])


def downgrade() -> None:
    op.drop_table("password_reset_requests")
    op.drop_table("password_reset_tokens")
