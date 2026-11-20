"""liga RLS em todas as tabelas (Supabase expõe o schema public pela API: sem RLS e sem políticas, a chave pública não lê nada)

Revision ID: c0ffee5afe01
Revises: be45d0100415
"""
from alembic import op

revision = "c0ffee5afe01"
down_revision = "be45d0100415"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ DECLARE t record; BEGIN
          FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
          END LOOP;
        END $$;
    """)


def downgrade() -> None:
    pass
