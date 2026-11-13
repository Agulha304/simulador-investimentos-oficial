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


# ----------------------------------------------------------------- renda fixa

class FixedIncomeType(StrEnum):
    TESOURO_SELIC = "TESOURO_SELIC"
    TESOURO_PREFIXADO = "TESOURO_PREFIXADO"
    TESOURO_PREFIXADO_JUROS = "TESOURO_PREFIXADO_JUROS"
    TESOURO_IPCA = "TESOURO_IPCA"
    TESOURO_IPCA_JUROS = "TESOURO_IPCA_JUROS"
    TESOURO_IGPM_JUROS = "TESOURO_IGPM_JUROS"
    TESOURO_RENDA_MAIS = "TESOURO_RENDA_MAIS"
    TESOURO_EDUCA_MAIS = "TESOURO_EDUCA_MAIS"
    CDB = "CDB"
    LCI = "LCI"
    LCA = "LCA"
    CRI = "CRI"
    CRA = "CRA"
    DEBENTURE = "DEBENTURE"


class Indexer(StrEnum):
    PRE = "PRE"
    CDI = "CDI"
    SELIC = "SELIC"
    IPCA = "IPCA"
    IGPM = "IGPM"


class RateMode(StrEnum):
    FIXED = "FIXED"                          # taxa prefixada ao ano
    PERCENT_OF_INDEX = "PERCENT_OF_INDEX"    # ex.: 110% do CDI
    SPREAD = "SPREAD"                        # índice + taxa ao ano (ex.: IPCA + 7%)


class Liquidity(StrEnum):
    DAILY = "DAILY"                          # resgate diário (após a carência, se houver)
    AT_MATURITY = "AT_MATURITY"              # só no vencimento (ou mercado secundário, se permitido)
    SPECIFIC_DATES = "SPECIFIC_DATES"        # janelas de resgate em datas definidas


class PaymentFrequency(StrEnum):
    AT_MATURITY = "AT_MATURITY"
    MONTHLY = "MONTHLY"
    SEMIANNUAL = "SEMIANNUAL"
    ANNUAL = "ANNUAL"


class TaxRegime(StrEnum):
    REGRESSIVE = "REGRESSIVE"                # IR regressivo (+ IOF até 30 dias)
    EXEMPT = "EXEMPT"                        # isento para pessoa física (LCI, LCA, CRI, CRA, incentivadas)


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ProductSource(StrEnum):
    TESOURO_TRANSPARENTE = "TESOURO_TRANSPARENTE"
    SAMPLE = "SAMPLE"                        # oferta de exemplo (sem fonte pública estruturada)


class InvestmentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REDEEMED = "REDEEMED"                    # resgatado antecipadamente
    MATURED = "MATURED"                      # liquidado no vencimento


class EventKind(StrEnum):
    COUPON = "COUPON"                        # pagamento periódico de juros
    MATURITY = "MATURITY"                    # vencimento (principal + juros finais)


class EventStatus(StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class IndexName(StrEnum):
    CDI = "CDI"
    SELIC = "SELIC"
    IPCA = "IPCA"
    IGPM = "IGPM"
