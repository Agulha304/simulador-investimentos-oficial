"""Importa todos os models para que o Alembic e o metadata os enxerguem."""
from backend.models.asset import Asset
from backend.models.enums import AssetClass, Currency, TransactionSource, TransactionType
from backend.models.holding import Holding
from backend.models.portfolio import Portfolio
from backend.models.transaction import Transaction
from backend.models.user import User

__all__ = [
    "Asset", "AssetClass", "Currency", "Holding", "Portfolio",
    "Transaction", "TransactionSource", "TransactionType", "User",
]
