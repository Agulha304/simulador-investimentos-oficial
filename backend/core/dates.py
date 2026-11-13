"""Datas do domínio: o 'hoje' do simulador é o dia civil em São Paulo."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")


def today_br() -> date:
    return datetime.now(TZ).date()
