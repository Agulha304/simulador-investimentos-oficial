"""Importa todos os models para que o Alembic e o metadata os enxerguem."""
from backend.models.asset import Asset
from backend.models.budget import (
    BudgetCategory, BudgetItem, FinanceAccount, LedgerEntry, RecurringItem, RecurringItemVersion, SimMonth,
)
from backend.models.chart_layout import ChartLayout
from backend.models.company import (
    Company, CompanyCost, CompanyEvent, CompanyLease, CompanyLoan, CompanyLoanInstallment, CompanyMonth, Employee,
    InventoryItem,
)
from backend.models.distribution import Dividend, DividendEligibility, DividendPayment
from backend.models.enums import (
    AccountKind, AmortizationSystem, CompanyCostKind, CompanyEventType, CompanySegment, CompanySize, CompanyStatus,
    EmployeeLevel, EmployeeStatus, LeaseKind, AssetClass, Condition, CostKind, GoodCategory, GoodEventType, GoodStatus,
    InstallmentStatus, LoanStatus, Occupancy, REAL_ESTATE, ValueSource, Currency, EntryOrigin, FlowKind, Frequency, MonthStatus, DistributionKind, EligibilityStatus, EventKind, EventStatus, FixedIncomeType,
    IndexName, Indexer, InvestmentStatus, Liquidity, PaymentFrequency, ProductSource, RateMode, RiskLevel,
    TaxRegime, TransactionSource, TransactionType,
)
from backend.models.economy import EconomicCrisis, EconomyState, GameProfile, SimPrice, WorldEvent
from backend.models.fixed_income import FinancialEvent, FixedIncomeInvestment, FixedIncomeProduct, IndexRate
from backend.models.goods import (
    Good, GoodCost, GoodEvent, GoodValue, Loan, LoanInstallment, RealEstateDetails, ValuationRule, VehicleDetails,
)
from backend.models.games import Game
from backend.models.holding import Holding
from backend.models.life import Child, LifeLog, LifeProfile, Person, Relationship
from backend.models.performance import LessonProgress, PortfolioSnapshot
from backend.models.portfolio import Portfolio
from backend.models.progress import Achievement, Goal, MonthReport
from backend.models.transaction import Transaction
from backend.models.user import User

__all__ = [
    "Game",
    "Achievement", "Goal", "MonthReport",
    "EconomicCrisis", "EconomyState", "GameProfile", "SimPrice", "WorldEvent",
    "Child", "LifeLog", "LifeProfile", "Person", "Relationship",
    "Company", "CompanyCost", "CompanyCostKind", "CompanyEvent", "CompanyEventType", "CompanyLease", "CompanyLoan",
    "CompanyLoanInstallment", "CompanyMonth", "CompanySegment", "CompanySize", "CompanyStatus", "Employee", "EmployeeLevel",
    "EmployeeStatus", "InventoryItem", "LeaseKind",
    "AmortizationSystem", "Condition", "CostKind", "Good", "GoodCategory", "GoodCost", "GoodEvent", "GoodEventType",
    "GoodStatus", "GoodValue", "InstallmentStatus", "Loan", "LoanInstallment", "LoanStatus", "Occupancy", "REAL_ESTATE",
    "RealEstateDetails", "ValuationRule", "ValueSource", "VehicleDetails",
    "AccountKind", "BudgetCategory", "BudgetItem", "EntryOrigin", "FinanceAccount", "FlowKind", "Frequency",
    "LedgerEntry", "MonthStatus", "RecurringItem", "RecurringItemVersion", "SimMonth",
    "Asset", "AssetClass", "ChartLayout", "Dividend", "DividendEligibility", "DividendPayment",
    "DistributionKind", "EligibilityStatus", "EventKind", "EventStatus", "FinancialEvent", "FixedIncomeInvestment",
    "FixedIncomeProduct", "FixedIncomeType", "IndexName", "IndexRate", "Indexer", "InvestmentStatus", "Liquidity",
    "LessonProgress", "PaymentFrequency", "PortfolioSnapshot", "ProductSource", "RateMode", "RiskLevel", "TaxRegime", "Currency", "Holding", "Portfolio",
    "Transaction", "TransactionSource", "TransactionType", "User",
]
