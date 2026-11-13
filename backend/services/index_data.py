"""Índices econômicos (CDI, Selic, IPCA, IGP-M): camada de dados ISOLADA.

Fonte: API SGS do Banco Central (pública e oficial). O histórico é guardado em `index_rates`,
então o cálculo de rendimento é determinístico e funciona sem rede. Para trocar de fonte,
implemente `IndexProvider`.

Projeções (usadas para datas futuras / ainda não publicadas):
  * CDI e Selic: mantém a última taxa diária conhecida;
  * IPCA e IGP-M: média dos últimos 12 meses publicados.
"""
import logging
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.core.calendar_br import business_days_between, iter_business_days
from backend.core.money import to_decimal
from backend.models import IndexName, IndexRate

log = logging.getLogger(__name__)
D = Decimal
DAILY = (IndexName.CDI, IndexName.SELIC)
MONTHLY = (IndexName.IPCA, IndexName.IGPM)


class IndexDataUnavailable(Exception):
    pass


class IndexProvider(Protocol):
    def fetch(self, name: IndexName, start: date, end: date) -> list[tuple[date, Decimal]]: ...


class BCBProvider:
    """SGS: 12 = CDI (% a.d.), 11 = Selic (% a.d.), 433 = IPCA (% a.m.), 189 = IGP-M (% a.m.)."""
    SERIES = {IndexName.CDI: 12, IndexName.SELIC: 11, IndexName.IPCA: 433, IndexName.IGPM: 189}
    URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"

    def fetch(self, name: IndexName, start: date, end: date) -> list[tuple[date, Decimal]]:
        params = {"formato": "json", "dataInicial": start.strftime("%d/%m/%Y"), "dataFinal": end.strftime("%d/%m/%Y")}
        last: Exception | None = None
        for _ in range(3):
            try:
                r = httpx.get(self.URL.format(code=self.SERIES[name]), params=params, timeout=30.0)
                r.raise_for_status()
                out = []
                for row in r.json():
                    d, m, y = row["data"].split("/")
                    out.append((date(int(y), int(m), int(d)), to_decimal(row["valor"])))
                return out
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                last = exc
        raise IndexDataUnavailable(f"falha ao consultar {name} no Banco Central: {last}")


_provider: IndexProvider = BCBProvider()


def set_provider(p: IndexProvider) -> None:
    global _provider
    _provider = p


def sync(db: Session, today: date, names: list[IndexName] | None = None, history_years: int = 6) -> int:
    """Baixa o que falta de cada índice. Idempotente (upsert por índice+data). Retorna linhas novas."""
    total = 0
    for name in names or list(IndexName):
        last = db.scalar(select(func.max(IndexRate.ref_date)).where(IndexRate.index_name == name))
        start = (last + timedelta(days=1)) if last else today - timedelta(days=365 * history_years)
        if name in MONTHLY and last:
            start = last                       # o último mês pode ter sido revisado/ainda incompleto
        try:
            rows = _provider.fetch(name, start, today)
        except IndexDataUnavailable as exc:
            log.warning("%s", exc)
            continue
        for i in range(0, len(rows), 500):                      # upsert em lotes
            stmt = pg_insert(IndexRate).values([{"index_name": name, "ref_date": d, "value": v} for d, v in rows[i:i + 500]])
            db.execute(stmt.on_conflict_do_update(constraint="uq_index_rate", set_={"value": stmt.excluded.value}))
        total += len(rows)
        db.commit()
    return total


@dataclass
class IndexData:
    """Fotografia imutável dos índices em memória: as contas de rendimento recebem isto,
    sem tocar no banco (testáveis com dados sintéticos)."""
    daily: dict[IndexName, dict[date, Decimal]] = field(default_factory=dict)      # % ao dia útil
    monthly: dict[IndexName, dict[date, Decimal]] = field(default_factory=dict)    # % ao mês (chave: dia 1)
    fallback_daily: dict[IndexName, Decimal] = field(default_factory=dict)
    fallback_monthly: dict[IndexName, Decimal] = field(default_factory=dict)

    def __post_init__(self):
        self._keys = {n: sorted(s) for n, s in self.daily.items()}

    # ------------------------------------------------------------ taxas diárias (CDI, Selic)
    def last_known_day(self, name: IndexName) -> date | None:
        keys = self._keys.get(name)
        return keys[-1] if keys else None

    def daily_rate(self, name: IndexName, d: date) -> Decimal:
        keys = self._keys.get(name)
        if not keys:
            return self.fallback_daily[name]
        series = self.daily[name]
        if d in series:
            return series[d]
        i = bisect_right(keys, d)
        return series[keys[max(i - 1, 0)]]      # lacuna: última taxa conhecida (ou a primeira, se antes do histórico)

    def daily_factor(self, name: IndexName, start: date, end: date, multiplier: Decimal = D(1)) -> Decimal:
        """Π (1 + taxa_dia × multiplicador) sobre os dias úteis em (start, end]. Trecho sem dados publicados
        usa a última taxa conhecida elevada ao nº de dias úteis (projeção)."""
        if end <= start:
            return D(1)
        known = self.last_known_day(name)
        cut = min(end, known) if known else start
        factor = D(1)
        for d in iter_business_days(start, cut):
            factor *= 1 + self.daily_rate(name, d) / 100 * multiplier
        proj_start = max(start, cut)
        n = business_days_between(proj_start, end)
        if n:
            factor *= (1 + self.daily_rate(name, end) / 100 * multiplier) ** n
        return factor

    def annual_rate(self, name: IndexName) -> Decimal:
        """Taxa anualizada (252 d.u.) a partir da última taxa diária conhecida, em %."""
        known = self.last_known_day(name)
        daily = self.daily_rate(name, known) if known else self.fallback_daily[name]
        return ((1 + daily / 100) ** 252 - 1) * 100

    # ------------------------------------------------------------ índices mensais (IPCA, IGP-M)
    def monthly_rate(self, name: IndexName, month_start: date) -> Decimal:
        series = self.monthly.get(name) or {}
        if month_start in series:
            return series[month_start]
        if not series:
            return self.fallback_monthly[name]
        last12 = [series[k] for k in sorted(series)[-12:]]
        return sum(last12, D(0)) / len(last12)         # projeção: média dos últimos 12 meses

    def accumulated_12m(self, name: IndexName) -> Decimal:
        series = self.monthly.get(name) or {}
        if not series:
            return ((1 + self.fallback_monthly[name] / 100) ** 12 - 1) * 100
        f = D(1)
        for k in sorted(series)[-12:]:
            f *= 1 + series[k] / 100
        return (f - 1) * 100

    def monthly_factor(self, name: IndexName, start: date, end: date) -> Decimal:
        """Correção por índice mensal, rateada por dias corridos dentro de cada mês, em (start, end]."""
        if end <= start:
            return D(1)
        factor = D(1)
        cursor = start
        while cursor < end:
            month_start = (cursor + timedelta(days=1)).replace(day=1)       # o dia cursor+1 é o 1º a render
            nxt = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            days_in_month = (nxt - month_start).days
            seg_end = min(end, nxt - timedelta(days=1))
            days = (seg_end - cursor).days
            factor *= (1 + self.monthly_rate(name, month_start) / 100) ** (D(days) / days_in_month)
            cursor = seg_end
        return factor


def load(db: Session, since_years: int = 7) -> IndexData:
    s = get_settings()
    daily: dict[IndexName, dict[date, Decimal]] = {}
    monthly: dict[IndexName, dict[date, Decimal]] = {}
    cutoff = date.today() - timedelta(days=365 * since_years)
    for name, ref_date, value in db.execute(
        select(IndexRate.index_name, IndexRate.ref_date, IndexRate.value).where(IndexRate.ref_date >= cutoff)
    ):
        (daily if name in DAILY else monthly).setdefault(name, {})[ref_date] = value
    return IndexData(
        daily=daily, monthly=monthly,
        fallback_daily={IndexName.CDI: _daily_from_annual(s.fallback_cdi_annual),
                        IndexName.SELIC: _daily_from_annual(s.fallback_selic_annual)},
        fallback_monthly={IndexName.IPCA: s.fallback_ipca_monthly, IndexName.IGPM: s.fallback_igpm_monthly},
    )


def _daily_from_annual(annual_pct: Decimal) -> Decimal:
    return ((1 + annual_pct / 100) ** (D(1) / 252) - 1) * 100
