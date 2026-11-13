"""Importa todos os models para que o Alembic e o metadata os enxerguem."""
from backend.models.asset import Asset
from backend.models.chart_layout import ChartLayout
from backend.models.distribution import Dividend, DividendEligibility, DividendPayment
from backend.models.enums import (
    AssetClass, Currency, DistributionKind, EligibilityStatus, EventKind, EventStatus, FixedIncomeType,
    IndexName, Indexer, InvestmentStatus, Liquidity, PaymentFrequency, ProductSource, RateMode, RiskLevel,
    TaxRegime, TransactionSource, TransactionType,
)
from backend.models.fixed_income import FinancialEvent, FixedIncomeInvestment, FixedIncomeProduct, IndexRate
from backend.models.holding import Holding
from backend.models.portfolio import Portfolio
from backend.models.transaction import Transaction
from backend.models.user import User

__all__ = [
    "Asset", "AssetClass", "ChartLayout", "Dividend", "DividendEligibility", "DividendPayment",
    "DistributionKind", "EligibilityStatus", "EventKind", "EventStatus", "FinancialEvent", "FixedIncomeInvestment",
    "FixedIncomeProduct", "FixedIncomeType", "IndexName", "IndexRate", "Indexer", "InvestmentStatus", "Liquidity",
    "PaymentFrequency", "ProductSource", "RateMode", "RiskLevel", "TaxRegime", "Currency", "Holding", "Portfolio",
    "Transaction", "TransactionSource", "TransactionType", "User",
]
