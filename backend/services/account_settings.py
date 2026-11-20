"""Configurações da conta: categorias de receitas e despesas.

As categorias que o jogador quer usar (ativar/desativar, renomear, criar) são uma escolha da CONTA, não de uma partida:
cada mudança vale para todas as partidas atuais e as próximas já nascem com elas.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import AccountCategory, BudgetCategory, FlowKind, Game
from backend.services.budget_service import DEFAULT_EXPENSE_CATEGORIES, DEFAULT_INCOME_CATEGORIES
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError


def ensure_defaults(db: Session, account_id: int) -> list[AccountCategory]:
    rows = list(db.scalars(select(AccountCategory).where(AccountCategory.account_id == account_id).order_by(AccountCategory.sort_order, AccountCategory.id)))
    if rows:
        return rows
    for i, (kind, name) in enumerate([(FlowKind.EXPENSE, n) for n in DEFAULT_EXPENSE_CATEGORIES] + [(FlowKind.INCOME, n) for n in DEFAULT_INCOME_CATEGORIES]):
        db.add(AccountCategory(account_id=account_id, kind=kind.value, name=name, sort_order=i))
    db.flush()
    return list(db.scalars(select(AccountCategory).where(AccountCategory.account_id == account_id).order_by(AccountCategory.sort_order, AccountCategory.id)))


def _worlds(db: Session, account_id: int) -> list[int]:
    return list(db.scalars(select(Game.world_user_id).where(Game.account_id == account_id)))


def seed_world(db: Session, account_id: int, world_user_id: int) -> None:
    """Uma partida nova nasce com as categorias da conta (inclusive as desativadas)."""
    for i, c in enumerate(ensure_defaults(db, account_id)):
        db.add(BudgetCategory(user_id=world_user_id, kind=FlowKind(c.kind), name=c.name, is_default=True, active=c.active, sort_order=i))
    db.flush()


def _get(db: Session, account_id: int, category_id: int) -> AccountCategory:
    c = db.get(AccountCategory, category_id)
    if c is None or c.account_id != account_id:
        raise NotFoundError("categoria não encontrada")
    return c


def create(db: Session, account_id: int, name: str, kind: str) -> AccountCategory:
    name = name.strip()
    if not name:
        raise FinanceError("informe o nome da categoria")
    if kind not in ("INCOME", "EXPENSE"):
        raise FinanceError("tipo inválido (INCOME ou EXPENSE)")
    ensure_defaults(db, account_id)
    if db.scalar(select(AccountCategory.id).where(AccountCategory.account_id == account_id, AccountCategory.kind == kind, AccountCategory.name == name)):
        raise ConflictError("já existe uma categoria com esse nome")
    top = db.scalar(select(func.coalesce(func.max(AccountCategory.sort_order), 0)).where(AccountCategory.account_id == account_id)) or 0
    c = AccountCategory(account_id=account_id, kind=kind, name=name, sort_order=top + 1)
    db.add(c)
    db.flush()
    for w in _worlds(db, account_id):                      # vale também para as partidas que já existem
        if not db.scalar(select(BudgetCategory.id).where(BudgetCategory.user_id == w, BudgetCategory.kind == FlowKind(kind), BudgetCategory.name == name)):
            db.add(BudgetCategory(user_id=w, kind=FlowKind(kind), name=name, sort_order=top + 1))
    db.flush()
    return c


def update(db: Session, account_id: int, category_id: int, *, name: str | None, active: bool | None) -> AccountCategory:
    c = _get(db, account_id, category_id)
    old = c.name
    if name is not None:
        name = name.strip()
        if not name:
            raise FinanceError("informe o nome da categoria")
        if name != old and db.scalar(select(AccountCategory.id).where(AccountCategory.account_id == account_id, AccountCategory.kind == c.kind, AccountCategory.name == name)):
            raise ConflictError("já existe uma categoria com esse nome")
        c.name = name
    if active is not None:
        c.active = active
    db.flush()
    for w in _worlds(db, account_id):                      # propaga para todas as partidas (por tipo + nome antigo)
        bc = db.scalar(select(BudgetCategory).where(BudgetCategory.user_id == w, BudgetCategory.kind == FlowKind(c.kind), BudgetCategory.name == old))
        if bc is None:
            continue
        if name is not None and name != old and not db.scalar(select(BudgetCategory.id).where(
                BudgetCategory.user_id == w, BudgetCategory.kind == bc.kind, BudgetCategory.name == name)):
            bc.name = name
        if active is not None:
            bc.active = active
    db.flush()
    return c


def out(c: AccountCategory) -> dict:
    return {"id": c.id, "kind": c.kind, "name": c.name, "active": c.active}
