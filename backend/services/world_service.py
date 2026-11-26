"""Mundo: câmbio por país, custo de vida convertido em reais e tabela da aba de economia internacional."""
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.services import country_rules as cr
from backend.services import world_economy as we
from backend.services.budget_service import shift_month
from backend.services.goods_rules import hash01

D = Decimal
EPOCH = we.EPOCH


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
    return D(str(round(we.fx(_seed(db, user_id), code, ref), 6)))


def price_level(db: Session, user_id: int, code: str, ref: date) -> D:
    """Nível de preços SIMULADO do país (1,00 no início do jogo): a inflação do país acumulada."""
    return D(str(round(we.price_level(_seed(db, user_id), code, ref), 6)))


def demand(db: Session, user_id: int, code: str, ref: date) -> float:
    """Fator de demanda do país (recessão < 1 < boom)."""
    return we.demand(_seed(db, user_id), code, ref)


def fx_history(db: Session, user_id: int, code: str, ref: date, n: int = 24) -> list[dict]:
    return [{"month": m.isoformat(), "rate": str(fx(db, user_id, code, m))}
            for m in (max(shift_month(ref, -i), EPOCH) for i in range(n - 1, -1, -1))]


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
    pl = float(price_level(db, user_id, code, ref))                       # a inflação simulada do país encarece a vida lá
    out = {k: str(convert(db, user_id, code, v * pl, ref, friction=True)) for k, v in local.items()}
    out["total"] = str(convert(db, user_id, code, local["total"] * pl, ref, friction=True))
    return out


def table(db: Session, user_id: int, ref: date) -> list[dict]:
    seed = _seed(db, user_id)
    rows = []
    for c in cr.COUNTRIES.values():
        now, prev = fx(db, user_id, c.code, ref), fx(db, user_id, c.code, shift_month(ref, -12))
        st = we.state(seed, c.code, ref)
        pl = st["pl"]
        living = cr.living_local(c.code)
        rows.append({
            "code": c.code, "name": c.name, "flag": c.flag, "currency": c.currency, "symbol": c.symbol, "rate": str(now),
            "rate_start": str(D(str(c.fx0))), "change_12m_pct": round(float((now / prev - 1) * 100), 2) if prev else 0.0,
            "inflation": round(st["infl"], 1), "growth": round(st["growth"], 1), "interest": round(st["rate"], 1), "confidence": round(st["confidence"]),
            "demand": round(st["demand"], 2), "price_level": round(pl, 3), "crisis": st["crisis"],
            "income_tax": c.income_tax, "corp_tax": c.corp_tax, "vat": c.vat, "burden": c.burden,
            "cost_index": c.cost_index, "wage_index": c.wage_index, "market": c.market, "language": c.language,
            "living_local": {k: round(v * pl, 2) for k, v in living.items()}, "living_brl": str(convert(db, user_id, c.code, living["total"] * pl, ref)),
            "history": fx_history(db, user_id, c.code, ref, 24) if c.code != cr.HOME else [],
            "inflation_series": we.series(seed, c.code, ref, 24, "infl"),
        })
    return rows


def events(db: Session, user_id: int, ref: date) -> list[dict]:
    """Crises mundiais e dos países (em andamento e passadas), da mais recente para a mais antiga."""
    out = []
    for c in we.crises(_seed(db, user_id), ref):
        out.append({"country": c.code, "country_name": "Mundo inteiro" if c.code == "*" else cr.get(c.code).name, "flag": "🌍" if c.code == "*" else cr.get(c.code).flag,
                    "kind": c.kind, "label": c.label, "start": c.start.isoformat(), "end": c.end.isoformat(), "active": c.active(ref),
                    "intensity": round(c.intensity, 2)})
    return sorted(out, key=lambda e: e["start"], reverse=True)
