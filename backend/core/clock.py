"""Relógio de mercado por partida.

Sem relógio, o simulador usa cotações e datas REAIS (comportamento original). Dentro de uma partida:
  * HISTORICAL (modo treino): o "hoje" é uma data do passado e os preços vêm de séries reais daquela data;
  * SIMULATED (vida financeira completa): o "hoje" é o mês simulado e os preços vêm do motor probabilístico.
O relógio vive num ContextVar definido pela dependência da requisição: nenhum serviço precisa receber a data.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterator


@dataclass(frozen=True)
class MarketClock:
    kind: str                                   # HISTORICAL | SIMULATED
    today: date
    quote_fn: Callable                          # asset -> Quote (moeda do ativo)
    fx_fn: Callable | None = None               # Currency -> Decimal (taxa para BRL)
    history_fn: Callable | None = None          # (asset, period) -> list[Candle]
    index_fn: Callable | None = None            # (daily, monthly) -> injeta CDI/IPCA simulados nos índices
    world: object | None = None                 # estado mutável do mundo simulado (avança dentro da requisição)


_clock: ContextVar[MarketClock | None] = ContextVar("market_clock", default=None)


def get_clock() -> MarketClock | None:
    return _clock.get()


@contextmanager
def use_clock(clock: MarketClock | None) -> Iterator[None]:
    token = _clock.set(clock)
    try:
        yield
    finally:
        _clock.reset(token)


def set_clock(clock: MarketClock | None):
    return _clock.set(clock)


def reset_clock(token) -> None:
    _clock.reset(token)
