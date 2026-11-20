"""Dívidas pessoais: empréstimos com juros pela taxa da economia e cheque especial (saldo negativo) com limite.

* Empréstimo: valor entra no caixa; as parcelas (juros + amortização) viram itens do orçamento de cada mês.
* Saldo negativo: se faltar dinheiro no fechamento do mês, o cheque especial cobre a diferença (juros altos) até R$ 100 mil;
  qualquer dinheiro que sobrar depois paga o cheque especial. Passou de R$ 100 mil negativo = FALÊNCIA (fim de jogo).
Só vale para partidas (mundos); contas antigas mantêm o comportamento anterior (o mês não fecha sem saldo).
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import EntryOrigin, FlowKind, PersonalLoan, PersonalLoanInstallment, Portfolio, SimMonth, TransactionSource, User
from backend.models import AmortizationSystem
from backend.services import budget_service, economy_service, finance_ledger, item_sync, loan_math
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError

D = Decimal
ZERO = D("0.00")
OVERDRAFT_LIMIT = D("100000.00")
LOAN_SPREAD_PP = D("12")           # spread do crédito pessoal sobre a taxa básica
OVERDRAFT_SPREAD_PP = D("38")      # cheque especial é muito mais caro
BASE_RATE = D("10.5")
MIN_TERM, MAX_TERM = 3, 60
MIN_LIMIT, MAX_LIMIT = D("3000"), D("300000")


def is_world(db: Session, user_id: int) -> bool:
    u = db.get(User, user_id)
    return bool(u and u.is_game_world)


def _credit_factor(db: Session, user_id: int, ref: date) -> Decimal:
    st = economy_service.get_state(db, user_id, ref)
    credit = (st.engine or {}).get("macro", {}).get("credit", 55.0) if st is not None and st.engine else 55.0
    return D(str(round(1 + (55.0 - credit) / 110.0, 4)))                   # crédito escasso encarece e reduz o limite


def loan_rate(db: Session, user_id: int, ref: date) -> D:
    base = BASE_RATE + economy_service.financing_rate_add(db, user_id, ref)
    return quantize_money(base + LOAN_SPREAD_PP * _credit_factor(db, user_id, ref))


def overdraft_rate(db: Session, user_id: int, ref: date) -> D:
    return quantize_money(BASE_RATE + economy_service.financing_rate_add(db, user_id, ref) + OVERDRAFT_SPREAD_PP * _credit_factor(db, user_id, ref))


def get_overdraft(db: Session, user_id: int, ref: date, *, create: bool = True) -> PersonalLoan | None:
    od = db.scalar(select(PersonalLoan).where(PersonalLoan.user_id == user_id, PersonalLoan.kind == "OVERDRAFT"))
    if od is None and create:
        od = PersonalLoan(user_id=user_id, kind="OVERDRAFT", principal=ZERO, balance=ZERO, annual_rate_pct=overdraft_rate(db, user_id, ref),
                          start_month=ref)
        db.add(od)
        db.flush()
    return od


def active_loans(db: Session, user_id: int) -> list[PersonalLoan]:
    return list(db.scalars(select(PersonalLoan).where(PersonalLoan.user_id == user_id, PersonalLoan.kind == "LOAN",
                                                      PersonalLoan.status == "ACTIVE").order_by(PersonalLoan.id)))


def total_debt(db: Session, user_id: int) -> Decimal:
    return quantize_money(db.scalar(select(func.coalesce(func.sum(PersonalLoan.balance), 0)).where(
        PersonalLoan.user_id == user_id, PersonalLoan.status == "ACTIVE")) or ZERO)


def credit_limit(db: Session, user_id: int, month: SimMonth) -> Decimal:
    income = budget_service.summarize(db, user_id, month).planned_income
    lim = min(MAX_LIMIT, max(MIN_LIMIT, income * 12 * _credit_factor(db, user_id, month.ref_month) ** -1))
    used = sum((l.balance for l in active_loans(db, user_id)), ZERO)
    return max(ZERO, quantize_money(lim - used))


def ended(db: Session, user_id: int) -> str | None:
    g = economy_service.get_game(db, user_id, create=False)
    return g.ended_reason if g is not None else None


def require_playing(db: Session, user_id: int) -> None:
    r = ended(db, user_id)
    if r:
        raise ConflictError("esta partida terminou (" + ("falência" if r == "BANKRUPT" else "o personagem faleceu") + "): comece outra")


# ------------------------------------------------------------------ empréstimos
def take_loan(db: Session, user_id: int, month: SimMonth, amount: Decimal, term_months: int) -> PersonalLoan:
    budget_service.require_open(month)
    require_playing(db, user_id)
    amount = quantize_money(amount)
    if amount <= 0:
        raise FinanceError("informe um valor positivo")
    if not MIN_TERM <= term_months <= MAX_TERM:
        raise FinanceError(f"o prazo deve ficar entre {MIN_TERM} e {MAX_TERM} meses")
    limit = credit_limit(db, user_id, month)
    if amount > limit:
        raise FinanceError(f"valor acima do seu limite de crédito: {limit} (depende da sua renda e das condições de crédito)")
    ref = month.ref_month
    rate = loan_rate(db, user_id, ref)
    loan = PersonalLoan(user_id=user_id, kind="LOAN", principal=amount, balance=amount, annual_rate_pct=rate, term_months=term_months, start_month=ref)
    db.add(loan)
    db.flush()
    for r in loan_math.schedule(amount, rate, term_months, AmortizationSystem.PRICE):
        db.add(PersonalLoanInstallment(loan_id=loan.id, number=r.number, due_month=budget_service.shift_month(ref, r.number), payment=r.payment,
                                       interest=r.interest, amortization=r.amortization, balance_after=r.balance_after))
    cat = item_sync.category(db, user_id, FlowKind.INCOME, "Empréstimos")
    finance_ledger.post_entry(db, user_id, kind=FlowKind.INCOME, amount=amount, description=f"Empréstimo pessoal ({term_months}x a {rate}% a.a.)",
                              ref_month=ref, entry_date=ref, category_id=cat.id, origin=EntryOrigin.SYSTEM, origin_ref=f"debt:{loan.id}:in",
                              idempotency_key=f"debt:{loan.id}:in", capital=True, source=TransactionSource.SYSTEM)
    db.flush()
    sync_month(db, user_id, month)
    return loan


def prepay(db: Session, user_id: int, month: SimMonth, loan_id: int) -> PersonalLoan:
    budget_service.require_open(month)
    loan = db.get(PersonalLoan, loan_id)
    if loan is None or loan.user_id != user_id or loan.kind != "LOAN":
        raise NotFoundError("empréstimo não encontrado")
    if loan.status != "ACTIVE":
        raise ConflictError("este empréstimo já foi quitado")
    ref = month.ref_month
    cat = item_sync.category(db, user_id, FlowKind.EXPENSE, "Empréstimos")
    finance_ledger.post_entry(db, user_id, kind=FlowKind.EXPENSE, amount=loan.balance, description="Quitação antecipada do empréstimo", ref_month=ref,
                              entry_date=ref, category_id=cat.id, origin=EntryOrigin.SYSTEM, origin_ref=f"debt:{loan.id}:prepay",
                              idempotency_key=f"debt:{loan.id}:prepay", capital=True, source=TransactionSource.SYSTEM)
    loan.status, loan.balance = "PAID", ZERO
    for inst in db.scalars(select(PersonalLoanInstallment).where(PersonalLoanInstallment.loan_id == loan.id, PersonalLoanInstallment.status == "PENDING")):
        inst.status = "CANCELLED"
    db.flush()
    sync_month(db, user_id, month)
    return loan


# ------------------------------------------------------------------ orçamento do mês
def sync_month(db: Session, user_id: int, month: SimMonth) -> None:
    if month.status.value != "OPEN" or not is_world(db, user_id):
        return
    ref = month.ref_month
    desired: dict[str, dict] = {}
    for loan in active_loans(db, user_id):
        for inst in db.scalars(select(PersonalLoanInstallment).where(
                PersonalLoanInstallment.loan_id == loan.id, PersonalLoanInstallment.due_month == ref, PersonalLoanInstallment.status == "PENDING")):
            label = f"{inst.number}/{loan.term_months}"
            if inst.interest > 0:
                desired[f"debt:{loan.id}:{inst.number}:interest"] = {"name": f"Juros do empréstimo {label}", "kind": FlowKind.EXPENSE, "cat": "Dívidas", "amount": inst.interest}
            desired[f"debt:{loan.id}:{inst.number}:principal"] = {"name": f"Amortização do empréstimo {label}", "kind": FlowKind.EXPENSE, "cat": "Dívidas",
                                                                  "amount": inst.amortization, "capital": True}
    od = get_overdraft(db, user_id, ref, create=False)
    if od is not None and od.balance > 0:
        rate = overdraft_rate(db, user_id, ref)
        od.annual_rate_pct = rate
        interest = quantize_money(od.balance * loan_math.monthly_rate(rate))
        if interest > 0:
            desired[f"debt:od:{ref:%Y-%m}:interest"] = {"name": "Juros do cheque especial (saldo negativo)", "kind": FlowKind.EXPENSE, "cat": "Dívidas", "amount": interest}
    item_sync.reconcile(db, user_id, month, desired, ("debt:",))


def settle_month(db: Session, user_id: int, month: SimMonth) -> None:
    """Depois das cobranças: parcelas pagas, saldo devedor atualizado, empréstimo quitado na última parcela."""
    from backend.models import BudgetItem, LedgerEntry
    for loan in active_loans(db, user_id):
        for inst in db.scalars(select(PersonalLoanInstallment).where(
                PersonalLoanInstallment.loan_id == loan.id, PersonalLoanInstallment.due_month == month.ref_month, PersonalLoanInstallment.status == "PENDING")):
            item = db.scalar(select(BudgetItem).where(BudgetItem.month_id == month.id, BudgetItem.source_key == f"debt:{loan.id}:{inst.number}:principal"))
            if item is not None and db.scalar(select(LedgerEntry.id).where(LedgerEntry.budget_item_id == item.id).limit(1)):
                inst.status, loan.balance = "PAID", inst.balance_after
                if inst.number == loan.term_months:
                    loan.status = "PAID"


# ------------------------------------------------------------------ saldo negativo (cheque especial) e falência
def cover_shortfall(db: Session, user_id: int, month: SimMonth) -> Decimal:
    """Se as contas do mês passam do caixa, o cheque especial cobre a diferença (só em partidas)."""
    if not is_world(db, user_id):
        return ZERO
    s = budget_service.summarize(db, user_id, month)
    shortfall = quantize_money(s.pending_expense - (s.balance + s.pending_income))
    if shortfall <= 0:
        return ZERO
    ref = month.ref_month
    od = get_overdraft(db, user_id, ref)
    od.balance = quantize_money(od.balance + shortfall)
    od.principal = quantize_money(od.principal + shortfall)
    cat = item_sync.category(db, user_id, FlowKind.INCOME, "Empréstimos")
    finance_ledger.post_entry(db, user_id, kind=FlowKind.INCOME, amount=shortfall, description="Cheque especial: cobriu o saldo que faltou", ref_month=ref,
                              entry_date=ref, category_id=cat.id, origin=EntryOrigin.SYSTEM, origin_ref=f"debt:od:{ref:%Y-%m}:draw",
                              idempotency_key=f"debt:od:{ref:%Y-%m}:draw", capital=True, source=TransactionSource.SYSTEM)
    return shortfall


def autorepay(db: Session, user_id: int, month: SimMonth) -> Decimal:
    """Dinheiro que sobra no fim do mês paga o cheque especial primeiro."""
    od = get_overdraft(db, user_id, month.ref_month, create=False)
    if od is None or od.balance <= 0:
        return ZERO
    cash = db.scalar(select(Portfolio.cash_balance).where(Portfolio.user_id == user_id)) or ZERO
    pay = min(cash, od.balance)
    if pay <= 0:
        return ZERO
    ref = month.ref_month
    cat = item_sync.category(db, user_id, FlowKind.EXPENSE, "Empréstimos")
    finance_ledger.post_entry(db, user_id, kind=FlowKind.EXPENSE, amount=pay, description="Pagamento do cheque especial", ref_month=ref, entry_date=ref,
                              category_id=cat.id, origin=EntryOrigin.SYSTEM, origin_ref=f"debt:od:{ref:%Y-%m}:repay",
                              idempotency_key=f"debt:od:{ref:%Y-%m}:repay", capital=True, source=TransactionSource.SYSTEM)
    od.balance = quantize_money(od.balance - pay)
    return pay


def end_game(db: Session, user_id: int, ref: date, reason: str, text: str) -> None:
    from backend.services import life_service
    g = economy_service.get_game(db, user_id)
    if g.ended_reason:
        return
    g.ended_reason, g.ended_month = reason, ref
    life_service.log(db, user_id, ref, reason, text)


def check_bankruptcy(db: Session, user_id: int, ref: date) -> bool:
    od = get_overdraft(db, user_id, ref, create=False)
    if od is not None and od.balance > OVERDRAFT_LIMIT:
        end_game(db, user_id, ref, "BANKRUPT", f"Falência: o saldo negativo passou de {OVERDRAFT_LIMIT} (dívida de {od.balance}). Fim de jogo.")
        return True
    return False


def overview(db: Session, user_id: int, month: SimMonth) -> dict:
    ref = month.ref_month
    od = get_overdraft(db, user_id, ref, create=False)
    cash = db.scalar(select(Portfolio.cash_balance).where(Portfolio.user_id == user_id)) or ZERO
    loans = []
    for l in db.scalars(select(PersonalLoan).where(PersonalLoan.user_id == user_id, PersonalLoan.kind == "LOAN").order_by(PersonalLoan.id.desc())):
        nxt = db.scalar(select(PersonalLoanInstallment).where(PersonalLoanInstallment.loan_id == l.id, PersonalLoanInstallment.status == "PENDING")
                        .order_by(PersonalLoanInstallment.number).limit(1))
        loans.append({"id": l.id, "principal": str(l.principal), "balance": str(l.balance), "rate": str(l.annual_rate_pct), "term": l.term_months,
                      "status": l.status, "start": l.start_month.isoformat(), "next_payment": str(nxt.payment) if nxt else None,
                      "next_due": nxt.due_month.isoformat() if nxt else None})
    bal = od.balance if od else ZERO
    return {"cash": str(cash), "overdraft": str(bal), "balance": str(quantize_money(cash - bal)), "overdraft_limit": str(OVERDRAFT_LIMIT),
            "overdraft_rate": str(overdraft_rate(db, user_id, ref)), "loan_rate": str(loan_rate(db, user_id, ref)),
            "credit_limit": str(credit_limit(db, user_id, month)), "min_term": MIN_TERM, "max_term": MAX_TERM, "loans": loans,
            "total_debt": str(total_debt(db, user_id)), "ended": ended(db, user_id)}
