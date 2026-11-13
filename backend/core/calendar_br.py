"""Calendário de dias úteis do Brasil (feriados nacionais), usado nas contas de 252 dias úteis.

Feriados: fixos + móveis derivados da Páscoa (Carnaval, Sexta-feira Santa, Corpus Christi).
Consciência Negra (20/11) é feriado nacional desde 2024. Não inclui ponto facultativo.
"""
from calendar import monthrange
from datetime import date, timedelta
from functools import lru_cache


def easter(year: int) -> date:
    """Domingo de Páscoa (algoritmo gregoriano anônimo)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


@lru_cache(maxsize=None)
def holidays(year: int) -> frozenset[date]:
    e = easter(year)
    fixed = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 25)]
    if year >= 2024:
        fixed.append((11, 20))
    days = {date(year, m, d) for m, d in fixed}
    days |= {e - timedelta(days=48), e - timedelta(days=47), e - timedelta(days=2), e + timedelta(days=60)}
    return frozenset(days)


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in holidays(d.year)


def next_business_day(d: date) -> date:
    """O próprio dia se for útil; senão o próximo."""
    while not is_business_day(d):
        d += timedelta(days=1)
    return d


def business_days_between(start: date, end: date) -> int:
    """Dias úteis em (start, end] — a data inicial não conta, a final conta."""
    n = (end - start).days
    if n <= 0:
        return 0
    full, rem = divmod(n, 7)
    count = full * 5
    base = start + timedelta(days=full * 7)
    count += sum(1 for k in range(1, rem + 1) if (base + timedelta(days=k)).weekday() < 5)
    for year in range(start.year, end.year + 1):
        count -= sum(1 for h in holidays(year) if start < h <= end and h.weekday() < 5)
    return count


def iter_business_days(start: date, end: date):
    """Dias úteis em (start, end]."""
    d = start + timedelta(days=1)
    while d <= end:
        if is_business_day(d):
            yield d
        d += timedelta(days=1)


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))
