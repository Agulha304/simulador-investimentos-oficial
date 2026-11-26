"""Mundo: câmbio por país, custo de vida convertido em reais e tabela da aba de economia internacional."""
import math
from datetime import date
from decimal import Decimal
from functools import lru_cache

from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.services import country_rules as cr
from backend.services.budget_service import shift_month
from backend.services.goods_rules import hash01

D = Decimal
EPOCH = date(2026, 11, 1)
BR_INFL = 4.5


@lru_cache(maxsize=4096)
def _series_value(code: str, seed: int, ref: date) -> float:
    """Câmbio (R$ por unidade) no mês `ref`: parte do câmbio inicial e deriva pela diferença de inflação (PPC) com ruído mensal."""
    c = cr.get(code)
    if code == cr.HOME:
        return 1.0
    rate, m, steps = c.fx0, EPOCH, 0
    while m < ref and steps < 600:
        m = shift_month(m, 1)
        steps += 1
        drift = math.log((1 + BR_INFL / 100) / (1 + c.infl / 100)) / 12
        noise = (hash01("fx", seed, code, m.isoformat()) - 0.5) * 2 * c.vol
        rate = min(c.fx0 * 6, max(c.fx0 / 6, rate * math.exp(drift * 0.8 + noise)))
    return rate


def _seed(db: Session, user_id: int) -> int:
    from backend.services import economy_service
    g = economy_service.get_game(db, user_id, create=False)
    return int(g.seed) if g is not None and g.seed is not None else user_id


def fx(db: Session, user_id: int, code: str, ref: date) -> Decimal:
    """Reais por 1 unidade da moeda do país no mês. O dólar acompanha o motor econômico quando a economia é dinâmica."""
    code = code.upper()
    if code == "US":
        from backend.services import economy_service
        if economy_service.is_dynamic(db, user_id):
            st = economy_service.get_state(db, user_id, ref)
            val = ((st.engine or {}).get("macro", {}).get("fx") if st is not None else None)
            if val:
                return D(str(round(float(val), 4)))
    return D(str(round(_series_value(code, _seed(db, user_id), ref), 6)))


def fx_history(db: Session, user_id: int, code: str, ref: date, n: int = 24) -> list[dict]:
    return [{"month": m.isoformat(), "rate": str(fx(db, user_id, code, m))}
            for m in (shift_month(ref, -i) for i in range(n - 1, -1, -1)) if m >= EPOCH or True]


def convert(db: Session, user_id: int, code: str, local: float | Decimal, ref: date, friction: bool = False) -> Decimal:
    """Valor em moeda local -> reais. `friction`: soma o IOF e o spread de quem manda dinheiro para o exterior."""
    v = D(str(local)) * fx(db, user_id, code, ref)
    return quantize_money(v * (1 + cr.FX_FRICTION) if friction else v)


def to_local(db: Session, user_id: int, code: str, brl: float | Decimal, ref: date) -> Decimal:
    f = fx(db, user_id, code, ref)
    return quantize_money(D(str(brl)) / f) if f else D(0)


def living_brl(db: Session, user_id: int, code: str, ref: date, lifestyle: str = "NORMAL") -> dict:
    """Custo mensal de viver no país, em reais (com IOF/spread), item a item e total."""
    local = cr.living_local(code, lifestyle)
    out = {k: str(convert(db, user_id, code, v, ref, friction=True)) for k, v in local.items()}
    out["total"] = str(convert(db, user_id, code, local["total"], ref, friction=True))
    return out


def table(db: Session, user_id: int, ref: date) -> list[dict]:
    rows = []
    for c in cr.COUNTRIES.values():
        now, prev = fx(db, user_id, c.code, ref), fx(db, user_id, c.code, shift_month(ref, -12))
        living = cr.living_local(c.code)
        rows.append({
            "code": c.code, "name": c.name, "flag": c.flag, "currency": c.currency, "symbol": c.symbol, "rate": str(now),
            "rate_start": str(D(str(c.fx0))), "change_12m_pct": round(float((now / prev - 1) * 100), 2) if prev else 0.0,
            "inflation": c.infl, "income_tax": c.income_tax, "corp_tax": c.corp_tax, "vat": c.vat, "burden": c.burden,
            "cost_index": c.cost_index, "wage_index": c.wage_index, "market": c.market, "language": c.language,
            "living_local": living, "living_brl": str(convert(db, user_id, c.code, living["total"], ref)),
            "history": fx_history(db, user_id, c.code, ref, 24) if c.code != cr.HOME else [],
        })
    return rows
