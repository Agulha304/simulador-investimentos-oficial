"""Mercado SIMULADO de uma partida de vida completa: relógio, preços persistidos dos ativos e índices (CDI/IPCA) simulados.

Os preços são função pura de (cotação real de ancoragem, semente, fatores guardados em cada mês). Por isso podem ser
calculados sob demanda para qualquer ativo (e salvos), sem recalcular nada que já exista: o histórico nunca muda.
A cotação REAL só entra uma vez, como ponto de partida; todo preço depois disso é do motor probabilístico.
"""
import logging
import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.core.clock import MarketClock
from backend.database import SessionLocal
from backend.models import Asset, Currency, EconomyState, GameProfile, SimPrice
from backend.services import historical_market, market_data
from backend.services.engine import markets as mk
from backend.services.engine import regimes as rg
from backend.services.engine.rng import Rng
from backend.services.market_data import Candle, MarketDataUnavailable, Quote

log = logging.getLogger(__name__)
D = Decimal
_lock = threading.Lock()


def _ym(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _step_from_state(price: float, meta: dict, st: EconomyState, seed: int) -> float:
    info = (st.engine or {}).get("info", {})
    regime = (st.engine or {}).get("regime", "SIDEWAYS")
    rv = rg.REGIMES[regime][1]
    return mk.step_price(price, meta, info.get("factors", {"mkt": 0, "mkt_us": 0, "rates": 0, "infl": 0, "growth": 0, "fx": 0, "comm": 0, "house": 0, "risk": 0}),
                         rv, info.get("class_ret", {}), Rng(seed, _ym(st.ref_month)), 1.0)


def meta_of(asset: Asset) -> dict:
    return {"symbol": asset.symbol, "asset_class": asset.asset_class.value if hasattr(asset.asset_class, "value") else str(asset.asset_class)}


def ensure_prices(db, user_id: int, asset: Asset, upto: date) -> list[SimPrice]:
    """Garante as linhas de preço do ativo até o mês `upto` (ancora na 1ª vez; depois avança mês a mês) e as devolve."""
    rows = list(db.scalars(select(SimPrice).where(SimPrice.user_id == user_id, SimPrice.asset_id == asset.id).order_by(SimPrice.ref_month)))
    game = db.scalar(select(GameProfile).where(GameProfile.user_id == user_id))
    if not rows:
        start = date(game.started_month.year, game.started_month.month, 1) if game and game.started_month else upto
        q = market_data._cached_quote(asset.provider_symbol, market_data.QUOTE_TTL)         # cotação REAL, só como âncora
        row = SimPrice(user_id=user_id, asset_id=asset.id, ref_month=start, price=q.price, source="ANCHOR")
        db.add(row)
        db.flush()
        rows = [row]
    last = rows[-1]
    if last.ref_month < upto:
        seed = game.seed if game else user_id
        price = float(last.price)
        for st in db.scalars(select(EconomyState).where(EconomyState.user_id == user_id, EconomyState.ref_month > last.ref_month,
                                                       EconomyState.ref_month <= upto).order_by(EconomyState.ref_month)):
            price = _step_from_state(price, meta_of(asset), st, seed)
            row = SimPrice(user_id=user_id, asset_id=asset.id, ref_month=st.ref_month, price=D(str(round(price, 8))), source="SIM")
            db.add(row)
            rows.append(row)
        db.flush()
    return rows


def roll_forward(db, user_id: int, new_state: EconomyState, seed: int) -> int:
    """No avanço do mês: leva a novo preço todo ativo que já tem série (os demais são calculados quando forem usados)."""
    prev = [r for r in db.scalars(select(SimPrice).where(SimPrice.user_id == user_id, SimPrice.ref_month < new_state.ref_month)
                                  .order_by(SimPrice.asset_id, SimPrice.ref_month.desc()))]
    seen: set[int] = set()
    n = 0
    for r in prev:
        if r.asset_id in seen:
            continue
        seen.add(r.asset_id)
        if db.scalar(select(SimPrice.id).where(SimPrice.user_id == user_id, SimPrice.asset_id == r.asset_id, SimPrice.ref_month == new_state.ref_month)):
            continue
        a = db.get(Asset, r.asset_id)
        price = _step_from_state(float(r.price), meta_of(a), new_state, seed)
        db.add(SimPrice(user_id=user_id, asset_id=a.id, ref_month=new_state.ref_month, price=D(str(round(price, 8))), source="SIM"))
        n += 1
    db.flush()
    return n


class SimWorld:
    """Estado mutável do relógio de uma requisição (o avanço do mês dentro dela atualiza `ref` e `fx`)."""

    def __init__(self, user_id: int, ref: date, fx: Decimal):
        self.user_id, self.ref, self.fx = user_id, ref, fx
        self.cache: dict[int, tuple[Decimal, Decimal | None]] = {}

    def advance(self, ref: date, fx: Decimal) -> None:
        self.ref, self.fx = ref, fx
        self.cache.clear()

    def quote(self, asset: Asset) -> Quote:
        hit = self.cache.get(asset.id)
        if hit is None:
            hit = self._load(asset)
            self.cache[asset.id] = hit
        price, prev = hit
        return Quote(price, asset.currency, datetime(self.ref.year, self.ref.month, self.ref.day, tzinfo=UTC), prev)

    def _load(self, asset: Asset):
        with _lock, SessionLocal() as db:                  # sessão própria: lê/grava só fatos já definidos (idempotente)
            try:
                rows = ensure_prices(db, self.user_id, asset, self.ref)
                db.commit()
            except IntegrityError:
                db.rollback()
                rows = list(db.scalars(select(SimPrice).where(SimPrice.user_id == self.user_id, SimPrice.asset_id == asset.id)
                                       .order_by(SimPrice.ref_month)))
            upto = [r for r in rows if r.ref_month <= self.ref]
            if not upto:
                raise MarketDataUnavailable(f"sem preço simulado para {asset.symbol}")
            prev = upto[-2].price if len(upto) > 1 else None
            return upto[-1].price, prev

    def history(self, asset: Asset, period: str) -> list[Candle]:
        if period in market_data.INTRADAY_RANGES:
            return []
        self.quote(asset)
        with SessionLocal() as db:
            rows = [r for r in db.scalars(select(SimPrice).where(SimPrice.user_id == self.user_id, SimPrice.asset_id == asset.id)
                                          .order_by(SimPrice.ref_month)) if r.ref_month <= self.ref]
        months = {"1mo": 2, "6mo": 7, "1y": 13, "5y": 61, "max": 10_000}[period]
        out, prev = [], None
        anchor = next((r.ref_month for r in rows if r.source == "ANCHOR"), None)
        if anchor is not None:                              # passado REAL até o mês de partida + futuro simulado depois dele
            try:
                for m, c in historical_market.monthly(asset.provider_symbol):
                    if m < anchor:
                        out.append(c)
                        prev = c.close
            except MarketDataUnavailable:
                pass
        for r in rows:
            o = prev if prev is not None else r.price
            ts = int(datetime(r.ref_month.year, r.ref_month.month, 1, tzinfo=UTC).timestamp())
            out.append(Candle(ts, o, max(o, r.price), min(o, r.price), r.price, D(0)))
            prev = r.price
        return out[-months:]

    def fx_rate(self, currency: Currency) -> Decimal:
        return self.fx if currency == Currency.USD else D(1)


def clock_for(user_id: int, ref: date, fx: Decimal) -> tuple[MarketClock, SimWorld]:
    w = SimWorld(user_id, ref, fx)
    return MarketClock("SIMULATED", ref, quote_fn=w.quote, fx_fn=w.fx_rate, history_fn=w.history,
                       index_fn=lambda daily, monthly: inject_indices(user_id, daily, monthly), world=w), w


def inject_indices(user_id: int, daily: dict, monthly: dict) -> None:
    """CDI/Selic e IPCA do mundo simulado: derivados da taxa de juros e da inflação de cada mês simulado."""
    from backend.models import IndexName
    from backend.services.index_data import _daily_from_annual
    with SessionLocal() as db:
        states = list(db.scalars(select(EconomyState).where(EconomyState.user_id == user_id).order_by(EconomyState.ref_month)))
    for st in states:
        m = st.ref_month
        monthly.setdefault(IndexName.IPCA, {})[m] = D(str(round((st.monthly_changes or {}).get("geral", 0.0), 4)))
        rate = _daily_from_annual(D(str(max(0.5, float(st.interest) - 0.1))))
        nxt = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        d = m
        while d < nxt:
            if d.weekday() < 5:
                daily.setdefault(IndexName.CDI, {})[d] = rate
                daily.setdefault(IndexName.SELIC, {})[d] = rate
            d += timedelta(days=1)
