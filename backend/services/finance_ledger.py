"""Livro de movimentações financeiras (receitas e despesas realizadas).

Toda movimentação do orçamento passa por `post_entry`. Ela:
  * registra o efeito no caixa pelo ÚNICO ponto que altera saldo (`ledger_service.record`);
  * grava uma `LedgerEntry` imutável ligada à `Transaction` correspondente;
  * é idempotente quando recebe `idempotency_key`.
Nenhuma função aqui faz commit: quem chama decide (fechamento de mês = tudo ou nada).

Módulos futuros (imóveis, empresas, família...) devem chamar `post_entry` com sua
própria `origin`/`origin_ref`, sem tocar no saldo diretamente.
"""
import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import (
    AccountKind, Company, EntryOrigin, FinanceAccount, FlowKind, LedgerEntry, Portfolio, TransactionSource, TransactionType,
)
from backend.services import ledger_service
from backend.services.ledger_service import CashMovement

log = logging.getLogger(__name__)


class FinanceError(Exception):
    """Erro de regra de negócio do módulo financeiro (vira 4xx na API)."""


class NotFoundError(FinanceError):
    pass


class ConflictError(FinanceError):
    pass


def scoped_key(user_id: int, key: str) -> str:
    return f"u{user_id}|{key}"


def signed_amount(entry: LedgerEntry) -> Decimal:
    """Valor da entrada na sua natureza (receita/despesa): estornos contam negativo."""
    return -entry.amount if entry.origin == EntryOrigin.REVERSAL else entry.amount


def personal_account(db: Session, user_id: int) -> FinanceAccount:
    acc = db.scalar(select(FinanceAccount).where(
        FinanceAccount.user_id == user_id, FinanceAccount.kind == AccountKind.PERSONAL))
    if acc:
        return acc
    portfolio_id = db.scalar(select(Portfolio.id).where(Portfolio.user_id == user_id))
    acc = FinanceAccount(user_id=user_id, kind=AccountKind.PERSONAL, name="Conta pessoal", portfolio_id=portfolio_id)
    db.add(acc)
    db.flush()
    return acc


def business_account(db: Session, company_id: int) -> FinanceAccount:
    """Conta da empresa, travada para escrita (FOR UPDATE): movimentações concorrentes se enfileiram."""
    acc = db.scalar(select(FinanceAccount).join(Company, Company.account_id == FinanceAccount.id).where(
        Company.id == company_id).with_for_update())
    if acc is None:
        raise NotFoundError("conta empresarial não encontrada")
    return acc


def _cash_effect(kind: FlowKind, amount: Decimal, *, reversal: bool) -> Decimal:
    sign = 1 if kind == FlowKind.INCOME else -1
    return amount * sign * (-1 if reversal else 1)


def post_entry(
    db: Session, user_id: int, *, kind: FlowKind, amount: Decimal, description: str, ref_month: date,
    entry_date: date, category_id: int | None = None, origin: EntryOrigin = EntryOrigin.MANUAL,
    origin_ref: str | None = None, budget_item_id: int | None = None, recurring_item_id: int | None = None,
    idempotency_key: str | None = None, source: TransactionSource = TransactionSource.USER,
    note: str | None = None, reverses_id: int | None = None, capital: bool = False,
    company_id: int | None = None, line: str | None = None, allow_overdraft: bool = False,
) -> LedgerEntry:
    """Registra uma receita/despesa efetiva. Repetir a mesma `idempotency_key` devolve a entrada original."""
    amount = quantize_money(amount)
    if amount <= 0:
        raise FinanceError("o valor deve ser positivo")
    raw_key = idempotency_key
    if idempotency_key:
        # A chave é do USUÁRIO (cada partida é um mundo): duas partidas no mesmo mês geram chaves iguais ("life:tuition"...) e não
        # podem se atrapalhar. Registros antigos (sem prefixo) continuam valendo para o próprio dono.
        idempotency_key = scoped_key(user_id, idempotency_key)
        prev = db.scalar(select(LedgerEntry).where(LedgerEntry.idempotency_key.in_((idempotency_key, raw_key)), LedgerEntry.user_id == user_id))
        if prev:
            return prev

    reversal = origin == EntryOrigin.REVERSAL
    if company_id is not None:
        # Conta EMPRESARIAL: saldo próprio, separado do caixa pessoal. Mesmo livro de movimentações, outro `company_id`.
        account = business_account(db, company_id)
        cash = quantize_money(_cash_effect(kind, amount, reversal=reversal))
        if not allow_overdraft and account.balance + cash < 0:
            raise ledger_service.InsufficientFundsError(
                f"saldo da empresa insuficiente: disponível {account.balance}, necessário {-cash}")
        account.balance = quantize_money(account.balance + cash)
        tx = None
    else:
        account = personal_account(db, user_id)
        cash = quantize_money(_cash_effect(kind, amount, reversal=reversal))
        tx = ledger_service.record(db, account.portfolio_id, CashMovement(
            type=TransactionType.BUDGET_INCOME if kind == FlowKind.INCOME else TransactionType.BUDGET_EXPENSE,
            gross_amount_brl=amount, cash_amount_brl=cash, source=source,
            idempotency_key=f"entry:{idempotency_key}" if idempotency_key else None, note=description,
        ))
    entry = LedgerEntry(
        user_id=user_id, kind=kind, amount=amount, category_id=category_id, description=description,
        entry_date=entry_date, ref_month=ref_month,
        source_account_id=account.id if cash < 0 else None,
        dest_account_id=account.id if cash > 0 else None,
        origin=origin, origin_ref=origin_ref, budget_item_id=budget_item_id,
        recurring_item_id=recurring_item_id, transaction_id=tx.id if tx else None, reverses_id=reverses_id, capital=capital,
        company_id=company_id, line=line,
        idempotency_key=idempotency_key, note=note,
    )
    db.add(entry)
    db.flush()
    log.info("entry %s user=%s %s %s origin=%s", entry.id, user_id, kind, amount, origin)
    return entry


def reverse_entry(db: Session, user_id: int, entry_id: int, *, ref_month: date, entry_date: date,
                  note: str | None = None) -> LedgerEntry:
    """Corrige uma movimentação criando outra de sinal oposto no mês aberto (a original não muda)."""
    original = db.get(LedgerEntry, entry_id)
    if original is None or original.user_id != user_id:
        raise NotFoundError("movimentação não encontrada")
    if original.company_id is not None:
        raise ConflictError("movimentações empresariais não são estornadas pelo orçamento pessoal")
    if original.origin == EntryOrigin.REVERSAL:
        raise ConflictError("um estorno não pode ser estornado")
    if db.scalar(select(LedgerEntry.id).where(LedgerEntry.reverses_id == original.id)):
        raise ConflictError("movimentação já estornada")
    return post_entry(
        db, user_id, kind=original.kind, amount=original.amount, description=f"Estorno: {original.description}",
        ref_month=ref_month, entry_date=entry_date, category_id=original.category_id, origin=EntryOrigin.REVERSAL,
        origin_ref=str(original.id), reverses_id=original.id,
        budget_item_id=original.budget_item_id if original.ref_month == ref_month else None,
        idempotency_key=f"reversal:{original.id}", note=note, capital=original.capital,
    )
