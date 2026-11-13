"""Enums de domínio. Gravados como VARCHAR (native_enum=False) para que novas
classes de ativo / tipos de transação possam ser adicionados sem ALTER TYPE."""
from enum import StrEnum


class AssetClass(StrEnum):
    STOCK = "STOCK"          # ações BR e internacionais
    ETF = "ETF"
    FII = "FII"              # fundos imobiliários brasileiros
    REIT = "REIT"
    CRYPTO = "CRYPTO"
    BDR = "BDR"


class Currency(StrEnum):
    BRL = "BRL"
    USD = "USD"


class TransactionType(StrEnum):
    DEPOSIT = "DEPOSIT"                  # aporte de saldo virtual (inclui o inicial)
    WITHDRAWAL = "WITHDRAWAL"
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"                # proventos (ações, FIIs, REITs, ETFs)
    FIXED_INCOME_APPLY = "FIXED_INCOME_APPLY"
    FIXED_INCOME_REDEEM = "FIXED_INCOME_REDEEM"
    FIXED_INCOME_COUPON = "FIXED_INCOME_COUPON"
    FIXED_INCOME_MATURITY = "FIXED_INCOME_MATURITY"


class TransactionSource(StrEnum):
    """Quem originou a transação — útil para auditoria e para os workers."""
    USER = "USER"
    SYSTEM = "SYSTEM"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    DISTRIBUTION_WORKER = "DISTRIBUTION_WORKER"
    FIXED_INCOME_WORKER = "FIXED_INCOME_WORKER"


class DistributionKind(StrEnum):
    DIVIDEND = "DIVIDEND"        # dividendos (ações, ETFs, REITs)
    JCP = "JCP"                  # juros sobre capital próprio
    RENDIMENTO = "RENDIMENTO"    # rendimentos de FIIs


class EligibilityStatus(StrEnum):
    PENDING = "PENDING"          # direito reconhecido, aguardando pagamento
    PAID = "PAID"
    CANCELLED = "CANCELLED"      # valor líquido zero (ex.: arredondou para R$ 0,00)
