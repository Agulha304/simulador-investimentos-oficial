"""Bens, imóveis, financiamentos e patrimônio.

TODO efeito financeiro passa pelo ledger (`finance_ledger.post_entry`) e pelo orçamento:
  * compra/venda/quitação = movimentações PATRIMONIAIS (`capital=True`): mexem no caixa, não são despesa/receita;
  * taxas, juros, custos do bem e impostos = despesas; aluguel recebido = receita;
  * custos, aluguel e parcelas viram `BudgetItem` com `source_key` e são lançados UMA vez no fechamento
    do mês (idempotência por chave + índice único), junto com as recorrências do orçamento.
Nenhuma função aqui faz commit.
"""
import logging
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import (
    REAL_ESTATE, AmortizationSystem, BudgetCategory, BudgetItem, Condition, CostKind, EntryOrigin, FlowKind, Frequency,
    Company, FinanceAccount, Good, GoodCategory, GoodCost, GoodEvent, GoodEventType, GoodStatus, GoodValue, InstallmentStatus, LedgerEntry,
    Loan, LoanInstallment, LoanStatus, Occupancy, RealEstateDetails, RecurringItem, SimMonth, ValuationRule,
    ValueSource, VehicleDetails,
)
from backend.services import finance_ledger, loan_math
from backend.services import goods_rules as rules
from backend.services.budget_service import first_of, months_between, require_open, shift_month
from backend.services.finance_ledger import ConflictError, FinanceError, NotFoundError
from backend.services.goods_rules import Listing

log = logging.getLogger(__name__)
ZERO = Decimal("0.00")
STEP = {Frequency.MONTHLY: 1, Frequency.QUARTERLY: 3, Frequency.SEMIANNUAL: 6, Frequency.ANNUAL: 12}
CONDITION_ORDER = [Condition.POOR, Condition.FAIR, Condition.GOOD, Condition.EXCELLENT, Condition.NEW]


# ------------------------------------------------------------------ regras e preços de mercado

def load_rules(db: Session) -> dict[GoodCategory, rules.Rule]:
    out = dict(rules.DEFAULT_RULES)
    for r in db.scalars(select(ValuationRule)):
        out[r.category] = rules.Rule(r.monthly_drift_pct, r.volatility_pct, r.uncertainty_pct)
    return out


def market_price(listing: Listing, month: date, rule_map: dict[GoodCategory, rules.Rule]) -> Decimal:
    price = listing.base_price
    rule = rule_map[listing.category]
    for n in range(1, min(rules.month_index(month), 240) + 1):
        price *= rules.monthly_factor(rule, f"listing:{listing.key}", shift_month(rules.EPOCH, n))
    return quantize_money(price)


def listings_for_user(db: Session, user_id: int, month: date, *, category: GoodCategory | None = None,
                      q: str | None = None, min_price: Decimal | None = None, max_price: Decimal | None = None):
    owned = set(db.scalars(select(Good.listing_key).where(
        Good.user_id == user_id, Good.status == GoodStatus.ACTIVE, Good.listing_key.is_not(None))))
    rule_map = load_rules(db)
    out = []
    for l in rules.CATALOG:
        if category and l.category != category:
            continue
        if q and q.lower() not in f"{l.name} {l.location} {l.description}".lower():
            continue
        price = market_price(l, month, rule_map)
        if (min_price is not None and price < min_price) or (max_price is not None and price > max_price):
            continue
        out.append((l, price, l.key in owned))
    return out


# ------------------------------------------------------------------ helpers

def _category(db: Session, user_id: int, kind: FlowKind, name: str) -> BudgetCategory:
    c = db.scalar(select(BudgetCategory).where(
        BudgetCategory.user_id == user_id, BudgetCategory.kind == kind, BudgetCategory.name == name))
    if c is None:
        c = BudgetCategory(user_id=user_id, kind=kind, name=name, sort_order=100)
        db.add(c)
        db.flush()
    return c


def get_good(db: Session, user_id: int, good_id: int, *, lock: bool = False) -> Good:
    q = select(Good).where(Good.id == good_id, Good.user_id == user_id)
    g = db.scalar(q.with_for_update() if lock else q)
    if g is None:
        raise NotFoundError("bem não encontrado")
    return g


def _personal_only(db: Session, good: Good) -> None:
    if good.owner_account_id != finance_ledger.personal_account(db, good.user_id).id:
        raise ConflictError("este bem pertence a uma empresa: administre-o no painel da empresa")


def _event(db, good: Good, month: date, etype: GoodEventType, text: str, amount: Decimal | None = None) -> None:
    db.add(GoodEvent(good_id=good.id, user_id=good.user_id, ref_month=month, type=etype, description=text, amount=amount))
    db.flush()                                   # a sessão não faz autoflush: a leitura seguinte já deve ver o evento


def _active_loan(db: Session, good_id: int) -> Loan | None:
    return db.scalar(select(Loan).where(Loan.good_id == good_id, Loan.status == LoanStatus.ACTIVE))


def _cost_due(c: GoodCost, month: date) -> bool:
    return c.active and month >= c.start_month and months_between(c.start_month, month) % STEP[c.frequency] == 0


# ------------------------------------------------------------------ financiamento (simulação)

def financing_terms(category: GoodCategory) -> rules.FinancingTerms:
    t = rules.FINANCING.get(category)
    if t is None:
        raise FinanceError("este tipo de bem não pode ser financiado")
    return t


def simulate_financing(category: GoodCategory, price: Decimal, down_payment: Decimal, term: int,
                       system: AmortizationSystem, annual_rate_pct: Decimal | None):
    t = financing_terms(category)
    price, down_payment = quantize_money(price), quantize_money(down_payment)
    min_down = quantize_money(price * (100 - t.max_ltv_pct) / 100)
    if down_payment < min_down:
        raise FinanceError(f"entrada mínima de {min_down} ({100 - t.max_ltv_pct}% do preço)")
    if down_payment >= price:
        raise FinanceError("a entrada deve ser menor que o preço para haver financiamento")
    if not 1 <= term <= t.max_term_months:
        raise FinanceError(f"prazo deve ficar entre 1 e {t.max_term_months} meses")
    rate = t.annual_rate_pct if annual_rate_pct is None else annual_rate_pct
    if rate < 0 or rate > 100:
        raise FinanceError("taxa de juros inválida")
    return rate, loan_math.schedule(price - down_payment, rate, term, system)


# ------------------------------------------------------------------ compra

def purchase(db: Session, user_id: int, month: SimMonth, *, listing_key: str, purchase_key: str, financed: bool = False,
             down_payment: Decimal | None = None, term_months: int = 0,
             system: AmortizationSystem = AmortizationSystem.PRICE, annual_rate_pct: Decimal | None = None,
             extra_costs: Decimal = ZERO, usage_km_month: int | None = None, company: Company | None = None) -> Good:
    require_open(month)
    if company is not None and financed:
        raise FinanceError("bens de empresa só podem ser comprados à vista nesta versão (use o empréstimo da empresa)")
    prev = db.scalar(select(Good).where(Good.user_id == user_id, Good.purchase_key == purchase_key))
    if prev:
        return prev                                           # repetição da mesma solicitação: nada é cobrado de novo
    listing = rules.CATALOG_BY_KEY.get(listing_key)
    if listing is None:
        raise NotFoundError("anúncio não encontrado")
    if db.scalar(select(Good.id).where(Good.user_id == user_id, Good.listing_key == listing_key,
                                       Good.status == GoodStatus.ACTIVE)):
        raise ConflictError("você já possui este bem")
    if extra_costs < 0:
        raise FinanceError("custos adicionais não podem ser negativos")
    cat = listing.category
    rule_map = load_rules(db)
    price = market_price(listing, month.ref_month, rule_map)
    fee = quantize_money(price * rules.PURCHASE_FEE_PCT.get(cat, Decimal(0)) / 100) + quantize_money(extra_costs)

    rate, rows = None, []
    if financed:
        down = quantize_money(down_payment if down_payment is not None else price * Decimal("0.2"))
        rate, rows = simulate_financing(cat, price, down, term_months, system, annual_rate_pct)
    else:
        down = price

    account = db.get(FinanceAccount, company.account_id) if company else finance_ledger.personal_account(db, user_id)
    cond = Condition(listing.condition) if listing.condition else None
    good = Good(user_id=user_id, owner_account_id=account.id, category=cat, name=listing.name,
                description=listing.description, listing_key=listing.key, condition=cond, location=listing.location,
                acquired_on=month.ref_month, purchase_price=price, acquisition_cost=price + fee, current_value=price,
                purchase_key=purchase_key)
    db.add(good)
    db.flush()
    start = shift_month(month.ref_month, 1)

    if cat in REAL_ESTATE:
        db.add(RealEstateDetails(good_id=good.id, property_type=listing.property_type or "house",
                                 address=listing.address or listing.location, area_m2=listing.area_m2 or Decimal(0),
                                 bedrooms=listing.bedrooms, occupancy=Occupancy.VACANT, monthly_rent=ZERO))
    elif cat in (GoodCategory.CAR, GoodCategory.MOTORCYCLE):
        db.add(VehicleDetails(good_id=good.id, usage_km_month=usage_km_month or rules.VEHICLE_DEFAULT_KM_MONTH,
                              km_per_liter=rules.VEHICLE_KM_PER_LITER))
    for kind, amount, freq in rules.default_costs(
            cat, price, area_m2=listing.area_m2, property_type=listing.property_type,
            km_month=usage_km_month or rules.VEHICLE_DEFAULT_KM_MONTH):
        db.add(GoodCost(good_id=good.id, kind=kind, name=rules.COST_LABEL[kind], amount=amount,
                        frequency=Frequency(freq), start_month=start))
    db.add(GoodValue(good_id=good.id, ref_month=month.ref_month, value=price, source=ValueSource.PURCHASE))

    if financed:
        loan = Loan(user_id=user_id, good_id=good.id, principal=price - down, down_payment=down,
                    annual_rate_pct=rate, monthly_rate=loan_math.monthly_rate(rate), term_months=term_months,
                    system=system, start_month=month.ref_month, end_month=shift_month(month.ref_month, term_months),
                    balance=price - down, status=LoanStatus.ACTIVE)
        db.add(loan)
        db.flush()
        for r in rows:
            db.add(LoanInstallment(loan_id=loan.id, number=r.number, due_month=shift_month(month.ref_month, r.number),
                                   payment=r.payment, interest=r.interest, amortization=r.amortization,
                                   balance_after=r.balance_after))
    _event(db, good, month.ref_month, GoodEventType.PURCHASE,
           f"Compra por {price}" + (f", financiada ({term_months}x, {system.value})" if financed else " à vista"), price)

    cid = company.id if company else None
    cat_goods = None if company else _category(db, user_id, FlowKind.EXPENSE, "Bens e imóveis")
    finance_ledger.post_entry(
        db, user_id, kind=FlowKind.EXPENSE, amount=down, description=f"Compra: {good.name}" + (" (entrada)" if financed else ""),
        ref_month=month.ref_month, entry_date=month.ref_month, category_id=cat_goods.id if cat_goods else None,
        origin=EntryOrigin.ASSET, origin_ref=f"good:{good.id}:purchase", idempotency_key=f"good:{good.id}:purchase",
        capital=True, company_id=cid, line="EQUIPMENT" if company else None)
    if fee > 0:
        finance_ledger.post_entry(
            db, user_id, kind=FlowKind.EXPENSE, amount=fee, description=f"Taxas e impostos da compra: {good.name}",
            ref_month=month.ref_month, entry_date=month.ref_month, category_id=cat_goods.id if cat_goods else None,
            origin=EntryOrigin.ASSET, origin_ref=f"good:{good.id}:fees", idempotency_key=f"good:{good.id}:fees",
            company_id=cid, line="FEES" if company else None)
    if company is None:
        sync_month(db, user_id, month)
    log.info("compra good=%s user=%s preço=%s financiado=%s", good.id, user_id, price, financed)
    return good


# ------------------------------------------------------------------ venda

def sale_quote(db: Session, good: Good, sale_price: Decimal | None = None, extra_fees: Decimal = ZERO) -> dict:
    price = quantize_money(sale_price if sale_price is not None else good.current_value)
    fees = quantize_money(price * rules.SALE_FEE_PCT.get(good.category, Decimal(3)) / 100) + quantize_money(extra_fees)
    loan = _active_loan(db, good.id)
    payoff = loan.balance if loan else ZERO
    return {"sale_price": price, "fees": fees, "loan_payoff": payoff, "net_cash": price - fees - payoff,
            "result": price - fees - good.acquisition_cost}


def sell(db: Session, user_id: int, month: SimMonth, good_id: int, *, sale_price: Decimal | None = None,
         extra_fees: Decimal = ZERO) -> Good:
    require_open(month)
    good = get_good(db, user_id, good_id, lock=True)           # trava a linha: duas vendas simultâneas se enfileiram
    _personal_only(db, good)
    if good.status != GoodStatus.ACTIVE:
        raise ConflictError("este bem já foi vendido ou baixado")
    if sale_price is not None and sale_price <= 0:
        raise FinanceError("o preço de venda deve ser positivo")
    if extra_fees < 0:
        raise FinanceError("as taxas não podem ser negativas")
    det = db.get(RealEstateDetails, good.id)
    if det is not None and det.occupancy == Occupancy.COMPANY_USE:
        raise ConflictError("este imóvel está cedido a uma empresa sua: encerre o contrato de locação antes de vender")
    q = sale_quote(db, good, sale_price, extra_fees)
    cat_in = _category(db, user_id, FlowKind.INCOME, "Venda de bens")
    cat_out = _category(db, user_id, FlowKind.EXPENSE, "Bens e imóveis")
    ref = month.ref_month
    finance_ledger.post_entry(
        db, user_id, kind=FlowKind.INCOME, amount=q["sale_price"], description=f"Venda: {good.name}", ref_month=ref,
        entry_date=ref, category_id=cat_in.id, origin=EntryOrigin.ASSET, origin_ref=f"good:{good.id}:sale",
        idempotency_key=f"good:{good.id}:sale", capital=True)
    loan = _active_loan(db, good.id)
    if loan and loan.balance > 0:
        finance_ledger.post_entry(
            db, user_id, kind=FlowKind.EXPENSE, amount=loan.balance, description=f"Quitação do financiamento: {good.name}",
            ref_month=ref, entry_date=ref, category_id=cat_out.id, origin=EntryOrigin.ASSET,
            origin_ref=f"loan:{loan.id}:payoff", idempotency_key=f"loan:{loan.id}:payoff", capital=True)
    if q["fees"] > 0:
        finance_ledger.post_entry(
            db, user_id, kind=FlowKind.EXPENSE, amount=q["fees"], description=f"Custos da venda: {good.name}", ref_month=ref,
            entry_date=ref, category_id=cat_out.id, origin=EntryOrigin.ASSET, origin_ref=f"good:{good.id}:sale_fees",
            idempotency_key=f"good:{good.id}:sale_fees")
    if loan:
        loan.status = LoanStatus.SETTLED
        loan.balance = ZERO
        for inst in db.scalars(select(LoanInstallment).where(
                LoanInstallment.loan_id == loan.id, LoanInstallment.status == InstallmentStatus.PENDING)):
            inst.status = InstallmentStatus.CANCELLED
    good.status = GoodStatus.SOLD
    good.sold_on = ref
    good.sale_price, good.sale_fees, good.sale_result = q["sale_price"], q["fees"], q["result"]
    db.add(GoodValue(good_id=good.id, ref_month=ref, value=q["sale_price"], source=ValueSource.SALE))
    good.current_value = ZERO
    for c in db.scalars(select(GoodCost).where(GoodCost.good_id == good.id)):
        c.active = False
    _event(db, good, ref, GoodEventType.SALE, f"Vendido por {q['sale_price']} (resultado {q['result']})", q["sale_price"])
    db.flush()
    sync_month(db, user_id, month)
    return good


def write_off(db: Session, user_id: int, month: SimMonth, good_id: int, reason: str) -> Good:
    """Perda do bem (roubo, destruição...). Sem dinheiro envolvido; só pode se não houver dívida."""
    require_open(month)
    good = get_good(db, user_id, good_id, lock=True)
    _personal_only(db, good)
    if good.status != GoodStatus.ACTIVE:
        raise ConflictError("este bem não está ativo")
    if _active_loan(db, good.id):
        raise ConflictError("quite ou venda o bem antes: há financiamento ativo")
    good.status = GoodStatus.LOST
    good.current_value = ZERO
    db.add(GoodValue(good_id=good.id, ref_month=month.ref_month, value=ZERO, source=ValueSource.WRITE_OFF))
    for c in db.scalars(select(GoodCost).where(GoodCost.good_id == good.id)):
        c.active = False
    _event(db, good, month.ref_month, GoodEventType.WRITE_OFF, reason.strip() or "Bem baixado")
    db.flush()
    sync_month(db, user_id, month)
    return good


# ------------------------------------------------------------------ ocupação e aluguel

def housing_candidates(db: Session, user_id: int) -> list[RecurringItem]:
    """Despesas recorrentes de moradia (possível aluguel residencial) que o usuário pode encerrar ao se mudar."""
    cat = db.scalar(select(BudgetCategory.id).where(
        BudgetCategory.user_id == user_id, BudgetCategory.kind == FlowKind.EXPENSE, BudgetCategory.name == "Moradia"))
    if cat is None:
        return []
    return list(db.scalars(select(RecurringItem).where(
        RecurringItem.user_id == user_id, RecurringItem.category_id == cat, RecurringItem.kind == FlowKind.EXPENSE,
        RecurringItem.active.is_(True))))


def set_occupancy(db: Session, user_id: int, month: SimMonth, good_id: int, mode: Occupancy, *,
                  monthly_rent: Decimal | None = None, end_recurring_item_ids: tuple[int, ...] = ()) -> Good:
    require_open(month)
    good = get_good(db, user_id, good_id, lock=True)
    _personal_only(db, good)
    if good.status != GoodStatus.ACTIVE:
        raise ConflictError("este bem não está ativo")
    det = db.get(RealEstateDetails, good.id)
    if det is None:
        raise FinanceError("ocupação só se aplica a imóveis")
    if det.occupancy == Occupancy.COMPANY_USE:
        raise ConflictError("este imóvel está cedido a uma empresa sua: encerre o contrato de locação primeiro")
    if mode == Occupancy.COMPANY_USE:
        raise FinanceError("o uso por empresa é definido pelo contrato de locação da empresa")
    if mode == Occupancy.RENTED:
        raise FinanceError("o inquilino chega pela simulação: anuncie o imóvel para alugar (LISTED_FOR_RENT)")
    if good.category == GoodCategory.LAND and mode != Occupancy.VACANT:
        raise FinanceError("terrenos não podem ser habitados nem alugados")
    ref = month.ref_month
    if mode == Occupancy.OWNER_OCCUPIED:
        if good.category != GoodCategory.RESIDENTIAL:
            raise FinanceError("só imóveis residenciais podem ser usados como moradia")
        for other in db.scalars(select(RealEstateDetails).join(Good, Good.id == RealEstateDetails.good_id).where(
                Good.user_id == user_id, Good.status == GoodStatus.ACTIVE, RealEstateDetails.good_id != good.id,
                RealEstateDetails.occupancy == Occupancy.OWNER_OCCUPIED)):
            other.occupancy = Occupancy.VACANT
            _event(db, db.get(Good, other.good_id), ref, GoodEventType.OCCUPANCY, "Deixou de ser a moradia do proprietário")
        owned_ids = {r.id for r in housing_candidates(db, user_id)}
        for rid in end_recurring_item_ids:
            if rid not in owned_ids:
                raise NotFoundError("despesa recorrente de moradia não encontrada")
            r = db.get(RecurringItem, rid)
            r.active = False                                   # os meses passados e movimentações permanecem intactos
            for bi in db.scalars(select(BudgetItem).where(BudgetItem.month_id == month.id, BudgetItem.recurring_item_id == rid)):
                if not db.scalar(select(LedgerEntry.id).where(LedgerEntry.budget_item_id == bi.id).limit(1)):
                    db.delete(bi)                              # só remove o previsto ainda não realizado
        det.monthly_rent = ZERO
    elif mode == Occupancy.LISTED_FOR_RENT:
        rent = monthly_rent if monthly_rent is not None else (det.monthly_rent or rules.market_rent(good.category, good.current_value))
        if rent <= 0:
            raise FinanceError("informe o valor do aluguel")
        det.monthly_rent = quantize_money(rent)
    else:
        det.monthly_rent = det.monthly_rent if mode == Occupancy.VACANT else ZERO
    det.occupancy = mode
    _event(db, good, ref, GoodEventType.OCCUPANCY, f"Situação: {mode.value}" + (f", aluguel {det.monthly_rent}" if mode == Occupancy.LISTED_FOR_RENT else ""))
    db.flush()
    sync_month(db, user_id, month)
    return good


# ------------------------------------------------------------------ custos, manutenção, dados do bem

def add_cost(db: Session, user_id: int, month: SimMonth, good_id: int, *, kind: CostKind, name: str, amount: Decimal,
             frequency: Frequency) -> GoodCost:
    require_open(month)
    good = get_good(db, user_id, good_id)
    _personal_only(db, good)
    if good.status != GoodStatus.ACTIVE:
        raise ConflictError("este bem não está ativo")
    if amount <= 0:
        raise FinanceError("o valor deve ser positivo")
    c = GoodCost(good_id=good.id, kind=kind, name=name.strip() or rules.COST_LABEL[kind], amount=quantize_money(amount),
                 frequency=frequency, start_month=month.ref_month)
    db.add(c)
    _event(db, good, month.ref_month, GoodEventType.COST_CHANGE, f"Novo custo: {c.name} {c.amount}", c.amount)
    db.flush()
    sync_month(db, user_id, month)
    return c


def update_cost(db: Session, user_id: int, month: SimMonth, good_id: int, cost_id: int, *, amount: Decimal | None = None,
                active: bool | None = None, frequency: Frequency | None = None) -> GoodCost:
    require_open(month)
    good = get_good(db, user_id, good_id)
    _personal_only(db, good)
    c = db.get(GoodCost, cost_id)
    if c is None or c.good_id != good.id:
        raise NotFoundError("custo não encontrado")
    if amount is not None:
        if amount <= 0:
            raise FinanceError("o valor deve ser positivo")
        c.amount = quantize_money(amount)                       # vale do mês aberto em diante; meses fechados não mudam
    if active is not None:
        c.active = active
    if frequency is not None:
        c.frequency = frequency
    _event(db, good, month.ref_month, GoodEventType.COST_CHANGE, f"Custo alterado: {c.name} → {c.amount}", c.amount)
    db.flush()
    sync_month(db, user_id, month)
    return c


def register_maintenance(db: Session, user_id: int, month: SimMonth, good_id: int, amount: Decimal, description: str,
                         key: str | None) -> LedgerEntry:
    require_open(month)
    good = get_good(db, user_id, good_id)
    _personal_only(db, good)
    if good.status != GoodStatus.ACTIVE:
        raise ConflictError("este bem não está ativo")
    cat = _category(db, user_id, FlowKind.EXPENSE, rules.COST_BUDGET_CATEGORY[CostKind.MAINTENANCE])
    ref_key = key or uuid.uuid4().hex
    replay = db.scalar(select(LedgerEntry.id).where(LedgerEntry.idempotency_key == f"good:{good.id}:maintenance:{ref_key}"))
    entry = finance_ledger.post_entry(
        db, user_id, kind=FlowKind.EXPENSE, amount=amount, description=description.strip() or f"Manutenção: {good.name}",
        ref_month=month.ref_month, entry_date=month.ref_month, category_id=cat.id, origin=EntryOrigin.ASSET,
        origin_ref=f"good:{good.id}:maintenance", idempotency_key=f"good:{good.id}:maintenance:{ref_key}")
    if replay:
        return entry                              # mesma solicitação repetida: nada é registrado de novo
    if good.condition in (Condition.POOR, Condition.FAIR) and amount >= good.current_value * Decimal("0.02"):
        good.condition = CONDITION_ORDER[CONDITION_ORDER.index(good.condition) + 1]
    _event(db, good, month.ref_month, GoodEventType.MAINTENANCE, entry.description, entry.amount)
    return entry


def appraise(db: Session, good: Good) -> dict:
    """Estimativa de mercado (somente leitura): valor atual ± a incerteza da categoria."""
    unc = load_rules(db)[good.category].uncertainty_pct / 100
    return {"estimate": good.current_value, "low": quantize_money(good.current_value * (1 - unc)),
            "high": quantize_money(good.current_value * (1 + unc)), "uncertainty_pct": unc * 100}


# ------------------------------------------------------------------ orçamento: itens gerados pelos bens

def sync_month(db: Session, user_id: int, month: SimMonth) -> None:
    """Alinha os itens do orçamento do mês ABERTO com o estado dos bens (idempotente)."""
    if month.status.value != "OPEN":
        return
    ref = month.ref_month
    desired: dict[str, dict] = {}

    def want(key, name, kind, cat_name, amount, capital=False):
        if amount > 0:
            desired[key] = {"name": name[:80], "kind": kind, "cat": cat_name, "amount": quantize_money(amount), "capital": capital}

    personal_id = finance_ledger.personal_account(db, user_id).id
    for g in db.scalars(select(Good).where(Good.user_id == user_id, Good.status == GoodStatus.ACTIVE,
                                           Good.owner_account_id == personal_id)):
        for c in db.scalars(select(GoodCost).where(GoodCost.good_id == g.id)):
            if _cost_due(c, ref):
                want(f"good:{g.id}:cost:{c.id}", f"{c.name} — {g.name}", FlowKind.EXPENSE,
                     rules.COST_BUDGET_CATEGORY[c.kind], c.amount)
        det = db.get(RealEstateDetails, g.id)
        if det and det.occupancy == Occupancy.RENTED and det.monthly_rent > 0:
            want(f"good:{g.id}:rent", f"Aluguel recebido — {g.name}", FlowKind.INCOME, "Aluguéis recebidos", det.monthly_rent)
            want(f"good:{g.id}:rent_tax", f"IR sobre aluguel — {g.name}", FlowKind.EXPENSE, "Impostos",
                 det.monthly_rent * det.rent_tax_pct / 100)
        loan = _active_loan(db, g.id)
        if loan:
            for inst in db.scalars(select(LoanInstallment).where(
                    LoanInstallment.loan_id == loan.id, LoanInstallment.due_month == ref,
                    LoanInstallment.status == InstallmentStatus.PENDING)):
                label = f"{inst.number}/{loan.term_months}"
                want(f"loan:{loan.id}:{inst.number}:interest", f"Juros do financiamento {label} — {g.name}",
                     FlowKind.EXPENSE, "Dívidas", inst.interest)
                want(f"loan:{loan.id}:{inst.number}:principal", f"Amortização do financiamento {label} — {g.name}",
                     FlowKind.EXPENSE, "Dívidas", inst.amortization, capital=True)

    existing = {bi.source_key: bi for bi in db.scalars(select(BudgetItem).where(
        BudgetItem.month_id == month.id, BudgetItem.source_key.is_not(None))) if bi.source_key.startswith(("good:", "loan:"))}
    with_entries = set(db.scalars(select(LedgerEntry.budget_item_id).where(
        LedgerEntry.user_id == user_id, LedgerEntry.ref_month == ref, LedgerEntry.budget_item_id.is_not(None))))
    for key, d in desired.items():
        cat = _category(db, user_id, d["kind"], d["cat"])
        bi = existing.get(key)
        if bi is None:
            db.add(BudgetItem(user_id=user_id, month_id=month.id, category_id=cat.id, name=d["name"], kind=d["kind"],
                              planned_amount=d["amount"], source_key=key, capital=d["capital"]))
        elif bi.id not in with_entries:
            bi.name, bi.category_id, bi.planned_amount = d["name"], cat.id, d["amount"]
    for key, bi in existing.items():
        if key not in desired and bi.id not in with_entries:
            db.delete(bi)
    db.flush()


def settle_month(db: Session, user_id: int, month: SimMonth) -> None:
    """Depois das cobranças do fechamento: parcelas do mês viram PAGAS e o saldo devedor é atualizado."""
    for loan in db.scalars(select(Loan).where(Loan.user_id == user_id, Loan.status == LoanStatus.ACTIVE)):
        for inst in db.scalars(select(LoanInstallment).where(
                LoanInstallment.loan_id == loan.id, LoanInstallment.due_month == month.ref_month,
                LoanInstallment.status == InstallmentStatus.PENDING)):
            item = db.scalar(select(BudgetItem).where(
                BudgetItem.month_id == month.id, BudgetItem.source_key == f"loan:{loan.id}:{inst.number}:principal"))
            paid = item is not None and db.scalar(select(LedgerEntry.id).where(LedgerEntry.budget_item_id == item.id).limit(1))
            if paid or inst.amortization == 0:
                inst.status = InstallmentStatus.PAID
                loan.balance = inst.balance_after
                if inst.number == loan.term_months:
                    loan.status = LoanStatus.PAID


def advance_to_month(db: Session, user_id: int, new_month: SimMonth) -> None:
    """Abertura de um novo mês: valoriza/deprecia os bens, simula a ocupação e gera os itens do orçamento.

    Determinístico e idempotente: o histórico de valor tem uma linha por bem e mês (única), e meses passados
    nunca são reescritos.
    """
    rule_map = load_rules(db)
    ref = new_month.ref_month
    for g in db.scalars(select(Good).where(Good.user_id == user_id, Good.status == GoodStatus.ACTIVE)):
        already = db.scalar(select(GoodValue.id).where(
            GoodValue.good_id == g.id, GoodValue.ref_month == ref, GoodValue.source == ValueSource.MONTHLY))
        if not already and g.acquired_on < ref:
            rule = rule_map[g.category]
            factor = rules.monthly_factor(rule, f"good:{g.id}", ref)
            if g.condition == Condition.POOR:
                factor -= Decimal("0.003")
            g.current_value = max(quantize_money(g.current_value * factor), ZERO)
            db.add(GoodValue(good_id=g.id, ref_month=ref, value=g.current_value, source=ValueSource.MONTHLY))
        det = db.get(RealEstateDetails, g.id)
        if det and det.occupancy == Occupancy.LISTED_FOR_RENT:
            market = rules.market_rent(g.category, g.current_value)
            ratio = float(market / det.monthly_rent) if det.monthly_rent > 0 else 1.0
            p = min(0.9, max(0.1, rules.FILL_BASE_PROB * ratio))
            if rules.hash01("fill", g.id, ref.isoformat()) < p:
                det.occupancy = Occupancy.RENTED
                _event(db, g, ref, GoodEventType.RENTED, f"Imóvel alugado por {det.monthly_rent}/mês", det.monthly_rent)
        elif det and det.occupancy == Occupancy.RENTED:
            if rules.hash01("vacate", g.id, ref.isoformat()) < rules.VACATE_PROB:
                det.occupancy = Occupancy.LISTED_FOR_RENT
                _event(db, g, ref, GoodEventType.VACATED, "Inquilino saiu: imóvel vago e anunciado")
    db.flush()
    sync_month(db, user_id, new_month)
