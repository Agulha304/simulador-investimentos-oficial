"""Sincronização de itens do orçamento gerados por módulos (vida, economia...): cria, atualiza e remove itens
do mês ABERTO com uma `source_key` própria, sem tocar nos itens de outros módulos nem nos que já têm lançamento."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import BudgetCategory, BudgetItem, FlowKind, LedgerEntry, SimMonth


def category(db: Session, user_id: int, kind: FlowKind, name: str) -> BudgetCategory:
    c = db.scalar(select(BudgetCategory).where(
        BudgetCategory.user_id == user_id, BudgetCategory.kind == kind, BudgetCategory.name == name))
    if c is None:
        c = BudgetCategory(user_id=user_id, kind=kind, name=name, sort_order=100)
        db.add(c)
        db.flush()
    return c


def reconcile(db: Session, user_id: int, month: SimMonth, desired: dict[str, dict], prefixes: tuple[str, ...]) -> None:
    """`desired`: key -> {name, kind, cat, amount}. Só mexe em itens cuja source_key começa com `prefixes`."""
    ref: date = month.ref_month
    existing = {bi.source_key: bi for bi in db.scalars(select(BudgetItem).where(
        BudgetItem.month_id == month.id, BudgetItem.source_key.is_not(None))) if bi.source_key.startswith(prefixes)}
    with_entries = set(db.scalars(select(LedgerEntry.budget_item_id).where(
        LedgerEntry.user_id == user_id, LedgerEntry.ref_month == ref, LedgerEntry.budget_item_id.is_not(None))))
    for key, d in desired.items():
        cat = category(db, user_id, d["kind"], d["cat"])
        bi = existing.get(key)
        if bi is None:
            db.add(BudgetItem(user_id=user_id, month_id=month.id, category_id=cat.id, name=d["name"][:80], kind=d["kind"],
                              planned_amount=d["amount"], source_key=key, capital=bool(d.get("capital", False))))
        elif bi.id not in with_entries:
            bi.name, bi.kind, bi.category_id, bi.planned_amount = d["name"][:80], d["kind"], cat.id, d["amount"]
            bi.capital = bool(d.get("capital", False))
    for key, bi in existing.items():
        if key not in desired and bi.id not in with_entries:
            db.delete(bi)
    db.flush()


def salary_total(db: Session, user_id: int, ref: date) -> Decimal:
    """Soma dos salários recorrentes vigentes no mês (categoria Salário)."""
    from backend.models import RecurringItem
    from backend.services import budget_service
    total = Decimal("0.00")
    cat = db.scalar(select(BudgetCategory.id).where(
        BudgetCategory.user_id == user_id, BudgetCategory.kind == FlowKind.INCOME, BudgetCategory.name == "Salário"))
    if cat is None:
        return total
    for r in db.scalars(select(RecurringItem).where(
            RecurringItem.user_id == user_id, RecurringItem.category_id == cat, RecurringItem.active.is_(True))):
        if budget_service.is_due(r, ref):
            total += budget_service.version_amount(db, r.id, ref) or Decimal("0.00")
    return total
