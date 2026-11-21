"""Stop Loss / Take Profit.

Níveis são definidos na moeda do ativo. O worker compara a cotação ATUAL (na mesma
moeda) com os níveis e vende a posição inteira a mercado. Segurança contra duplicidade:

  1. a carteira e a posição são travadas (FOR UPDATE) e RELIDAS antes de agir — se o
     usuário vendeu, alterou ou removeu os níveis nesse meio-tempo, nada acontece;
  2. a venda usa idempotency_key `sltp:{holding_id}:{risk_version}` (única no banco);
  3. a venda zera a posição e apaga os níveis na mesma transação.
O preço de execução pode ser pior que o nível quando o mercado "pula" (gap).
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.core.money import quantize_price, to_decimal
from backend.models import Asset, Holding, Transaction, TransactionSource
from backend.services import ledger_service, market_data, trading_service

log = logging.getLogger(__name__)


class RiskError(ValueError):
    """Níveis inválidos (mensagem apresentável ao usuário)."""


def set_levels(db: Session, portfolio_id: int, asset: Asset, *, stop_loss: Decimal | None,
               take_profit: Decimal | None) -> Holding:
    stop = quantize_price(to_decimal(stop_loss)) if stop_loss is not None else None
    take = quantize_price(to_decimal(take_profit)) if take_profit is not None else None
    if (stop is not None and stop <= 0) or (take is not None and take <= 0):
        raise RiskError("os níveis devem ser maiores que zero")
    if stop is not None and take is not None and stop >= take:
        raise RiskError("o Stop Loss deve ser menor que o Take Profit")
    try:
        price = market_data.get_quote(asset).price if (stop is not None or take is not None) else None
    except market_data.MarketDataUnavailable as exc:
        raise RiskError("cotação indisponível; tente novamente") from exc
    # um nível já "vencido" venderia na próxima checagem: melhor recusar do que surpreender
    if price is not None:
        if stop is not None and stop >= price:
            raise RiskError(f"o Stop Loss deve ser menor que o preço atual ({price} {asset.currency})")
        if take is not None and take <= price:
            raise RiskError(f"o Take Profit deve ser maior que o preço atual ({price} {asset.currency})")

    ledger_service.lock_portfolio(db, portfolio_id)
    holding = db.execute(
        select(Holding).where(Holding.portfolio_id == portfolio_id, Holding.asset_id == asset.id).with_for_update()
    ).scalar_one_or_none()
    if holding is None or holding.quantity <= 0:
        raise RiskError("você não possui este ativo")
    holding.stop_loss, holding.take_profit = stop, take
    holding.risk_version += 1
    db.commit()
    return holding


@dataclass(frozen=True)
class Trigger:
    holding_id: int
    kind: str          # STOP_LOSS | TAKE_PROFIT


def _evaluate(holding: Holding, price: Decimal) -> str | None:
    if holding.quantity <= 0:
        return None
    if holding.stop_loss is not None and price <= holding.stop_loss:
        return "STOP_LOSS"            # se os dois dispararem (gap), proteger o capital vem primeiro
    if holding.take_profit is not None and price >= holding.take_profit:
        return "TAKE_PROFIT"
    return None


def _execute(db: Session, holding_id: int, price: Decimal) -> Transaction | None:
    """Revalida sob lock e vende. Retorna a transação, ou None se nada a fazer."""
    portfolio_id = db.scalar(select(Holding.portfolio_id).where(Holding.id == holding_id))
    if portfolio_id is None:
        return None
    ledger_service.lock_portfolio(db, portfolio_id)
    holding = db.execute(
        select(Holding).where(Holding.id == holding_id).options(joinedload(Holding.asset))
        .with_for_update(of=Holding)
    ).scalar_one()
    db.refresh(holding)
    kind = _evaluate(holding, price)
    if kind is None:
        db.rollback()
        return None
    level = holding.stop_loss if kind == "STOP_LOSS" else holding.take_profit
    label = "Stop Loss" if kind == "STOP_LOSS" else "Take Profit"
    try:
        tx = trading_service.sell(
            db, portfolio_id, holding.asset, quantity=holding.quantity,
            source=TransactionSource[kind], idempotency_key=f"sltp:{holding.id}:{holding.risk_version}",
            note=f"{label} acionado: cotação {price} {holding.asset.currency}, nível {level}",
        )
    except ledger_service.DuplicateTransactionError:
        db.rollback()
        log.info("%s já executado para holding=%s (ignorado)", label, holding_id)
        return None
    log.warning("%s executado: holding=%s %s cotação=%s nível=%s", label, holding_id, holding.asset.symbol, price, level)
    return tx


def check_all(db: Session) -> int:
    """Uma rodada do worker. Idempotente: pode rodar quantas vezes for preciso."""
    rows = db.execute(
        select(Holding.id, Asset)
        .join(Asset, Asset.id == Holding.asset_id)
        .where(Holding.quantity > 0, (Holding.stop_loss.is_not(None)) | (Holding.take_profit.is_not(None)))
    ).all()
    executed = 0
    targets = [(hid, a.id, a.provider_symbol, a.symbol) for hid, a in rows]
    db.rollback()                       # encerra a transação: a conexão NÃO fica presa enquanto esperamos a fonte externa
    prices: dict[int, Decimal | None] = {}
    syms = {aid: (psym, sym) for _, aid, psym, sym in targets}

    def fetch(aid: int):
        try:
            return aid, market_data._cached_quote(syms[aid][0], market_data.QUOTE_TTL).price
        except market_data.MarketDataUnavailable:
            log.warning("sem cotação para %s; SL/TP adiado", syms[aid][1])
            return aid, None
    if syms:                            # uma consulta por ativo (não por posição), em paralelo
        with ThreadPoolExecutor(max_workers=min(6, len(syms))) as ex:
            prices = dict(ex.map(fetch, list(syms)))
    for holding_id, asset_id, _psym, _sym in targets:
        price = prices[asset_id]
        if price is None:
            continue
        try:
            holding = db.get(Holding, holding_id)
            db.refresh(holding)
            if _evaluate(holding, price) is None:
                db.rollback()
                continue
            if _execute(db, holding_id, price):
                executed += 1
        except trading_service.TradeError as exc:
            db.rollback()
            log.warning("SL/TP holding=%s não executado agora: %s", holding_id, exc)
        except Exception:
            db.rollback()
            log.exception("erro ao processar SL/TP holding=%s", holding_id)
    return executed
