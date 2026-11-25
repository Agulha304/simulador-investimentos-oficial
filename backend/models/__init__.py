"""Importa todos os models para que o Alembic e o metadata os enxerguem."""
from backend.models.asset import Asset
from backend.models.budget import (
    BudgetCategory, BudgetItem, FinanceAccount, LedgerEntry, RecurringItem, RecurringItemVersion, SimMonth,
)
from backend.models.career import CareerJob, Education, Gig, JobApplication
from backend.models.chart_layout import ChartLayout
from backend.models.company import (
    CompanyPartner, PartnerInvite,
    Company, CompanyCost, CompanyEvent, CompanyLease, CompanySupplier, CompanyLoan, CompanyLoanInstallment, CompanyMonth, Employee,
    InventoryItem, CandidateBlock, CompanyUnit, CompanyExpansion, CompanyRecruiter, CompanyRecruiterRun, CompanyAide, CompanyFranchise, CompanyListing,
)
from backend.models.distribution import Dividend, DividendEligibility, DividendPayment
from backend.models.enums import (
    AccountKind, AmortizationSystem, CompanyChannel, SiteMode, CompanyCostKind, CompanyEventType, CompanySegment, CompanySize, CompanyStatus,
    EmployeeLevel, EmployeeStatus, EmployeeRegime, WorkSchedule, EmployeeEducation, LeaseKind, AssetClass, Condition, CostKind, GoodCategory, GoodEventType, GoodStatus,
    InstallmentStatus, LoanStatus, Occupancy, REAL_ESTATE, ValueSource, Currency, EntryOrigin, FlowKind, Frequency, MonthStatus, DistributionKind, EligibilityStatus, EventKind, EventStatus, FixedIncomeType,
    IndexName, Indexer, InvestmentStatus, Liquidity, PaymentFrequency, ProductSource, RateMode, RiskLevel,
    TaxRegime, TransactionSource, TransactionType,
)
from backend.models.debt import InvestorProfile, PersonalLoan, PersonalLoanInstallment
from backend.models.economy import EconomicCrisis, EconomyState, GameProfile, SimPrice, WorldEvent
from backend.models.fixed_income import FinancialEvent, FixedIncomeInvestment, FixedIncomeProduct, IndexRate
from backend.models.goods import (
    Good, GoodCost, GoodEvent, GoodValue, Loan, LoanInstallment, RealEstateDetails, ShortStayMonth, ValuationRule, VehicleDetails,
)
from backend.models.games import AccountCategory, Game
from backend.models.holding import Holding
from backend.models.life import Child, LifeLog, LifeProfile, Person, Relationship
from backend.models.password_reset import PasswordResetRequest, PasswordResetToken
from backend.models.performance import LessonProgress, PortfolioSnapshot
from backend.models.portfolio import Portfolio
from backend.models.progress import Achievement, Goal, MonthReport
from backend.models.transaction import Transaction
from backend.models.user import User

__all__ = [
    "PasswordResetRequest", "PasswordResetToken",
    "CareerJob", "Education", "Gig", "JobApplication",    "InvestorProfile",    "PersonalLoan", "PersonalLoanInstallment",    "CompanyPartner", "PartnerInvite",    "ShortStayMonth",    "AccountCategory", "Game",
    "Achievement", "Goal", "MonthReport",
    "EconomicCrisis", "EconomyState", "GameProfile", "SimPrice", "WorldEvent",
    "Child", "LifeLog", "LifeProfile", "Person", "Relationship",
    "Company", "CompanyChannel", "SiteMode", "CompanyCost", "CompanyCostKind", "CompanyEvent", "CompanyEventType", "CompanyLease", "CompanySupplier", "CompanyLoan",
    "CompanyLoanInstallment", "CompanyMonth", "CompanySegment", "CompanySize", "CompanyStatus", "Employee", "EmployeeLevel",
    "EmployeeStatus", "EmployeeRegime", "WorkSchedule", "EmployeeEducation", "CandidateBlock", "CompanyUnit", "CompanyExpansion", "CompanyRecruiter", "CompanyRecruiterRun", "CompanyAide", "CompanyFranchise", "CompanyListing", "InventoryItem", "LeaseKind",
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
