"""Patrimônio: valor líquido dos bens (entra no patrimônio total da carteira) e visões agregadas."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import (
    AccountKind, BudgetItem, Company, CompanyStatus, FinanceAccount, InventoryItem, FlowKind, Good, GoodStatus, GoodValue, InstallmentStatus, LedgerEntry, Loan, LoanInstallment,
    LoanStatus, SimMonth, MonthStatus, ValueSource,
)
from backend.services.budget_service import shift_month

ZERO = Decimal("0.00")


def _personal_ids(user_id: int):
    return select(FinanceAccount.id).where(FinanceAccount.user_id == user_id, FinanceAccount.kind == AccountKind.PERSONAL)


def goods_value(db: Session, user_id: int) -> Decimal:
    """Bens PESSOAIS (bens de empresas contam no patrimônio da empresa)."""
    return quantize_money(db.scalar(select(func.coalesce(func.sum(Good.current_value), 0)).where(
        Good.user_id == user_id, Good.status == GoodStatus.ACTIVE, Good.owner_account_id.in_(_personal_ids(user_id)))))


def debts(db: Session, user_id: int) -> Decimal:
    return quantize_money(db.scalar(select(func.coalesce(func.sum(Loan.balance), 0)).join(Good, Good.id == Loan.good_id).where(
        Loan.user_id == user_id, Loan.status == LoanStatus.ACTIVE, Good.status == GoodStatus.ACTIVE)))


def personal_debts(db: Session, user_id: int) -> Decimal:
    """Empréstimos pessoais + cheque especial em aberto."""
    from backend.models import PersonalLoan
    return quantize_money(db.scalar(select(func.coalesce(func.sum(PersonalLoan.balance), 0)).where(
        PersonalLoan.user_id == user_id, PersonalLoan.status == "ACTIVE")) or ZERO)


def company_equity(db: Session, company: Company) -> Decimal:
    """Patrimônio empresarial = caixa (negativo = dívida) + estoque + bens da empresa + terreno próprio − empréstimos."""
    from backend.models import CompanyLoan   # evita ciclo de import no topo
    cash = db.scalar(select(FinanceAccount.balance).where(FinanceAccount.id == company.account_id))
    stock = db.scalar(select(func.coalesce(func.sum(InventoryItem.quantity * InventoryItem.unit_cost), 0)).where(
        InventoryItem.company_id == company.id))
    assets = db.scalar(select(func.coalesce(func.sum(Good.current_value), 0)).where(
        Good.owner_account_id == company.account_id, Good.status == GoodStatus.ACTIVE))
    loans = db.scalar(select(func.coalesce(func.sum(CompanyLoan.balance), 0)).where(
        CompanyLoan.company_id == company.id, CompanyLoan.status == LoanStatus.ACTIVE))
    from backend.models import CompanyUnit
    branch_land = db.scalar(select(func.coalesce(func.sum(CompanyUnit.site_value), 0)).where(
        CompanyUnit.company_id == company.id, CompanyUnit.status == "OPEN"))      # terrenos das filiais abertas
    return quantize_money(cash + stock + assets + (company.site_value or 0) + branch_land - loans)


def companies_net_value(db: Session, user_id: int) -> Decimal:
    """Participação do usuário no patrimônio das empresas ativas (entra no patrimônio total)."""
    total = ZERO
    for c in db.scalars(select(Company).where(Company.user_id == user_id, Company.status == CompanyStatus.ACTIVE)):
        from backend.models import CompanyListing
        listing = db.scalar(select(CompanyListing).where(CompanyListing.company_id == c.id, CompanyListing.status == "LISTED"))
        base = quantize_money(listing.price * listing.shares_total) if listing is not None else company_equity(db, c)   # capital aberto: valor de mercado
        total += base * c.owner_share_pct / 100
    return quantize_money(total)


def goods_net_value(db: Session, user_id: int) -> Decimal:
    """Bens (valor de mercado) − dívidas dos bens. Somado ao caixa e aos investimentos forma o patrimônio total."""
    return quantize_money(goods_value(db, user_id) - debts(db, user_id))


def overview(db: Session, user_id: int) -> dict:
    goods = list(db.scalars(select(Good).where(Good.user_id == user_id, Good.owner_account_id.in_(_personal_ids(user_id))).order_by(Good.id)))
    active = [g for g in goods if g.status == GoodStatus.ACTIVE]
    value = sum((g.current_value for g in active), ZERO)
    cost = sum((g.acquisition_cost for g in active), ZERO)
    debt = debts(db, user_id)

    month = db.scalar(select(SimMonth).where(SimMonth.user_id == user_id, SimMonth.status == MonthStatus.OPEN))
    inc = exp = debt_service = ZERO
    if month:
        for bi in db.scalars(select(BudgetItem).where(BudgetItem.month_id == month.id, BudgetItem.source_key.is_not(None))):
            if bi.source_key.startswith("loan:"):
                debt_service += bi.planned_amount
                if not bi.capital:
                    exp += bi.planned_amount
            elif bi.kind == FlowKind.INCOME:
                inc += bi.planned_amount
            else:
                exp += bi.planned_amount
    by_cat: dict[str, dict] = defaultdict(lambda: {"count": 0, "value": ZERO})
    for g in active:
        by_cat[g.category.value]["count"] += 1
        by_cat[g.category.value]["value"] += g.current_value
    totals = db.execute(select(LedgerEntry.kind, func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
        LedgerEntry.user_id == user_id, LedgerEntry.origin == "ASSET", LedgerEntry.capital.is_(False),
        LedgerEntry.company_id.is_(None)).group_by(
        LedgerEntry.kind)).all()
    received = next((quantize_money(v) for k, v in totals if k == FlowKind.INCOME), ZERO)
    spent = next((quantize_money(v) for k, v in totals if k == FlowKind.EXPENSE), ZERO)
    return {
        "count": len(active), "sold_count": sum(1 for g in goods if g.status == GoodStatus.SOLD),
        "total_value": quantize_money(value), "total_acquisition_cost": quantize_money(cost),
        "debts": debt, "net_worth": quantize_money(value - debt),
        "unrealized_result": quantize_money(value - cost),
        "monthly_income": quantize_money(inc), "monthly_expense": quantize_money(exp),
        "monthly_debt_service": quantize_money(debt_service),
        "income_received_total": received, "expense_paid_total": spent,
        "by_category": [{"category": k, **v} for k, v in sorted(by_cat.items())],
        "series": series(db, user_id, goods, month.ref_month if month else None),
    }


def series(db: Session, user_id: int, goods: list[Good], until: date | None) -> list[dict]:
    """Evolução mês a mês: valor dos bens e dívidas (a partir do histórico imutável)."""
    if not goods or until is None:
        return []
    start = min(g.acquired_on for g in goods)
    values = defaultdict(list)
    for v in db.scalars(select(GoodValue).where(GoodValue.good_id.in_([g.id for g in goods])).order_by(GoodValue.ref_month)):
        if v.source in (ValueSource.PURCHASE, ValueSource.MONTHLY):
            values[v.good_id].append((v.ref_month, v.value))
    loans = {l.good_id: l for l in db.scalars(select(Loan).where(Loan.user_id == user_id))}
    insts = defaultdict(list)
    for i in db.scalars(select(LoanInstallment).where(LoanInstallment.loan_id.in_([l.id for l in loans.values()] or [0]))):
        insts[i.loan_id].append(i)
    out, m = [], start
    while m <= until:
        gv = ZERO
        debt = ZERO
        for g in goods:
            if g.acquired_on > m or (g.sold_on is not None and g.sold_on <= m):
                continue
            hist = [v for rm, v in values.get(g.id, []) if rm <= m]
            if hist:
                gv += hist[-1]
            loan = loans.get(g.id)
            if loan and not (loan.status == LoanStatus.SETTLED and g.sold_on is not None and g.sold_on <= m):
                paid = sum((i.amortization for i in insts[loan.id] if i.status == InstallmentStatus.PAID and i.due_month <= m), ZERO)
                debt += loan.principal - paid
        out.append({"ref_month": m, "goods_value": quantize_money(gv), "debts": quantize_money(debt),
                    "net": quantize_money(gv - debt)})
        m = shift_month(m, 1)
    return out
