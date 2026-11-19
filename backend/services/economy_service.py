"""Economia simulada (etapa 5). Esta primeira versão só expõe o índice de preços; ver seções abaixo."""
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

ONE = Decimal("1.0000")


def index_value(db: Session, user_id: int, ref_month: date, category: str) -> Decimal:
    return ONE
