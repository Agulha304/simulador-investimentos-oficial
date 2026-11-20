"""Fechamento do mês e avanço do tempo do simulador.

O tempo só avança por ação explícita do usuário (não há worker/cron). O fechamento
roda numa ÚNICA transação do banco: ou aplica tudo (cobranças recorrentes, saldos,
resumo, abertura do próximo mês) ou nada. Quem chama faz commit; em qualquer exceção
deve fazer rollback.

Garantias contra duplicidade:
  * a carteira é travada (FOR UPDATE), então dois fechamentos simultâneos se enfileiram;
  * o mês só fecha se estiver OPEN (repetir a solicitação dá ConflictError sem efeitos);
  * índice único (recurring_item_id, ref_month) para lançamentos RECORRENTES e chave de
    idempotência `recurring:<item>:<mês>` no caixa.
"""
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import (
    BudgetItem, EntryOrigin, FlowKind, LedgerEntry, MonthStatus, Portfolio, SimMonth, TransactionSource,
)
from backend.services import budget_service, company_service, economy_service, finance_ledger, goods_service, ledger_service, life_service, progression_service
from backend.services.finance_ledger import ConflictError, NotFoundError

log = logging.getLogger(__name__)


@dataclass
class ClosePreview:
    summary: budget_service.MonthSummary
    next_month: date
    carried_balance: Decimal
    pending: list[BudgetItem]
    shortfall: Decimal            # quanto falta de caixa para pagar as recorrentes pendentes (0 = ok)

    @property
    def can_close(self) -> bool:
        return self.shortfall == 0


def _origin_of(source_key: str) -> EntryOrigin:
    if source_key.startswith(("family:", "child:", "life:")):
        return EntryOrigin.FAMILY
    if source_key.startswith("econ:"):
        return EntryOrigin.EVENT
    return EntryOrigin.ASSET


def _pending_recurring(db: Session, month: SimMonth) -> list[BudgetItem]:
    """Itens recorrentes e itens gerados por bens (aluguel, custos, parcelas) sem nenhuma movimentação
    registrada: serão lançados no fechamento."""
    out = []
    for bi in db.scalars(select(BudgetItem).where(
            BudgetItem.month_id == month.id,
            or_(BudgetItem.recurring_item_id.is_not(None), BudgetItem.source_key.is_not(None))).order_by(BudgetItem.id)):
        has_entry = db.scalar(select(LedgerEntry.id).where(LedgerEntry.budget_item_id == bi.id).limit(1))
        if not has_entry:
            out.append(bi)
    return out


def preview_close(db: Session, user_id: int, month: SimMonth) -> ClosePreview:
    budget_service.require_open(month)
    summary = budget_service.summarize(db, user_id, month)
    pending = _pending_recurring(db, month)
    # Receitas entram antes das despesas; o pior ponto do caixa é depois de todas as despesas.
    cash = summary.balance + summary.pending_income
    shortfall = max(Decimal("0.00"), quantize_money(summary.pending_expense - cash))
    return ClosePreview(summary, budget_service.shift_month(month.ref_month, 1),
                        summary.projected_closing_balance, pending, shortfall)


def close_month(db: Session, user_id: int, ref_month: date) -> SimMonth:
    """Fecha `ref_month` e abre o seguinte. Levanta ConflictError se já estiver fechado."""
    portfolio = db.scalar(select(Portfolio).where(Portfolio.user_id == user_id))
    ledger_service.lock_portfolio(db, portfolio.id)               # serializa fechamentos concorrentes
    month = db.scalar(select(SimMonth).where(
        SimMonth.user_id == user_id, SimMonth.ref_month == ref_month).with_for_update())
    if month is None:
        raise NotFoundError("mês não encontrado")
    if month.status != MonthStatus.OPEN:
        raise ConflictError("este mês já foi fechado")

    company_service.process_month(db, user_id, month)          # empresas primeiro: pró-labore e aluguel entram no caixa pessoal
    life_service.process_month(db, user_id, month)             # atributos e relacionamentos do mês que termina
    pending = _pending_recurring(db, month)
    pending.sort(key=lambda b: (b.kind != FlowKind.INCOME, b.id))   # receitas antes das despesas
    for bi in pending:
        if bi.source_key:                                      # gerado por um bem: aluguel, custo, parcela
            finance_ledger.post_entry(
                db, user_id, kind=bi.kind, amount=bi.planned_amount, description=bi.name,
                ref_month=month.ref_month, entry_date=month.ref_month, category_id=bi.category_id,
                origin=_origin_of(bi.source_key), origin_ref=bi.source_key, budget_item_id=bi.id, capital=bi.capital,
                idempotency_key=f"asset:{bi.source_key}:{month.ref_month:%Y-%m}", source=TransactionSource.SYSTEM,
            )
            continue
        finance_ledger.post_entry(
            db, user_id, kind=bi.kind, amount=bi.planned_amount, description=bi.name,
            ref_month=month.ref_month, entry_date=month.ref_month, category_id=bi.category_id,
            origin=EntryOrigin.RECURRING, origin_ref=str(bi.recurring_item_id), budget_item_id=bi.id,
            recurring_item_id=bi.recurring_item_id, idempotency_key=f"recurring:{bi.recurring_item_id}:{month.ref_month:%Y-%m}",
            source=TransactionSource.SYSTEM,
        )
    goods_service.settle_month(db, user_id, month)             # parcelas pagas, saldo devedor atualizado

    summary = budget_service.summarize(db, user_id, month)
    now = datetime.now(timezone.utc)
    db.refresh(portfolio)
    month.total_income = summary.realized_income
    month.total_expense = summary.realized_expense
    month.invested = budget_service._invested_since(db, portfolio.id, month.opened_at, now)
    month.closing_balance = portfolio.cash_balance
    month.status = MonthStatus.CLOSED
    month.closed_at = now
    db.flush()

    nxt = SimMonth(user_id=user_id, ref_month=budget_service.shift_month(month.ref_month, 1),
                   status=MonthStatus.OPEN, opening_balance=portfolio.cash_balance,
                   planned_investment=month.planned_investment)
    db.add(nxt)
    db.flush()
    economy_service.advance_to_month(db, user_id, nxt)        # condições, eventos, índices e reajustes (antes dos itens do mês)
    life_service.apply_career_changes(db, user_id, nxt)       # reajuste anual / mudança de área (antes de gerar os itens do mês)
    budget_service.generate_items(db, user_id, nxt)
    goods_service.advance_to_month(db, user_id, nxt)          # valorização, ocupação e itens dos bens
    life_service.advance_to_month(db, user_id, nxt)           # nascimentos, mudanças, escola e itens da família
    progression_service.on_month_closed(db, user_id, month, nxt)   # objetivos, conquistas e relatório do mês
    log.info("mês %s fechado user=%s saldo=%s", month.ref_month, user_id, portfolio.cash_balance)
    return nxt
