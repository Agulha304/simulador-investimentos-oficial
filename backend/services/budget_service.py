"""Orçamento mensal: categorias, itens planejados, recorrências e resumo do mês.

Valor PLANEJADO (BudgetItem) nunca mexe no saldo; só movimentações (LedgerEntry) mexem.
Como cada mês materializa seus próprios itens, alterar uma recorrência hoje não
reescreve meses passados (o aluguel de R$ 1.500 até março continua R$ 1.500).
Nenhuma função aqui faz commit.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.dates import today_br
from backend.core.money import quantize_money
from backend.models import (
    BudgetCategory, BudgetItem, EntryOrigin, FlowKind, Frequency, LedgerEntry, MonthStatus, Portfolio,
    RecurringItem, RecurringItemVersion, SimMonth, Transaction, TransactionType,
)
from backend.services import finance_ledger, ledger_service
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError, signed_amount

ZERO = Decimal("0.00")

DEFAULT_EXPENSE_CATEGORIES = [
    "Moradia", "Alimentação", "Transporte", "Saúde", "Educação", "Lazer", "Vestuário", "Comunicação",
    "Contas domésticas", "Impostos", "Dívidas", "Outros",
]
DEFAULT_INCOME_CATEGORIES = ["Salário", "Renda extra", "Aluguéis recebidos", "Rendimentos", "Outras receitas"]

FREQUENCY_STEP = {Frequency.MONTHLY: 1, Frequency.QUARTERLY: 3, Frequency.SEMIANNUAL: 6, Frequency.ANNUAL: 12}

# Exemplo opcional (o usuário pode aceitar ou ignorar; nada disso é fixo no código do orçamento).
EXAMPLE_ITEMS = [
    ("Salário", FlowKind.INCOME, "Salário", Decimal("4500.00")),
    ("Aluguel", FlowKind.EXPENSE, "Moradia", Decimal("1500.00")),
    ("Supermercado", FlowKind.EXPENSE, "Alimentação", Decimal("700.00")),
    ("Transporte", FlowKind.EXPENSE, "Transporte", Decimal("350.00")),
    ("Plano de saúde", FlowKind.EXPENSE, "Saúde", Decimal("200.00")),
    ("Internet e telefone", FlowKind.EXPENSE, "Comunicação", Decimal("150.00")),
    ("Lazer", FlowKind.EXPENSE, "Lazer", Decimal("300.00")),
]


# ------------------------------------------------------------------ datas

def first_of(d: date) -> date:
    return d.replace(day=1)


def shift_month(d: date, n: int) -> date:
    idx = d.year * 12 + (d.month - 1) + n
    return date(idx // 12, idx % 12 + 1, 1)


def months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def parse_month(value: str) -> date:
    """'2026-11' -> date(2026, 11, 1)."""
    try:
        y, m = value.split("-")
        return date(int(y), int(m), 1)
    except (ValueError, TypeError):
        raise FinanceError("mês inválido; use o formato AAAA-MM") from None


def is_due(item: RecurringItem, month: date) -> bool:
    if not item.active or month < item.start_month:
        return False
    if item.end_month is not None and month > item.end_month:
        return False
    return months_between(item.start_month, month) % FREQUENCY_STEP[item.frequency] == 0


# ------------------------------------------------------------------ preparo do usuário

def _ensure_categories(db: Session, user_id: int) -> None:
    if db.scalar(select(BudgetCategory.id).where(BudgetCategory.user_id == user_id).limit(1)):
        return
    rows = [(FlowKind.EXPENSE, n) for n in DEFAULT_EXPENSE_CATEGORIES] + [
        (FlowKind.INCOME, n) for n in DEFAULT_INCOME_CATEGORIES]
    for i, (kind, name) in enumerate(rows):
        db.add(BudgetCategory(user_id=user_id, kind=kind, name=name, is_default=True, sort_order=i))
    db.flush()


def ensure_setup(db: Session, user_id: int) -> SimMonth:
    """Garante conta, categorias e o mês aberto. Devolve o mês aberto (cria o primeiro se preciso)."""
    month = open_month(db, user_id)
    if month:
        return month
    portfolio = db.scalar(select(Portfolio).where(Portfolio.user_id == user_id))
    ledger_service.lock_portfolio(db, portfolio.id)           # serializa a criação inicial
    month = open_month(db, user_id)
    if month:
        return month
    if db.scalar(select(SimMonth.id).where(SimMonth.user_id == user_id).limit(1)):
        raise FinanceError("não há mês aberto; estado inconsistente")
    finance_ledger.personal_account(db, user_id)
    _ensure_categories(db, user_id)
    month = SimMonth(user_id=user_id, ref_month=first_of(today_br()), status=MonthStatus.OPEN,
                     opening_balance=portfolio.cash_balance)
    db.add(month)
    db.flush()
    return month


def open_month(db: Session, user_id: int) -> SimMonth | None:
    return db.scalar(select(SimMonth).where(SimMonth.user_id == user_id, SimMonth.status == MonthStatus.OPEN))


def get_month(db: Session, user_id: int, ref: date) -> SimMonth:
    m = db.scalar(select(SimMonth).where(SimMonth.user_id == user_id, SimMonth.ref_month == ref))
    if m is None:
        raise NotFoundError("mês não encontrado")
    return m


def require_open(month: SimMonth) -> None:
    if month.status != MonthStatus.OPEN:
        raise ConflictError("este mês já foi fechado e não pode ser alterado")


# ------------------------------------------------------------------ categorias

def get_category(db: Session, user_id: int, category_id: int, kind: FlowKind | None = None) -> BudgetCategory:
    c = db.get(BudgetCategory, category_id)
    if c is None or c.user_id != user_id:
        raise NotFoundError("categoria não encontrada")
    if kind is not None and c.kind != kind:
        raise FinanceError("a categoria não é do mesmo tipo (receita/despesa)")
    return c


def create_category(db: Session, user_id: int, name: str, kind: FlowKind) -> BudgetCategory:
    name = name.strip()
    if not name:
        raise FinanceError("informe o nome da categoria")
    if db.scalar(select(BudgetCategory.id).where(
            BudgetCategory.user_id == user_id, BudgetCategory.kind == kind, BudgetCategory.name == name)):
        raise ConflictError("já existe uma categoria com esse nome")
    top = db.scalar(select(func.coalesce(func.max(BudgetCategory.sort_order), 0)).where(
        BudgetCategory.user_id == user_id))
    c = BudgetCategory(user_id=user_id, kind=kind, name=name, sort_order=(top or 0) + 1)
    db.add(c)
    db.flush()
    return c


def update_category(db: Session, user_id: int, category_id: int, *, name: str | None, active: bool | None):
    c = get_category(db, user_id, category_id)
    if name is not None:
        name = name.strip()
        if not name:
            raise FinanceError("informe o nome da categoria")
        if name != c.name and db.scalar(select(BudgetCategory.id).where(
                BudgetCategory.user_id == user_id, BudgetCategory.kind == c.kind, BudgetCategory.name == name)):
            raise ConflictError("já existe uma categoria com esse nome")
        c.name = name
    if active is not None:
        c.active = active
    db.flush()
    return c


# ------------------------------------------------------------------ recorrências e itens

def version_amount(db: Session, item_id: int, month: date) -> Decimal | None:
    """Valor vigente da recorrência em `month` (a versão mais recente com effective_from <= month)."""
    return db.scalar(
        select(RecurringItemVersion.amount)
        .where(RecurringItemVersion.item_id == item_id, RecurringItemVersion.effective_from <= month)
        .order_by(RecurringItemVersion.effective_from.desc()).limit(1)
    )


def generate_items(db: Session, user_id: int, month: SimMonth) -> list[BudgetItem]:
    """Cria os itens planejados do mês a partir das recorrências devidas (sem duplicar)."""
    existing = set(db.scalars(select(BudgetItem.recurring_item_id).where(
        BudgetItem.month_id == month.id, BudgetItem.recurring_item_id.is_not(None))))
    created = []
    for r in db.scalars(select(RecurringItem).where(RecurringItem.user_id == user_id, RecurringItem.active.is_(True))):
        if r.id in existing or not is_due(r, month.ref_month):
            continue
        amount = version_amount(db, r.id, month.ref_month)
        if amount is None:
            continue
        bi = BudgetItem(user_id=user_id, month_id=month.id, category_id=r.category_id, recurring_item_id=r.id,
                        name=r.name, kind=r.kind, planned_amount=amount)
        db.add(bi)
        created.append(bi)
    db.flush()
    return created


def get_item(db: Session, user_id: int, item_id: int) -> BudgetItem:
    bi = db.get(BudgetItem, item_id)
    if bi is None or bi.user_id != user_id:
        raise NotFoundError("item não encontrado")
    return bi


def add_item(db: Session, user_id: int, month: SimMonth, *, name: str, kind: FlowKind, category_id: int,
             planned_amount: Decimal, recurring: bool, frequency: Frequency = Frequency.MONTHLY,
             end_month: date | None = None) -> BudgetItem:
    require_open(month)
    name = name.strip()
    if not name:
        raise FinanceError("informe o nome")
    planned_amount = quantize_money(planned_amount)
    if planned_amount <= 0:
        raise FinanceError("o valor deve ser positivo")
    get_category(db, user_id, category_id, kind)
    recurring_id = None
    if recurring:
        if end_month is not None and end_month < month.ref_month:
            raise FinanceError("o término não pode ser anterior ao mês atual")
        account = finance_ledger.personal_account(db, user_id)
        r = RecurringItem(user_id=user_id, account_id=account.id, category_id=category_id, name=name, kind=kind,
                          frequency=frequency, start_month=month.ref_month, end_month=end_month)
        db.add(r)
        db.flush()
        db.add(RecurringItemVersion(item_id=r.id, amount=planned_amount, effective_from=month.ref_month))
        recurring_id = r.id
    bi = BudgetItem(user_id=user_id, month_id=month.id, category_id=category_id, recurring_item_id=recurring_id,
                    name=name, kind=kind, planned_amount=planned_amount)
    db.add(bi)
    db.flush()
    return bi


def update_item(db: Session, user_id: int, item_id: int, *, name: str | None = None, category_id: int | None = None,
                planned_amount: Decimal | None = None, frequency: Frequency | None = None,
                end_month: date | None = None, clear_end_month: bool = False, apply_to_future: bool = True) -> BudgetItem:
    bi = get_item(db, user_id, item_id)
    month = db.get(SimMonth, bi.month_id)
    require_open(month)
    if bi.source_key:
        raise ConflictError("este item é gerado por um bem ou financiamento; altere-o no próprio bem")
    r = db.get(RecurringItem, bi.recurring_item_id) if bi.recurring_item_id else None
    if name is not None:
        if not name.strip():
            raise FinanceError("informe o nome")
        bi.name = name.strip()
        if r and apply_to_future:
            r.name = bi.name
    if category_id is not None:
        get_category(db, user_id, category_id, bi.kind)
        bi.category_id = category_id
        if r and apply_to_future:
            r.category_id = category_id
    if planned_amount is not None:
        planned_amount = quantize_money(planned_amount)
        if planned_amount <= 0:
            raise FinanceError("o valor deve ser positivo")
        bi.planned_amount = planned_amount
        if r and apply_to_future:
            # Nova versão vigente a partir deste mês; meses anteriores seguem com o valor antigo.
            ver = db.scalar(select(RecurringItemVersion).where(
                RecurringItemVersion.item_id == r.id, RecurringItemVersion.effective_from == month.ref_month))
            if ver:
                ver.amount = planned_amount
            else:
                db.add(RecurringItemVersion(item_id=r.id, amount=planned_amount, effective_from=month.ref_month))
    if r and (frequency is not None or end_month is not None or clear_end_month):
        if frequency is not None:
            r.frequency = frequency
        if clear_end_month:
            r.end_month = None
        elif end_month is not None:
            if end_month < month.ref_month:
                raise FinanceError("o término não pode ser anterior ao mês atual")
            r.end_month = end_month
    elif not r and (frequency is not None or end_month is not None):
        raise FinanceError("frequência e término só se aplicam a itens recorrentes")
    db.flush()
    return bi


def remove_item(db: Session, user_id: int, item_id: int, *, stop_recurring: bool) -> None:
    """Remove a linha planejada do mês aberto. Com `stop_recurring`, encerra também as próximas."""
    bi = get_item(db, user_id, item_id)
    month = db.get(SimMonth, bi.month_id)
    require_open(month)
    if bi.source_key:
        raise ConflictError("este item é gerado por um bem ou financiamento; altere-o no próprio bem")
    if db.scalar(select(LedgerEntry.id).where(LedgerEntry.budget_item_id == bi.id).limit(1)):
        raise ConflictError("este item já tem movimentações registradas e não pode ser removido")
    if bi.recurring_item_id and stop_recurring:
        r = db.get(RecurringItem, bi.recurring_item_id)
        r.active = False
    db.delete(bi)
    db.flush()


def seed_example(db: Session, user_id: int, month: SimMonth) -> list[BudgetItem]:
    """Cria o modelo de exemplo (recorrências editáveis) se o usuário ainda não tem nenhuma."""
    require_open(month)
    if db.scalar(select(RecurringItem.id).where(RecurringItem.user_id == user_id).limit(1)):
        raise ConflictError("você já tem itens recorrentes")
    cats = {(c.kind, c.name): c.id for c in db.scalars(select(BudgetCategory).where(BudgetCategory.user_id == user_id))}
    out = []
    for name, kind, cat_name, amount in EXAMPLE_ITEMS:
        cid = cats.get((kind, cat_name))
        if cid is None:
            continue
        out.append(add_item(db, user_id, month, name=name, kind=kind, category_id=cid,
                            planned_amount=amount, recurring=True))
    return out


# ------------------------------------------------------------------ movimentações

def register_entry(db: Session, user_id: int, month: SimMonth, *, kind: FlowKind, amount: Decimal, description: str,
                   category_id: int | None, budget_item_id: int | None, entry_date: date | None,
                   idempotency_key: str | None) -> LedgerEntry:
    require_open(month)
    bi = None
    if budget_item_id is not None:
        bi = get_item(db, user_id, budget_item_id)
        if bi.month_id != month.id:
            raise FinanceError("o item não pertence ao mês aberto")
        if bi.kind != kind:
            raise FinanceError("o item não é do mesmo tipo (receita/despesa)")
        category_id = bi.category_id
    if category_id is None:
        raise FinanceError("informe a categoria")
    get_category(db, user_id, category_id, kind)
    entry_date = entry_date or month.ref_month
    if first_of(entry_date) != month.ref_month:
        raise FinanceError("a data deve estar dentro do mês aberto")
    description = description.strip() or (bi.name if bi else "Movimentação")
    return finance_ledger.post_entry(
        db, user_id, kind=kind, amount=amount, description=description, ref_month=month.ref_month,
        entry_date=entry_date, category_id=category_id, budget_item_id=budget_item_id,
        idempotency_key=idempotency_key, capital=bool(bi and bi.capital),
    )


# ------------------------------------------------------------------ resumo

@dataclass
class ItemView:
    item: BudgetItem
    category_name: str
    realized: Decimal
    remaining: Decimal
    recurring: bool
    entry_count: int


@dataclass
class MonthSummary:
    month: SimMonth
    items: list[ItemView] = field(default_factory=list)
    unplanned: list[tuple[FlowKind, int | None, str, Decimal]] = field(default_factory=list)
    planned_income: Decimal = ZERO
    planned_expense: Decimal = ZERO
    realized_income: Decimal = ZERO
    realized_expense: Decimal = ZERO
    forecast_income: Decimal = ZERO
    forecast_expense: Decimal = ZERO
    pending_income: Decimal = ZERO       # recorrentes que ainda serão lançadas no fechamento
    pending_expense: Decimal = ZERO
    invested: Decimal = ZERO
    realized_capital_in: Decimal = ZERO     # movimentações patrimoniais (compra/venda de bens, amortização)
    realized_capital_out: Decimal = ZERO
    pending_capital_in: Decimal = ZERO
    pending_capital_out: Decimal = ZERO
    balance: Decimal = ZERO              # caixa atual (mês aberto) ou saldo final (mês fechado)
    projected_closing_balance: Decimal = ZERO


def _invested_since(db: Session, portfolio_id: int, start, end) -> Decimal:
    q = select(func.coalesce(func.sum(Transaction.gross_amount_brl), 0)).where(
        Transaction.portfolio_id == portfolio_id,
        Transaction.type.in_([TransactionType.BUY, TransactionType.FIXED_INCOME_APPLY]),
        Transaction.created_at >= start)
    if end is not None:
        q = q.where(Transaction.created_at <= end)
    return quantize_money(db.scalar(q))


def summarize(db: Session, user_id: int, month: SimMonth) -> MonthSummary:
    s = MonthSummary(month=month)
    cats = {c.id: c.name for c in db.scalars(select(BudgetCategory).where(BudgetCategory.user_id == user_id))}
    entries = list(db.scalars(select(LedgerEntry).where(
        LedgerEntry.user_id == user_id, LedgerEntry.ref_month == month.ref_month, LedgerEntry.company_id.is_(None))))
    realized_by_item: dict[int, Decimal] = {}
    count_by_item: dict[int, int] = {}
    unplanned: dict[tuple[FlowKind, int | None], Decimal] = {}
    for e in entries:
        v = signed_amount(e)
        if e.capital:
            if e.kind == FlowKind.INCOME:
                s.realized_capital_in += v
            else:
                s.realized_capital_out += v
        elif e.kind == FlowKind.INCOME:
            s.realized_income += v
        else:
            s.realized_expense += v
        if e.budget_item_id:
            realized_by_item[e.budget_item_id] = realized_by_item.get(e.budget_item_id, ZERO) + v
            count_by_item[e.budget_item_id] = count_by_item.get(e.budget_item_id, 0) + 1
        elif not e.capital:
            key = (e.kind, e.category_id)
            unplanned[key] = unplanned.get(key, ZERO) + v

    items = list(db.scalars(select(BudgetItem).where(BudgetItem.month_id == month.id).order_by(BudgetItem.id)))
    for bi in items:
        realized = realized_by_item.get(bi.id, ZERO)
        n = count_by_item.get(bi.id, 0)
        recurring = bi.recurring_item_id is not None
        s.items.append(ItemView(bi, cats.get(bi.category_id, "?"), realized,
                                quantize_money(bi.planned_amount - realized), recurring, n))
        forecast = max(bi.planned_amount, realized)
        if not bi.capital:
            if bi.kind == FlowKind.INCOME:
                s.planned_income += bi.planned_amount
                s.forecast_income += forecast
            else:
                s.planned_expense += bi.planned_amount
                s.forecast_expense += forecast
        if (recurring or bi.source_key) and n == 0 and month.status == MonthStatus.OPEN:
            if bi.kind == FlowKind.INCOME:
                s.pending_income += bi.planned_amount
                if bi.capital:
                    s.pending_capital_in += bi.planned_amount
            else:
                s.pending_expense += bi.planned_amount
                if bi.capital:
                    s.pending_capital_out += bi.planned_amount
    for (kind, cat_id), v in unplanned.items():
        s.unplanned.append((kind, cat_id, cats.get(cat_id, "Sem categoria"), v))
        if kind == FlowKind.INCOME:
            s.forecast_income += v
        else:
            s.forecast_expense += v

    portfolio_id = db.scalar(select(Portfolio.id).where(Portfolio.user_id == user_id))
    if month.status == MonthStatus.OPEN:
        s.balance = db.scalar(select(Portfolio.cash_balance).where(Portfolio.id == portfolio_id))
        s.invested = _invested_since(db, portfolio_id, month.opened_at, None)
        s.projected_closing_balance = quantize_money(s.balance + s.pending_income - s.pending_expense)
    else:
        s.balance = month.closing_balance
        s.invested = month.invested or ZERO
        s.projected_closing_balance = month.closing_balance
    for name in ("planned_income", "planned_expense", "realized_income", "realized_expense", "forecast_income",
                 "forecast_expense", "pending_income", "pending_expense", "realized_capital_in", "realized_capital_out",
                 "pending_capital_in", "pending_capital_out"):
        setattr(s, name, quantize_money(getattr(s, name)))
    return s


def list_months(db: Session, user_id: int) -> list[SimMonth]:
    return list(db.scalars(select(SimMonth).where(SimMonth.user_id == user_id).order_by(SimMonth.ref_month.desc())))


def list_entries(db: Session, user_id: int, ref: date) -> list[LedgerEntry]:
    return list(db.scalars(select(LedgerEntry).where(
        LedgerEntry.user_id == user_id, LedgerEntry.ref_month == ref, LedgerEntry.company_id.is_(None))
        .order_by(LedgerEntry.id.desc())))
