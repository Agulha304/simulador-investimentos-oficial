"""Renda fixa: aplicar, avaliar, resgatar e pagar eventos (cupons e vencimento).

Toda alteração de saldo passa pelo ledger_service. As contas de rendimento estão em
fixed_income_math (puras); impostos em tax_service; dados de índices em index_data.
"""
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.core.money import quantize_money, quantize_quantity
from backend.models import (
    EventKind, EventStatus, FinancialEvent, FixedIncomeInvestment, FixedIncomeProduct,
    Indexer, InvestmentStatus, Liquidity, PaymentFrequency, RateMode, TransactionSource, TransactionType,
)
from backend.services import fixed_income_math as fm
from backend.services import ledger_service, tax_service
from backend.services.index_data import IndexData
from backend.services.ledger_service import CashMovement

log = logging.getLogger(__name__)
D = Decimal
MARKET_RATE_MAX_AGE = timedelta(days=10)


class FixedIncomeError(Exception):
    """Operação inválida (mensagem apresentável ao usuário)."""


# ------------------------------------------------------------------ descrições

def rate_label(p) -> str:
    r = format(D(p.rate).quantize(D("0.01")), "f").replace(".", ",")
    if p.indexer == Indexer.PRE:
        return f"{r}% a.a."
    name = {Indexer.CDI: "CDI", Indexer.SELIC: "Selic", Indexer.IPCA: "IPCA", Indexer.IGPM: "IGP-M"}[p.indexer]
    return f"{r}% do {name}" if p.rate_mode == RateMode.PERCENT_OF_INDEX else f"{name} + {r}% a.a."


def terms_of(obj) -> fm.Terms:
    """Funciona para produto e para aplicação (mesmos nomes de atributos)."""
    return fm.Terms(obj.indexer, obj.rate_mode, D(obj.rate), obj.maturity_date, obj.payment_frequency,
                    obj.tax_regime, obj.uses_mtm)


def market_rate_for(product: FixedIncomeProduct, today: date) -> Decimal | None:
    if product.market_rate is None or today - product.as_of > MARKET_RATE_MAX_AGE:
        return None
    return D(product.market_rate)


# ------------------------------------------------------------------ avaliação e resgate

@dataclass(frozen=True)
class RedemptionQuote:
    method: str                 # CURVE | MTM
    gross_value: Decimal        # valor de mercado/curva antes de deságio
    discount_brl: Decimal       # deságio de venda no mercado secundário
    gross: Decimal
    tax: tax_service.RedemptionTax
    net: Decimal


def quote_redemption(inv: FixedIncomeInvestment, idx: IndexData, today: date, *, apply_discount: bool) -> RedemptionQuote:
    product = inv.product
    val = fm.value_as_of(terms_of(inv), inv.base_brl, inv.last_settlement_date, idx, today,
                         market_rate_for(product, today))
    gross_value = quantize_money(val.gross)
    discount = quantize_money(gross_value * D(product.secondary_discount_pct) / 100) if apply_discount else D("0.00")
    gross = gross_value - discount
    tax = tax_service.redemption_tax(inv.tax_regime, inv.applied_on, min(today, inv.maturity_date), gross - inv.principal_brl)
    return RedemptionQuote(val.method, gross_value, discount, gross, tax, gross - tax.total_brl)


def redemption_block_reason(inv: FixedIncomeInvestment, today: date) -> str | None:
    p = inv.product
    if inv.status != InvestmentStatus.ACTIVE:
        return "aplicação já encerrada"
    if today >= inv.maturity_date:
        return "título vencido: a liquidação no vencimento é automática"
    if not p.early_redemption:
        return f"este produto só pode ser resgatado no vencimento ({inv.maturity_date:%d/%m/%Y})"
    free_from = inv.applied_on + timedelta(days=p.grace_days)
    if today < free_from:
        return f"carência: resgate liberado a partir de {free_from:%d/%m/%Y}"
    if p.liquidity == Liquidity.SPECIFIC_DATES and today.isoformat() not in (p.liquidity_dates or []):
        nxt = next((d for d in sorted(p.liquidity_dates or []) if d > today.isoformat()), None)
        return "resgate só nas janelas definidas" + (f"; próxima em {date.fromisoformat(nxt):%d/%m/%Y}" if nxt else "")
    return None


@dataclass
class InvestmentView:
    inv: FixedIncomeInvestment
    current_gross: Decimal
    estimated_tax: Decimal
    estimated_net: Decimal
    method: str
    redeem_block_reason: str | None
    redeem_net: Decimal | None
    next_event: FinancialEvent | None


def describe(inv: FixedIncomeInvestment, idx: IndexData, today: date) -> InvestmentView:
    if inv.status == InvestmentStatus.ACTIVE:
        q = quote_redemption(inv, idx, today, apply_discount=False)
        reason = redemption_block_reason(inv, today)
        rnet = quote_redemption(inv, idx, today, apply_discount=True).net if reason is None else None
        nxt = next((e for e in inv.events if e.status == EventStatus.PENDING), None)
        return InvestmentView(inv, q.gross, q.tax.total_brl, q.net, q.method, reason, rnet, nxt)
    return InvestmentView(inv, inv.closed_gross_brl or D(0), inv.closed_tax_brl or D(0), inv.closed_net_brl or D(0),
                          "CLOSED", "aplicação já encerrada", None, None)


def list_investments(db: Session, portfolio_id: int) -> list[FixedIncomeInvestment]:
    return list(db.scalars(
        select(FixedIncomeInvestment).where(FixedIncomeInvestment.portfolio_id == portfolio_id)
        .options(joinedload(FixedIncomeInvestment.product), joinedload(FixedIncomeInvestment.events))
        .order_by(FixedIncomeInvestment.id.desc())).unique())


def portfolio_totals(db: Session, portfolio_id: int, idx: IndexData, today: date) -> tuple[Decimal, Decimal]:
    """(custo das aplicações ativas, valor líquido estimado se resgatadas hoje)."""
    invested = value = D("0.00")
    for inv in list_investments(db, portfolio_id):
        if inv.status != InvestmentStatus.ACTIVE:
            continue
        invested += inv.principal_brl
        value += quote_redemption(inv, idx, today, apply_discount=False).net
    return invested, value


# ------------------------------------------------------------------ aplicar

def invest(db: Session, portfolio_id: int, product_id: int, amount: Decimal, today: date,
           idempotency_key: str | None = None) -> FixedIncomeInvestment:
    product = db.get(FixedIncomeProduct, product_id)
    if product is None or not product.is_active:
        raise FixedIncomeError("produto não encontrado ou indisponível")
    amount = quantize_money(amount)
    if amount < product.min_investment_brl:
        raise FixedIncomeError(f"aplicação mínima: R$ {product.min_investment_brl}")
    if product.maturity_date <= today:
        raise FixedIncomeError("este título já venceu")
    try:
        ledger_service.lock_portfolio(db, portfolio_id)
        ledger_service.record(db, portfolio_id, CashMovement(
            type=TransactionType.FIXED_INCOME_APPLY, source=TransactionSource.USER,
            gross_amount_brl=amount, cash_amount_brl=-amount,
            idempotency_key=f"fi-apply:{portfolio_id}:{idempotency_key}" if idempotency_key else None,
            note=f"Aplicação: {product.name} ({rate_label(product)})"))
        inv = FixedIncomeInvestment(
            portfolio_id=portfolio_id, product_id=product.id, status=InvestmentStatus.ACTIVE, applied_on=today,
            principal_brl=amount, base_brl=amount, last_settlement_date=today,
            units=quantize_quantity(amount / product.unit_price) if product.unit_price else None,
            indexer=product.indexer, rate_mode=product.rate_mode, rate=product.rate,
            maturity_date=product.maturity_date, payment_frequency=product.payment_frequency,
            tax_regime=product.tax_regime, uses_mtm=product.uses_mtm,
        )
        db.add(inv)
        db.flush()
        for c in fm.coupon_dates(today, product.maturity_date, product.payment_frequency):
            db.add(FinancialEvent(investment_id=inv.id, portfolio_id=portfolio_id, kind=EventKind.COUPON,
                                  scheduled_date=c, status=EventStatus.PENDING))
        db.add(FinancialEvent(investment_id=inv.id, portfolio_id=portfolio_id, kind=EventKind.MATURITY,
                              scheduled_date=product.maturity_date, status=EventStatus.PENDING))
        db.commit()
    except Exception:
        db.rollback()
        raise
    log.info("RENDA FIXA aplicação: %s R$ %s (carteira %s)", product.name, amount, portfolio_id)
    return inv


# ------------------------------------------------------------------ resgatar

def redeem(db: Session, portfolio_id: int, investment_id: int, idx: IndexData, today: date) -> FixedIncomeInvestment:
    try:
        ledger_service.lock_portfolio(db, portfolio_id)
        inv = db.execute(select(FixedIncomeInvestment).where(
            FixedIncomeInvestment.id == investment_id, FixedIncomeInvestment.portfolio_id == portfolio_id)
            .options(joinedload(FixedIncomeInvestment.product)).with_for_update(of=FixedIncomeInvestment)).scalar_one_or_none()
        if inv is None:
            raise FixedIncomeError("aplicação não encontrada")
        db.refresh(inv)
        reason = redemption_block_reason(inv, today)
        if reason:
            raise FixedIncomeError(reason[0].upper() + reason[1:])
        q = quote_redemption(inv, idx, today, apply_discount=True)
        tx = ledger_service.record(db, portfolio_id, CashMovement(
            type=TransactionType.FIXED_INCOME_REDEEM, source=TransactionSource.USER,
            gross_amount_brl=q.gross, tax_brl=q.tax.total_brl, cash_amount_brl=q.net,
            idempotency_key=f"fi-redeem:{inv.id}",
            note=f"Resgate antecipado: {inv.product.name} ({q.method == 'MTM' and 'preço de mercado' or 'curva'}"
                 f"{f', deságio R$ {q.discount_brl}' if q.discount_brl else ''})"))
        tx.realized_pnl_brl = q.net - inv.principal_brl
        _close(inv, InvestmentStatus.REDEEMED, today, q.gross, q.tax.total_brl, q.net)
        for e in inv.events:
            if e.status == EventStatus.PENDING:
                e.status = EventStatus.CANCELLED
        db.commit()
    except ledger_service.DuplicateTransactionError:
        db.rollback()
        raise FixedIncomeError("aplicação já resgatada") from None
    except Exception:
        db.rollback()
        raise
    log.info("RENDA FIXA resgate: %s líquido R$ %s", inv.product.name, q.net)
    return inv


def _close(inv, status, on: date, gross, tax, net) -> None:
    inv.status, inv.closed_on = status, on
    inv.closed_gross_brl, inv.closed_tax_brl, inv.closed_net_brl = gross, tax, net


# ------------------------------------------------------------------ eventos (worker)

def process_due_events(db: Session, idx: IndexData, today: date) -> int:
    """Paga cupons e vencimentos devidos, em ordem cronológica. Idempotente."""
    ids = list(db.scalars(select(FinancialEvent.id).where(
        FinancialEvent.status == EventStatus.PENDING, FinancialEvent.scheduled_date <= today)
        .order_by(FinancialEvent.scheduled_date, FinancialEvent.id)))
    paid = 0
    for eid in ids:
        try:
            paid += _pay_event(db, eid, idx)
        except Exception:
            db.rollback()
            log.exception("erro ao processar evento de renda fixa %s", eid)
    return paid


def _pay_event(db: Session, event_id: int, idx: IndexData) -> bool:
    portfolio_id = db.scalar(select(FinancialEvent.portfolio_id).where(FinancialEvent.id == event_id))
    if portfolio_id is None:
        return False
    try:
        ledger_service.lock_portfolio(db, portfolio_id)
        ev = db.execute(select(FinancialEvent).where(FinancialEvent.id == event_id).with_for_update()).scalar_one()
        db.refresh(ev)
        if ev.status != EventStatus.PENDING:
            db.rollback()
            return False
        inv = db.execute(select(FixedIncomeInvestment).where(FixedIncomeInvestment.id == ev.investment_id)
                         .options(joinedload(FixedIncomeInvestment.product)).with_for_update(of=FixedIncomeInvestment)).scalar_one()
        db.refresh(inv)
        if inv.status != InvestmentStatus.ACTIVE:
            ev.status = EventStatus.CANCELLED
            db.commit()
            return False
        t, on = terms_of(inv), ev.scheduled_date

        if ev.kind == EventKind.COUPON:
            interest, new_base = fm.coupon_interest(t, inv.base_brl, inv.last_settlement_date, idx, on)
            gross = quantize_money(interest)
            if gross <= 0:
                ev.status = EventStatus.CANCELLED
                db.commit()
                return False
            tax = tax_service.redemption_tax(inv.tax_regime, inv.applied_on, on, gross)
            net = gross - tax.total_brl
            tx = ledger_service.record(db, portfolio_id, CashMovement(
                type=TransactionType.FIXED_INCOME_COUPON, source=TransactionSource.FIXED_INCOME_WORKER,
                gross_amount_brl=gross, tax_brl=tax.total_brl, cash_amount_brl=net,
                idempotency_key=f"fi-event:{ev.id}", note=f"Juros: {inv.product.name} ({on:%d/%m/%Y})"))
            inv.base_brl, inv.last_settlement_date = new_base, on
            inv.interest_paid_net_brl += net
        else:
            gross = quantize_money(fm.value_as_of(t, inv.base_brl, inv.last_settlement_date, idx, on).gross)
            tax = tax_service.redemption_tax(inv.tax_regime, inv.applied_on, on, gross - inv.principal_brl)
            net = gross - tax.total_brl
            tx = ledger_service.record(db, portfolio_id, CashMovement(
                type=TransactionType.FIXED_INCOME_MATURITY, source=TransactionSource.FIXED_INCOME_WORKER,
                gross_amount_brl=gross, tax_brl=tax.total_brl, cash_amount_brl=net,
                idempotency_key=f"fi-event:{ev.id}", note=f"Vencimento: {inv.product.name}"))
            tx.realized_pnl_brl = net - inv.principal_brl
            _close(inv, InvestmentStatus.MATURED, on, gross, tax.total_brl, net)
        ev.status, ev.gross_brl, ev.tax_brl, ev.net_brl = EventStatus.PAID, gross, tax.total_brl, net
        ev.transaction_id, ev.paid_at = tx.id, datetime.now(UTC)
        db.commit()
    except ledger_service.DuplicateTransactionError:
        db.rollback()
        return False
    except Exception:
        db.rollback()
        raise
    log.info("RENDA FIXA %s pago: %s líquido R$ %s", ev.kind.value, inv.product.name, net)
    return True


# ------------------------------------------------------------------ simulação

@dataclass(frozen=True)
class Simulation:
    flows: list[fm.Flow]
    principal: Decimal
    total_gross: Decimal
    total_tax: Decimal
    total_net: Decimal
    profit_net: Decimal
    annualized_net_pct: Decimal | None


def simulate(product: FixedIncomeProduct, amount: Decimal, today: date, idx: IndexData) -> Simulation:
    amount = quantize_money(amount)
    flows = fm.simulate_cashflows(terms_of(product), amount, today, idx)
    gross, tax = sum((f.gross for f in flows), D(0)), sum((f.tax for f in flows), D(0))
    net = gross - tax
    days = (product.maturity_date - today).days
    annual = None
    if days > 0 and product.payment_frequency == PaymentFrequency.AT_MATURITY and amount > 0:
        annual = (((net / amount) ** (D(365) / days)) - 1) * 100
    return Simulation(flows, amount, gross, tax, net, net - amount, annual)
