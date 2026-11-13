"""Tesouro Direto: camada de dados ISOLADA.

Fonte: conjunto de dados aberto "Preço e Taxa do Tesouro Direto" (Tesouro Transparente / Tesouro Nacional),
um CSV oficial atualizado nos dias úteis. Para cada título ficamos com a linha mais recente.
Para trocar de fonte, implemente `TreasuryProvider`.
"""
import csv
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

import httpx

from backend.core.money import to_decimal

log = logging.getLogger(__name__)

CSV_URL = ("https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/"
           "resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv")


class TreasuryUnavailable(Exception):
    pass


@dataclass(frozen=True)
class TreasuryQuote:
    type_name: str            # "Tesouro Prefixado", "Tesouro IPCA+", ...
    maturity: date
    base_date: date
    buy_rate: Decimal         # % a.a. (taxa de compra); no Selic é o spread sobre a Selic
    sell_rate: Decimal
    buy_pu: Decimal           # preço unitário de compra
    sell_pu: Decimal


class TreasuryProvider(Protocol):
    def fetch_latest(self) -> list[TreasuryQuote]: ...


def _num(text: str) -> Decimal:
    return to_decimal(text.strip().replace(".", "").replace(",", "."))


def _day(text: str) -> date:
    return datetime.strptime(text.strip(), "%d/%m/%Y").date()


def parse_latest(lines) -> list[TreasuryQuote]:
    """Lê o CSV (separador ';', decimais com vírgula) guardando só a linha mais recente de cada título."""
    reader = csv.DictReader(lines, delimiter=";")
    latest: dict[tuple[str, date], TreasuryQuote] = {}
    for row in reader:
        try:
            q = TreasuryQuote(
                type_name=row["Tipo Titulo"].strip(), maturity=_day(row["Data Vencimento"]),
                base_date=_day(row["Data Base"]), buy_rate=_num(row["Taxa Compra Manha"]),
                sell_rate=_num(row["Taxa Venda Manha"]), buy_pu=_num(row["PU Compra Manha"]),
                sell_pu=_num(row["PU Venda Manha"]),
            )
        except (KeyError, ValueError, ArithmeticError):
            continue                       # linha sem oferta no dia (campos vazios)
        if q.buy_pu <= 0 or q.sell_pu <= 0:
            continue
        key = (q.type_name, q.maturity)
        if key not in latest or q.base_date > latest[key].base_date:
            latest[key] = q
    return list(latest.values())


class TesouroTransparenteProvider:
    def fetch_latest(self) -> list[TreasuryQuote]:
        try:
            with httpx.stream("GET", CSV_URL, timeout=120.0, follow_redirects=True) as r:
                r.raise_for_status()
                return parse_latest(r.iter_lines())
        except httpx.HTTPError as exc:
            raise TreasuryUnavailable(f"falha ao baixar o CSV do Tesouro: {exc}") from exc


_provider: TreasuryProvider = TesouroTransparenteProvider()


def set_provider(p: TreasuryProvider) -> None:
    global _provider
    _provider = p


def fetch_latest() -> list[TreasuryQuote]:
    return _provider.fetch_latest()
