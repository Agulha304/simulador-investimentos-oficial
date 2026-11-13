"""Dividendos, rendimentos de FIIs, distribuições de REITs/ETFs.

Fluxo (cada etapa é idempotente e protegida por constraints únicas no banco):

  1. DESCOBERTA   consulta a fonte para os ativos que alguém já comprou e grava `Dividend`
                  (único por ativo + data EX + valor).
  2. ELEGIBILIDADE para cada evento novo, reconstrói pelas TRANSAÇÕES (não pela posição atual)
                  quanto cada carteira possuía na data EX e grava `DividendEligibility`
                  (única por carteira + evento).
  3. PAGAMENTO    quando chega a data prevista, credita quantidade × valor (convertido para BRL)
                  menos imposto, grava `DividendPayment` e uma `Transaction` com chave
                  `dividend:{evento}:{carteira}` (única).

Regra da data EX: tem direito quem possuía o ativo ANTES dela. Compra feita na própria
data EX não conta; venda feita na data EX não retira o direito. Datas são do fuso de São Paulo.
"""
import logging
from datetime import UTC, date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.core.money import quantize_money, quantize_price
from backend.models import (
    Asset, AssetClass, Dividend, DividendEligibility, DividendPayment, DistributionKind,
    EligibilityStatus, Transaction, TransactionSource, TransactionType,
)
from backend.services import ledger_service, market_data, tax_service
from backend.services.ledger_service import CashMovement

log = logging.getLogger(__name__)
TZ = ZoneInfo("America/Sao_Paulo")

# A fonte só informa a data EX; o pagamento é estimado com estes prazos (dias após a data EX).
PAY_LAG_DAYS = {("BR", AssetClass.FII): 14, ("BR", AssetClass.STOCK): 30, ("BR", AssetClass.ETF): 30,
                ("US", AssetClass.REIT): 21, ("US", AssetClass.STOCK): 21, ("US", AssetClass.ETF): 21}
DEFAULT_LAG = 21


def local_date(dt: datetime) -> date:
    return dt.astimezone(TZ).date()


def estimate_pay_date(asset: Asset, ex_date: date) -> date:
    from datetime import timedelta
    return ex_date + timedelta(days=PAY_LAG_DAYS.get((asset.country or "", asset.asset_class), DEFAULT_LAG))


def kind_for(asset: Asset) -> DistributionKind:
    return DistributionKind.RENDIMENTO if asset.asset_class == AssetClass.FII else DistributionKind.DIVIDEND


def quantities_at(db: Session, asset_id: int, ex_date: date) -> dict[int, Decimal]:
    """{portfolio_id: quantidade possuída antes da data EX}, reconstruída das transações."""
    cutoff = datetime.combine(ex_date, time.min, tzinfo=TZ)
    signed = func.sum(case((Transaction.type == TransactionType.BUY, Transaction.quantity),
                           (Transaction.type == TransactionType.SELL, -Transaction.quantity), else_=0))
    rows = db.execute(
        select(Transaction.portfolio_id, signed)
        .where(Transaction.asset_id == asset_id, Transaction.created_at < cutoff,
               Transaction.type.in_([TransactionType.BUY, TransactionType.SELL]))
        .group_by(Transaction.portfolio_id).having(signed > 0)
    ).all()
    return {pid: qty for pid, qty in rows}


# ------------------------------------------------------------------ 1 + 2

def discover(db: Session, asset_ids: list[int] | None = None) -> int:
    """Descobre eventos novos e gera elegibilidades. Retorna quantas elegibilidades novas."""
    q = (select(Asset, func.min(Transaction.created_at))
         .join(Transaction, Transaction.asset_id == Asset.id)
         .where(Transaction.type == TransactionType.BUY).group_by(Asset.id))
    if asset_ids is not None:
        q = q.where(Asset.id.in_(asset_ids))
    created = 0
    for asset, first_buy in db.execute(q).all():
        try:
            events = market_data.get_dividends(asset)
        except market_data.MarketDataUnavailable:
            log.warning("dividendos indisponíveis para %s; tentará de novo", asset.symbol)
            continue
        first_day = local_date(first_buy)
        for ev in events:
            if ev.ex_date <= first_day:       # ninguém tinha o ativo antes dessa data EX
                continue
            db.execute(pg_insert(Dividend).values(
                asset_id=asset.id, kind=kind_for(asset), ex_date=ev.ex_date,
                pay_date=estimate_pay_date(asset, ev.ex_date), pay_date_estimated=True,
                amount_per_unit=quantize_price(ev.amount), currency=asset.currency,
            ).on_conflict_do_nothing(constraint="uq_dividend_asset_ex_amount"))
        db.commit()
        created += _generate_eligibilities(db, asset)
    return created


def _generate_eligibilities(db: Session, asset: Asset) -> int:
    pending = db.scalars(select(Dividend).where(Dividend.asset_id == asset.id, Dividend.processed_at.is_(None))
                         .order_by(Dividend.ex_date)).all()
    total = 0
    for div in pending:
        for portfolio_id, qty in quantities_at(db, asset.id, div.ex_date).items():
            inserted = db.execute(pg_insert(DividendEligibility).values(
                portfolio_id=portfolio_id, dividend_id=div.id, quantity=qty, pay_date=div.pay_date,
                status=EligibilityStatus.PENDING,
            ).on_conflict_do_nothing(constraint="uq_eligibility_portfolio_dividend")
              .returning(DividendEligibility.id)).scalar_one_or_none()    # None = já existia (rowcount não é confiável)
            total += 1 if inserted is not None else 0
        div.processed_at = datetime.now(UTC)
        db.commit()
    return total


# ------------------------------------------------------------------ 3

def pay_one(db: Session, eligibility_id: int) -> bool:
    """Paga uma elegibilidade. Retorna True se pagou agora. Seguro contra reexecução e concorrência."""
    portfolio_id = db.scalar(select(DividendEligibility.portfolio_id).where(DividendEligibility.id == eligibility_id))
    if portfolio_id is None:
        return False
    try:
        ledger_service.lock_portfolio(db, portfolio_id)      # mesma ordem de locks dos outros fluxos
        elig = db.execute(select(DividendEligibility).where(DividendEligibility.id == eligibility_id)
                          .with_for_update()).scalar_one()
        db.refresh(elig)
        if elig.status != EligibilityStatus.PENDING:
            db.rollback()
            return False
        div = db.get(Dividend, elig.dividend_id)
        asset = db.get(Asset, div.asset_id)
        try:
            fx = market_data.get_fx_rate(div.currency)
        except market_data.MarketDataUnavailable:
            db.rollback()
            log.warning("sem câmbio para pagar dividendo %s; adiado", div.id)
            return False
        gross = quantize_money(elig.quantity * div.amount_per_unit * fx)
        tax = tax_service.distribution_tax(asset, div.kind, gross)
        net = quantize_money(gross - tax.tax_brl)
        if net <= 0:
            elig.status = EligibilityStatus.CANCELLED
            db.commit()
            log.info("distribuição %s/%s com líquido zero: cancelada", div.id, portfolio_id)
            return False
        tx = ledger_service.record(db, portfolio_id, CashMovement(
            type=TransactionType.DIVIDEND, source=TransactionSource.DISTRIBUTION_WORKER, asset_id=asset.id,
            gross_amount_brl=gross, tax_brl=tax.tax_brl, cash_amount_brl=net, quantity=elig.quantity,
            unit_price=div.amount_per_unit, price_currency=div.currency, fx_rate=fx,
            unit_price_brl=quantize_price(div.amount_per_unit * fx),
            idempotency_key=f"dividend:{div.id}:{portfolio_id}",
            note=f"{div.kind.value.title()} {asset.symbol} (EX {div.ex_date:%d/%m/%Y}). {tax.description}",
        ))
        db.add(DividendPayment(eligibility_id=elig.id, transaction_id=tx.id, gross_brl=gross,
                               tax_brl=tax.tax_brl, net_brl=net, fx_rate=fx))
        elig.status = EligibilityStatus.PAID
        db.commit()
    except ledger_service.DuplicateTransactionError:
        db.rollback()
        log.info("pagamento %s já registrado (ignorado)", eligibility_id)
        return False
    except Exception:
        db.rollback()
        raise
    log.info("PROVENTO pago: %s %s x %s = R$ %s (líquido R$ %s)", asset.symbol, elig.quantity,
             div.amount_per_unit, gross, net)
    return True


def pay_due(db: Session, today: date | None = None, portfolio_id: int | None = None) -> int:
    today = today or datetime.now(TZ).date()
    q = select(DividendEligibility.id).where(DividendEligibility.status == EligibilityStatus.PENDING,
                                             DividendEligibility.pay_date <= today)
    if portfolio_id is not None:
        q = q.where(DividendEligibility.portfolio_id == portfolio_id)
    paid = 0
    for eid in db.scalars(q.order_by(DividendEligibility.id)).all():
        try:
            paid += pay_one(db, eid)
        except Exception:
            log.exception("erro ao pagar elegibilidade %s", eid)
    return paid
