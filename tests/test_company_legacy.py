"""Empresas legadas: conversão do estoque com nomes duplicados, período de adaptação de conformidade e localização inválida."""
import importlib.util
from decimal import Decimal

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text

from backend.config import ROOT_DIR
from backend.database import engine
from backend.models import Company, Employee, EmployeeStatus, InventoryItem
from backend.services import company_rules
from tests.test_companies import C, close, create_ok, detail, rich  # noqa: F401  (rich = fixture)

D = Decimal


def _load_migration():
    path = next((ROOT_DIR / "backend" / "alembic" / "versions").glob("*_b8c9d0e1f2a3_*.py"))
    spec = importlib.util.spec_from_file_location("mig_b8c9", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_conversion(mod):
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod._grant_default_suppliers()


def test_supplier_migration_handles_duplicate_stock_names_and_is_reapplicable(client, rich, db):
    cid = create_ok(client, rich, staff=False, name="Sabor Legado", segment="RESTAURANT")["company"]["id"]
    seg = company_rules.SEGMENTS[db.get(Company, cid).segment]
    labels = [c.label for c in seg.supply_categories]
    assert "Bebidas" in labels
    # estado legado: sem fornecedores nem categorias; 1 item "Insumos" + itens antigos com nomes de categorias
    db.execute(text("DELETE FROM company_suppliers WHERE company_id = :c"), {"c": cid})
    db.execute(text("DELETE FROM inventory_items WHERE company_id = :c"), {"c": cid})
    for name, qty, cost in [("Insumos", 1000, "28.5"), ("Bebidas", 50, "6"), (labels[-1], 80, "1")]:
        db.execute(text("INSERT INTO inventory_items (company_id, name, unit, quantity, unit_cost, supplier, min_quantity, units_per_sale, "
                        "waste_pct) VALUES (:c, :n, 'un', :q, :u, 'X', 10, 1, 0)"), {"c": cid, "n": name, "q": qty, "u": cost})
    db.commit()
    total = db.scalar(text("SELECT sum(quantity * unit_cost) FROM inventory_items WHERE company_id = :c"), {"c": cid})
    mod = _load_migration()
    _run_conversion(mod)                                                   # não estoura uq_inventory_company_name
    db.expire_all()
    names = [i.name for i in db.scalars(select(InventoryItem).where(InventoryItem.company_id == cid))]
    assert len(names) == len(set(names)) and "Bebidas (antigo)" in names and f"{labels[-1]} (antigo)" in names
    assert all(lb in names for lb in labels)
    after = db.scalar(text("SELECT sum(quantity * unit_cost) FROM inventory_items WHERE company_id = :c"), {"c": cid})
    assert abs(after - total) < D("0.01")                                  # valor do estoque preservado
    n_items = len(names)
    _run_conversion(mod)                                                   # reaplicar não duplica nem falha
    db.expire_all()
    assert db.scalar(text("SELECT count(*) FROM inventory_items WHERE company_id = :c"), {"c": cid}) == n_items


def _drop_mandatory(db, cid, roles=("lawyer",)):
    for e in db.scalars(select(Employee).where(Employee.company_id == cid, Employee.role.in_(roles))):
        e.status = EmployeeStatus.TERMINATED
    db.commit()


def test_grace_period_sells_without_fine_counts_down_then_becomes_irregular(client, rich, db, monkeypatch):
    cid = create_ok(client, rich)["company"]["id"]
    _drop_mandatory(db, cid)
    db.execute(text("UPDATE companies SET compliance_grace_months = 3 WHERE id = :c"), {"c": cid})
    db.commit()
    comp = detail(client, rich, cid)["compliance"]
    assert comp["regular"] is False and comp["grace_months"] == 3
    for left in (2, 1, 0):
        assert close(client, rich).status_code == 200
        d = detail(client, rich, cid)
        m = d["months"][0]
        assert m["irregular"] is False and D(m["fines"]) == 0
        assert d["compliance"]["grace_months"] == left
        ev = [e for e in d["events"] if e["type"] == "COMPLIANCE"]
        assert any("adaptação" in e["description"] and "Advogado" in e["description"] for e in ev)
    assert D(detail(client, rich, cid)["months"][0]["units_sold"]) > 0
    assert close(client, rich).status_code == 200                           # acabou a tolerância
    m = detail(client, rich, cid)["months"][0]
    assert m["irregular"] is True and D(m["units_sold"]) == 0 and D(m["fines"]) > 0


def test_regular_company_resets_grace_counter(client, rich, db):
    cid = create_ok(client, rich)["company"]["id"]
    db.execute(text("UPDATE companies SET compliance_grace_months = 3 WHERE id = :c"), {"c": cid})
    db.commit()
    assert close(client, rich).status_code == 200
    db.expire_all()
    assert db.get(Company, cid).compliance_grace_months == 0


def test_new_company_has_no_grace(client, rich, db):
    cid = create_ok(client, rich, staff=False)["company"]["id"]
    assert db.get(Company, cid).compliance_grace_months == 0


def test_resolve_location_unknown_key_falls_back_with_warning(monkeypatch):
    warned = []
    monkeypatch.setattr(company_rules.log, "warning", lambda *a, **k: warned.append(a))
    for seg in company_rules.SEGMENTS.values():
        loc = company_rules.resolve_location(seg, "lugar-inexistente")
        assert loc is not None
        if seg.locations:
            assert loc.demand == min(x.demand for x in seg.locations)
    assert len(warned) == len(company_rules.SEGMENTS)


def test_invalid_location_in_database_does_not_break_listing(client, rich, db):
    cid = create_ok(client, rich)["company"]["id"]
    db.execute(text("UPDATE companies SET location = 'zzz-invalida' WHERE id = :c"), {"c": cid})
    db.commit()
    assert client.get(C, headers=rich).status_code == 200
    assert client.get(f"{C}/overview", headers=rich).status_code == 200
    assert client.get(f"{C}/{cid}", headers=rich).status_code == 200
