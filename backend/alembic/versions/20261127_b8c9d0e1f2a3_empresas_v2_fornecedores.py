"""empresas v2 (fase 4): fornecedores (contratos por categoria) e categoria nos itens de estoque

Empresas já existentes ganham um contrato ATIVO com o "Fornecedor padrão" em cada categoria do segmento (preço de referência, sem
pedido mínimo prático, volume ilimitado, confiabilidade 100%) para não quebrar; o item de estoque único antigo vira um item por
categoria (mesmo valor em estoque e mesmo custo por venda). Empresas novas NÃO ganham contratos: o jogador precisa procurar.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""
import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory_items", sa.Column("category", sa.String(32), nullable=True))
    op.create_table(
        "company_suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 4), nullable=False),
        sa.Column("reference_price", sa.Numeric(14, 4), nullable=False),
        sa.Column("min_monthly_order", sa.Numeric(16, 3), nullable=False),
        sa.Column("max_units_month", sa.Numeric(16, 3), nullable=False),
        sa.Column("reliability", sa.Numeric(4, 3), nullable=False),
        sa.Column("lead_days", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("status", sa.String(10), nullable=False, server_default="ACTIVE"),
        sa.Column("started_month", sa.Date(), nullable=False),
        sa.Column("ended_month", sa.Date(), nullable=True),
        sa.Column("term_months", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("volume_month", sa.Date(), nullable=True),
        sa.Column("volume_used", sa.Numeric(16, 3), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_company_suppliers_idem"),
        sa.CheckConstraint("status IN ('ACTIVE', 'ENDED')", name="ck_company_suppliers_status"),
        sa.CheckConstraint("unit_price > 0", name="ck_company_suppliers_price"),
    )
    op.create_index("ix_company_suppliers_company_id", "company_suppliers", ["company_id"])
    op.create_index("uq_company_suppliers_active", "company_suppliers", ["company_id", "category"], unique=True,
                    postgresql_where=sa.text("status = 'ACTIVE'"))
    _grant_default_suppliers()


def _grant_default_suppliers() -> None:
    """Dados das empresas existentes (SQL puro; o catálogo de categorias vem das regras do segmento)."""
    from backend.services import company_rules as rules
    from backend.services import company_supply as supply

    conn = op.get_bind()
    companies = conn.execute(sa.text("SELECT id, CAST(segment AS TEXT) AS segment, founded_on FROM companies")).all()
    for cid, segment, founded_on in companies:
        seg = next((s for s in rules.SEGMENTS.values() if s.key.value == segment), None)
        if seg is None or not seg.supply_categories:
            continue
        for cat in seg.supply_categories:
            conn.execute(sa.text(
                "INSERT INTO company_suppliers (company_id, category, name, unit_price, reference_price, min_monthly_order, "
                "max_units_month, reliability, lead_days, status, started_month, term_months, is_default, volume_used) "
                "VALUES (:c, :cat, :name, :p, :p, :mo, :mx, 1, 2, 'ACTIVE', :d, :t, true, 0) ON CONFLICT DO NOTHING"),
                {"c": cid, "cat": cat.key, "name": supply.DEFAULT_SUPPLIER_NAME, "p": cat.ref_price, "mo": supply.LEGACY_MIN_ORDER,
                 "mx": supply.DEFAULT_MAX_UNITS, "d": founded_on, "t": supply.CONTRACT_TERM_MONTHS})
        if not seg.has_stock:
            continue
        legacy = conn.execute(sa.text(
            "SELECT id, quantity, unit_cost, min_quantity, units_per_sale FROM inventory_items WHERE company_id = :c ORDER BY id"),
            {"c": cid}).all()
        if not legacy:
            continue
        labels = [cat.label[:60] for cat in seg.supply_categories]
        names = {r[0] for r in conn.execute(sa.text("SELECT name FROM inventory_items WHERE company_id = :c"), {"c": cid})}
        if all(lb in names for lb in labels):                                  # já convertida (upgrade após downgrade): não duplica
            for cat in seg.supply_categories:
                conn.execute(sa.text("UPDATE inventory_items SET category = :cat WHERE company_id = :c AND name = :name"),
                             {"c": cid, "cat": cat.key, "name": cat.label[:60]})
            continue
        old = legacy[0]
        _rename_colliding(conn, cid, old.id, set(labels))
        total_ref = sum((c.per_sale * c.ref_price for c in seg.supply_categories), rules.D(0))
        factor = (old.unit_cost * old.units_per_sale / total_ref) if total_ref else rules.D(1)       # preço médio pago / referência
        all_vals = []
        for cat in seg.supply_categories:
            all_vals.append({"c": cid, "name": cat.label[:60], "unit": cat.unit[:16], "cat": cat.key, "ups": cat.per_sale, "w": cat.waste_pct,
                             "q": (old.quantity * cat.per_sale / old.units_per_sale).quantize(rules.D("0.001")),
                             "mn": (old.min_quantity * cat.per_sale / old.units_per_sale).quantize(rules.D("0.001")),
                             "uc": (cat.ref_price * factor).quantize(rules.D("0.0001")), "sup": supply.DEFAULT_SUPPLIER_NAME, "id": old.id})
        # o arredondamento do custo unitário (4 casas) distorce preços minúsculos: a última categoria absorve o resíduo para preservar o valor
        target = old.quantity * old.unit_cost
        if len(all_vals) > 1 and all_vals[-1]["uc"] > 0:
            rest = sum((v["q"] * v["uc"] for v in all_vals[:-1]), rules.D(0))
            all_vals[-1]["q"] = max(rules.D(0), (target - rest) / all_vals[-1]["uc"]).quantize(rules.D("0.001"))
        for n, vals in enumerate(all_vals):
            if n == 0:                                                        # o item antigo vira o da 1ª categoria
                conn.execute(sa.text(
                    "UPDATE inventory_items SET name = :name, unit = :unit, category = :cat, units_per_sale = :ups, waste_pct = :w, "
                    "quantity = :q, min_quantity = :mn, unit_cost = :uc, supplier = :sup WHERE id = :id"), vals)
            else:
                conn.execute(sa.text(
                    "INSERT INTO inventory_items (company_id, name, unit, quantity, unit_cost, supplier, min_quantity, units_per_sale, "
                    "waste_pct, category) VALUES (:c, :name, :unit, :q, :uc, :sup, :mn, :ups, :w, :cat) "
                    "ON CONFLICT (company_id, name) DO NOTHING"), vals)


def _rename_colliding(conn, cid: int, keep_id: int, labels: set[str]) -> None:
    """Itens ANTIGOS (que não o convertido) com o nome de uma categoria ganham o sufixo " (antigo)" (<= 60 caracteres), para não
    estourar `uq_inventory_company_name`. O valor em estoque não muda."""
    taken = {r[0] for r in conn.execute(sa.text("SELECT name FROM inventory_items WHERE company_id = :c"), {"c": cid})}
    rows = conn.execute(sa.text("SELECT id, name FROM inventory_items WHERE company_id = :c AND id <> :k ORDER BY id"),
                        {"c": cid, "k": keep_id}).all()
    for iid, name in rows:
        if name not in labels:
            continue
        for suffix in (" (antigo)", f" (antigo {iid})"):
            new = name[:60 - len(suffix)] + suffix
            if new not in taken and new not in labels:
                break
        conn.execute(sa.text("UPDATE inventory_items SET name = :n WHERE id = :i"), {"n": new, "i": iid})
        taken.add(new)


def downgrade() -> None:
    op.drop_index("uq_company_suppliers_active", table_name="company_suppliers")
    op.drop_index("ix_company_suppliers_company_id", table_name="company_suppliers")
    op.drop_table("company_suppliers")
    op.drop_column("inventory_items", "category")
