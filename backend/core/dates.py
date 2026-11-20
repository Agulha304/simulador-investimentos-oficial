"""Datas do domínio: o 'hoje' do simulador é o dia civil em São Paulo."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")


def today_br() -> date:
    from backend.core.clock import get_clock          # import tardio: o relógio é opcional
    clock = get_clock()
    return clock.today if clock is not None else datetime.now(TZ).date()
