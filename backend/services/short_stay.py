"""Hospedagem de temporada (o "Airbnb" do jogo).

Rende mais que o aluguel fixo, mas dá trabalho: ou você gasta horas do seu mês cuidando dos hóspedes (SELF) ou paga um
gestor (HIRED, 20% da receita). Sem tempo para cuidar, a nota cai e as reservas também. O resultado de cada mês é
calculado UMA vez (tabela `short_stay_months`) e depende da cidade, da estação, da economia (demanda, crises) e da nota.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.money import quantize_money
from backend.models import Good, RealEstateDetails, ShortStayMonth
from backend.services import br_taxes, goods_rules as rules
from backend.services.life_rules import hash01

D = Decimal
STR_HOURS = 14                  # horas/mês de gestão própria por imóvel
PLATFORM_PCT = D("3")           # taxa da plataforma de reservas
MANAGER_PCT = D("20")           # gestor contratado
CLEANING_PER_STAY = D("90")     # limpeza por hospedagem
AVG_STAY_NIGHTS = 3
TOURIST = ("Florianópolis", "Gramado", "Salvador", "Fortaleza", "Rio de Janeiro", "Recife", "Bombinhas", "Jurerê")


def base_occupancy(location: str, property_type: str) -> float:
    city = br_taxes.city_of(location)
    base = 0.68 if city in TOURIST else 0.58 if city in ("São Paulo", "Belo Horizonte", "Curitiba", "Porto Alegre", "Brasília") else 0.48
    return base + (0.03 if property_type == "house" else 0.0)


def compute(good: Good, det: RealEstateDetails, ref: date, *, demand: float, hours_ok: bool, services_index: float) -> dict:
    market = float(rules.market_nightly(good.category, good.current_value))
    nightly = float(det.nightly_rate or market)
    occ = base_occupancy(good.location, det.property_type)
    occ *= 1 + (hash01("stay-season", good.id, ref.isoformat()) - 0.5) * 0.30                      # estação (±15%)
    occ *= max(0.5, min(1.2, demand)) ** 1.2                                                       # economia: demanda e crises
    occ *= 0.6 + det.str_rating / 200.0                                                            # nota dos hóspedes
    ratio = nightly / market if market else 1.0
    occ *= max(0.35, 1 - 0.9 * (ratio - 1.3)) if ratio > 1.3 else (1 + min(0.10, (1.0 - ratio) * 0.4) if ratio < 1 else 1.0)   # preço
    hired = det.management == "HIRED"
    note = "gestor contratado" if hired else "gestão própria"
    rating = det.str_rating
    if hired:
        rating = rating + (1 if rating < 82 else -1 if rating > 82 else 0)
    elif hours_ok:
        rating = min(98, rating + 1)
    else:
        occ *= 0.75
        rating = max(50, rating - 3)
        note = "sem tempo para cuidar dos hóspedes: nota e reservas caíram"
    occ = max(0.05, min(0.95, occ))
    nights = int(round(30 * occ))
    gross = quantize_money(D(nights) * D(str(nightly)))
    stays = max(1, round(nights / AVG_STAY_NIGHTS)) if nights else 0
    return {"nights": nights, "occupancy_pct": D(str(round(occ * 100, 1))), "nightly": quantize_money(D(str(nightly))), "gross": gross,
            "platform_fee": quantize_money(gross * PLATFORM_PCT / 100), "manager_fee": quantize_money(gross * MANAGER_PCT / 100) if hired else D("0.00"),
            "cleaning": quantize_money(D(stays) * CLEANING_PER_STAY * D(str(services_index))), "iss": quantize_money(gross * br_taxes.ISS_STAY_PCT / 100),
            "rating": rating, "note": note}


def ensure_month(db: Session, good: Good, det: RealEstateDetails, ref: date, *, demand: float, hours_ok: bool, services_index: float,
                 replace: bool = False) -> ShortStayMonth:
    """Calcula o mês UMA vez. `replace` refaz o mês ABERTO quando você muda diária/gestão (a nota só muda na virada do mês)."""
    row = db.scalar(select(ShortStayMonth).where(ShortStayMonth.good_id == good.id, ShortStayMonth.ref_month == ref))
    if row is not None and not replace:
        return row
    if row is not None:
        db.delete(row)
        db.flush()
    r = compute(good, det, ref, demand=demand, hours_ok=hours_ok, services_index=services_index)
    if not replace:
        det.str_rating = r["rating"]
    else:
        r["rating"] = det.str_rating
    row = ShortStayMonth(good_id=good.id, ref_month=ref, **r)
    db.add(row)
    db.flush()
    return row


def taxable_net(row: ShortStayMonth) -> Decimal:
    return row.gross - row.platform_fee - row.manager_fee
