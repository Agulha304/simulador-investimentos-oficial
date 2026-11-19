"""Fachada única de preços: todo módulo que precisa corrigir um valor pela inflação passa por aqui.

Assim a economia é UMA só (não há valores econômicos independentes por módulo). A implementação real
(índices por categoria, eventos) vive em `economy_service`; sem estado econômico dinâmico o fator é 1.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session


def price_factor(db: Session, user_id: int, ref_month: date, category: str) -> Decimal:
    """Índice acumulado da categoria no mês (1.0000 = preços-base)."""
    from backend.services import economy_service            # import tardio: evita ciclo
    return economy_service.index_value(db, user_id, ref_month, category)


def scale(db: Session, user_id: int, ref_month: date, category: str, amount: Decimal | int | float) -> Decimal:
    return (Decimal(str(amount)) * price_factor(db, user_id, ref_month, category)).quantize(Decimal("0.01"))
