"""Orçamento mensal e ciclo do simulador. Todas as rotas são do usuário autenticado."""
from collections.abc import Callable
from datetime import date
from typing import TypeVar

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.dependencies import CurrentUser, DbSession
from backend.models import (
    BudgetCategory, FlowKind, LedgerEntry, MonthStatus, Portfolio, RecurringItem, SimMonth,
)
from backend.schemas import budget as s
from backend.services import budget_service as bs
from backend.services import finance_ledger, month_service
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError
from backend.services.ledger_service import InsufficientFundsError

router = APIRouter(prefix="/budget", tags=["budget"])
T = TypeVar("T")


def _run(db: Session, fn: Callable[[], T]) -> T:
    """Executa a operação e faz commit; qualquer erro desfaz TUDO (nada fica pela metade)."""
    try:
        result = fn()
        db.commit()
        return result
    except NotFoundError as e:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ConflictError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except InsufficientFundsError as e:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except FinanceError as e:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    except IntegrityError as e:           # corrida: a restrição única do banco barrou a duplicidade
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "operação já processada") from e
    except Exception:
        db.rollback()
        raise


def _month(db: Session, user_id: int, ref: str | None) -> SimMonth:
    if ref is None:
        return bs.ensure_setup(db, user_id)
    bs.ensure_setup(db, user_id)
    return bs.get_month(db, user_id, bs.parse_month(ref))


def _summary_out(db: Session, user_id: int, summary: bs.MonthSummary) -> s.MonthSummaryOut:
    m = summary.month
    recs = {r.id: r for r in db.scalars(select(RecurringItem).where(RecurringItem.user_id == user_id))}
    cats = {c.id: c for c in db.scalars(select(BudgetCategory).where(BudgetCategory.user_id == user_id))}
    items = []
    totals: dict[tuple[FlowKind, int | None], list] = {}
    for v in summary.items:
        r = recs.get(v.item.recurring_item_id) if v.item.recurring_item_id else None
        items.append(s.ItemOut(
            id=v.item.id, name=v.item.name, kind=v.item.kind, category_id=v.item.category_id,
            category_name=v.category_name, planned_amount=v.item.planned_amount, realized=v.realized,
            remaining=v.remaining, recurring=v.recurring, frequency=r.frequency if r else None,
            end_month=r.end_month if r else None, entry_count=v.entry_count,
            capital=v.item.capital, source=v.item.source_key))
        if v.item.capital:
            continue                              # movimentação patrimonial não entra nos totais por categoria
        t = totals.setdefault((v.item.kind, v.item.category_id), [v.category_name, bs.ZERO, bs.ZERO])
        t[1] += v.item.planned_amount
        t[2] += v.realized
    for kind, cat_id, name, value in summary.unplanned:
        t = totals.setdefault((kind, cat_id), [name, bs.ZERO, bs.ZERO])
        t[2] += value
    by_category = [
        s.CategoryTotalOut(category_id=cid, category_name=t[0], kind=kind, planned=quantize_money(t[1]),
                           realized=quantize_money(t[2]), remaining=quantize_money(t[1] - t[2]))
        for (kind, cid), t in sorted(totals.items(), key=lambda kv: (kv[0][0] != FlowKind.INCOME, -kv[1][2]))
    ]
    open_month = m.status == MonthStatus.OPEN
    invest_remaining = quantize_money(max(m.planned_investment - summary.invested, bs.ZERO)) if open_month else m.planned_investment
    return s.MonthSummaryOut(
        ref_month=m.ref_month, status=m.status, opening_balance=m.opening_balance, closing_balance=m.closing_balance,
        planned_investment=m.planned_investment, balance=summary.balance,
        planned_income=summary.planned_income, planned_expense=summary.planned_expense,
        realized_income=summary.realized_income, realized_expense=summary.realized_expense,
        forecast_income=summary.forecast_income, forecast_expense=summary.forecast_expense,
        remaining_income=quantize_money(max(summary.planned_income - summary.realized_income, bs.ZERO)),
        remaining_expense=quantize_money(max(summary.planned_expense - summary.realized_expense, bs.ZERO)),
        invested=summary.invested, result=quantize_money(summary.realized_income - summary.realized_expense),
        projected_closing_balance=summary.projected_closing_balance,
        free_after_investment=quantize_money(summary.projected_closing_balance - invest_remaining),
        invest_remaining=invest_remaining, invest_done=bool(open_month and m.planned_investment > 0 and invest_remaining == 0),
        capital_in=summary.realized_capital_in, capital_out=summary.realized_capital_out,
        items=items, by_category=by_category,
    )


def _close_out(user_id: int, db: Session, month: SimMonth) -> s.ClosePreviewOut:
    p = month_service.preview_close(db, user_id, month)
    sm = p.summary
    return s.ClosePreviewOut(
        ref_month=month.ref_month, next_month=p.next_month,
        income=quantize_money(sm.realized_income + sm.pending_income - sm.pending_capital_in),
        expense=quantize_money(sm.realized_expense + sm.pending_expense - sm.pending_capital_out), invested=sm.invested,
        result=quantize_money((sm.realized_income + sm.pending_income - sm.pending_capital_in)
                              - (sm.realized_expense + sm.pending_expense - sm.pending_capital_out)),
        carried_balance=p.carried_balance, pending=[b.name for b in p.pending], shortfall=p.shortfall,
        can_close=p.can_close, overdraft_needed=p.overdraft_needed, bankruptcy_risk=p.bankruptcy_risk)


def _account_out(db: Session, user_id: int) -> s.AccountOut:
    acc = finance_ledger.personal_account(db, user_id)
    balance = db.scalar(select(Portfolio.cash_balance).where(Portfolio.id == acc.portfolio_id))
    return s.AccountOut(id=acc.id, name=acc.name, kind=acc.kind.value, balance=balance)


def _entry_out(db: Session, user_id: int, entries: list[LedgerEntry]) -> list[s.EntryOut]:
    cats = {c.id: c.name for c in db.scalars(select(BudgetCategory).where(BudgetCategory.user_id == user_id))}
    reversed_ids = set(db.scalars(select(LedgerEntry.reverses_id).where(
        LedgerEntry.user_id == user_id, LedgerEntry.reverses_id.is_not(None))))
    return [s.EntryOut(
        id=e.id, kind=e.kind, amount=e.amount, description=e.description, category_id=e.category_id,
        category_name=cats.get(e.category_id), entry_date=e.entry_date, ref_month=e.ref_month, origin=e.origin,
        budget_item_id=e.budget_item_id, reverses_id=e.reverses_id, reversed=e.id in reversed_ids,
        created_at=e.created_at, capital=e.capital, origin_ref=e.origin_ref) for e in entries]


# ------------------------------------------------------------------ painel e meses

@router.get("/overview", response_model=s.OverviewOut)
def overview(user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        return s.OverviewOut(
            account=_account_out(db, user.id),
            month=_summary_out(db, user.id, bs.summarize(db, user.id, month)),
            close=_close_out(user.id, db, month))
    return _run(db, go)


@router.get("/months", response_model=list[s.MonthRowOut])
def months(user: CurrentUser, db: DbSession):
    def go():
        bs.ensure_setup(db, user.id)
        rows = []
        for m in bs.list_months(db, user.id):
            if m.status == MonthStatus.CLOSED:
                inc, exp, inv = m.total_income, m.total_expense, m.invested
            else:
                sm = bs.summarize(db, user.id, m)
                inc, exp, inv = sm.realized_income, sm.realized_expense, sm.invested
            rows.append(s.MonthRowOut(
                ref_month=m.ref_month, status=m.status, opening_balance=m.opening_balance,
                closing_balance=m.closing_balance, income=inc, expense=exp, invested=inv,
                result=quantize_money(inc - exp)))
        return rows
    return _run(db, go)


@router.get("/months/{ref}", response_model=s.MonthSummaryOut)
def month_detail(ref: str, user: CurrentUser, db: DbSession):
    def go():
        return _summary_out(db, user.id, bs.summarize(db, user.id, _month(db, user.id, ref)))
    return _run(db, go)


@router.patch("/months/current", response_model=s.MonthSummaryOut)
def patch_month(body: s.MonthPatch, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        month.planned_investment = quantize_money(body.planned_investment)
        db.flush()
        return _summary_out(db, user.id, bs.summarize(db, user.id, month))
    return _run(db, go)


# ------------------------------------------------------------------ fechamento

@router.post("/close", response_model=s.OverviewOut)
def close_month(body: s.CloseRequest, user: CurrentUser, db: DbSession):
    """Fecha o mês e abre o próximo. Exige `confirm: true`; repetir a chamada devolve 409 sem cobrar de novo."""
    if not body.confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "confirme o fechamento do mês")

    def go():
        bs.ensure_setup(db, user.id)
        nxt = month_service.close_month(db, user.id, bs.parse_month(body.ref_month))
        return s.OverviewOut(
            account=_account_out(db, user.id),
            month=_summary_out(db, user.id, bs.summarize(db, user.id, nxt)),
            close=_close_out(user.id, db, nxt))
    return _run(db, go)


# ------------------------------------------------------------------ categorias

def _categories_belong_to_account(user) -> None:
    """Dentro de uma partida as categorias são só leitura: quem escolhe é a conta (Configurações da conta)."""
    if user.is_game_world:
        raise ConflictError("as categorias são escolhidas nas configurações da conta, não dentro da partida")


@router.get("/categories", response_model=list[s.CategoryOut])
def categories(user: CurrentUser, db: DbSession):
    def go():
        bs.ensure_setup(db, user.id)
        return list(db.scalars(select(BudgetCategory).where(BudgetCategory.user_id == user.id)
                               .order_by(BudgetCategory.kind, BudgetCategory.sort_order, BudgetCategory.id)))
    return _run(db, go)


@router.post("/categories", response_model=s.CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: s.CategoryCreate, user: CurrentUser, db: DbSession):
    def go():
        _categories_belong_to_account(user)
        bs.ensure_setup(db, user.id)
        return bs.create_category(db, user.id, body.name, body.kind)
    return _run(db, go)


@router.patch("/categories/{category_id}", response_model=s.CategoryOut)
def update_category(category_id: int, body: s.CategoryPatch, user: CurrentUser, db: DbSession):
    def go():
        _categories_belong_to_account(user)
        return bs.update_category(db, user.id, category_id, name=body.name, active=body.active)
    return _run(db, go)


# ------------------------------------------------------------------ itens planejados / recorrentes

@router.post("/items", response_model=s.MonthSummaryOut, status_code=status.HTTP_201_CREATED)
def add_item(body: s.ItemCreate, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        bs.add_item(db, user.id, month, name=body.name, kind=body.kind, category_id=body.category_id,
                    planned_amount=body.planned_amount, recurring=body.recurring, frequency=body.frequency,
                    end_month=bs.parse_month(body.end_month) if body.end_month else None)
        return _summary_out(db, user.id, bs.summarize(db, user.id, month))
    return _run(db, go)


@router.patch("/items/{item_id}", response_model=s.MonthSummaryOut)
def update_item(item_id: int, body: s.ItemPatch, user: CurrentUser, db: DbSession):
    def go():
        month = bs.ensure_setup(db, user.id)
        bs.update_item(db, user.id, item_id, name=body.name, category_id=body.category_id,
                       planned_amount=body.planned_amount, frequency=body.frequency,
                       end_month=bs.parse_month(body.end_month) if body.end_month else None,
                       clear_end_month=body.clear_end_month, apply_to_future=body.apply_to_future)
        return _summary_out(db, user.id, bs.summarize(db, user.id, month))
    return _run(db, go)


@router.delete("/items/{item_id}", response_model=s.MonthSummaryOut)
def delete_item(item_id: int, user: CurrentUser, db: DbSession, stop_recurring: bool = Query(True)):
    def go():
        month = bs.ensure_setup(db, user.id)
        bs.remove_item(db, user.id, item_id, stop_recurring=stop_recurring)
        return _summary_out(db, user.id, bs.summarize(db, user.id, month))
    return _run(db, go)


@router.post("/example", response_model=s.MonthSummaryOut, status_code=status.HTTP_201_CREATED)
def seed_example(user: CurrentUser, db: DbSession):
    """Modelo opcional de receitas/despesas recorrentes (tudo editável depois)."""
    def go():
        month = bs.ensure_setup(db, user.id)
        bs.seed_example(db, user.id, month)
        return _summary_out(db, user.id, bs.summarize(db, user.id, month))
    return _run(db, go)


# ------------------------------------------------------------------ movimentações

@router.get("/entries", response_model=list[s.EntryOut])
def entries(user: CurrentUser, db: DbSession, ref_month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$")):
    def go():
        month = _month(db, user.id, ref_month)
        return _entry_out(db, user.id, bs.list_entries(db, user.id, month.ref_month))
    return _run(db, go)


@router.post("/entries", response_model=s.EntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(body: s.EntryCreate, user: CurrentUser, db: DbSession):
    """Registra uma receita/despesa efetiva no mês aberto (é aqui que o saldo muda)."""
    def go():
        month = bs.ensure_setup(db, user.id)
        e = bs.register_entry(db, user.id, month, kind=body.kind, amount=body.amount, description=body.description,
                              category_id=body.category_id, budget_item_id=body.budget_item_id,
                              entry_date=body.entry_date, idempotency_key=body.idempotency_key)
        return _entry_out(db, user.id, [e])[0]
    return _run(db, go)


@router.post("/entries/{entry_id}/reverse", response_model=s.EntryOut, status_code=status.HTTP_201_CREATED)
def reverse_entry(entry_id: int, user: CurrentUser, db: DbSession):
    """Corrige uma movimentação: cria um estorno no mês aberto (a original permanece no histórico)."""
    def go():
        month = bs.ensure_setup(db, user.id)
        e = finance_ledger.reverse_entry(db, user.id, entry_id, ref_month=month.ref_month, entry_date=month.ref_month)
        return _entry_out(db, user.id, [e])[0]
    return _run(db, go)
