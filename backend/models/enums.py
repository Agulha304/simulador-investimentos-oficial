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
    BUDGET_INCOME = "BUDGET_INCOME"      # receita do orçamento (salário, renda extra...); conta como patrimônio
    BUDGET_EXPENSE = "BUDGET_EXPENSE"    # despesa do orçamento (moradia, alimentação...)


# ------------------------------------------------------- orçamento e ciclo mensal

class AccountKind(StrEnum):
    """Tipo de conta financeira. Só PERSONAL é usada na etapa 1; as demais já existem
    para que empresas e carteiras possam ter contas próprias sem misturar saldos."""
    PERSONAL = "PERSONAL"
    INVESTMENT = "INVESTMENT"
    BUSINESS = "BUSINESS"


class FlowKind(StrEnum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class Frequency(StrEnum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    SEMIANNUAL = "SEMIANNUAL"
    ANNUAL = "ANNUAL"


class EntryOrigin(StrEnum):
    """De onde veio a movimentação — hoje manual e recorrente; módulos futuros
    (imóveis, empresas, família...) entram como novos valores."""
    MANUAL = "MANUAL"
    RECURRING = "RECURRING"
    INVESTMENT = "INVESTMENT"
    SYSTEM = "SYSTEM"
    REVERSAL = "REVERSAL"
    ASSET = "ASSET"              # efeitos de bens (compra, venda, parcelas, aluguel, custos)
    COMPANY = "COMPANY"          # transferências entre a conta pessoal e as empresas (aporte, lucros, pró-labore, aluguel)
    FAMILY = "FAMILY"            # vida pessoal e família (filhos, moradia compartilhada, atividades, contribuição do parceiro)
    EVENT = "EVENT"              # consequências financeiras de eventos (pessoais, econômicos, empresariais)


class MonthStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


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


# ----------------------------------------------------------- bens e patrimônio (etapa 2)

class GoodCategory(StrEnum):
    RESIDENTIAL = "RESIDENTIAL"
    COMMERCIAL = "COMMERCIAL"
    LAND = "LAND"
    CAR = "CAR"
    MOTORCYCLE = "MOTORCYCLE"
    INSTRUMENT = "INSTRUMENT"
    EQUIPMENT = "EQUIPMENT"
    ANTIQUE = "ANTIQUE"
    COLLECTIBLE = "COLLECTIBLE"
    OTHER = "OTHER"


REAL_ESTATE = (GoodCategory.RESIDENTIAL, GoodCategory.COMMERCIAL, GoodCategory.LAND)


class GoodStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SOLD = "SOLD"
    LOST = "LOST"


class Condition(StrEnum):
    NEW = "NEW"
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"


class Occupancy(StrEnum):
    OWNER_OCCUPIED = "OWNER_OCCUPIED"      # o usuário mora
    VACANT = "VACANT"                      # sem uso e sem anúncio
    LISTED_FOR_RENT = "LISTED_FOR_RENT"    # anunciado, aguardando inquilino (vacância)
    RENTED = "RENTED"                      # alugado, gerando renda
    SHORT_STAY = "SHORT_STAY"              # hospedagem de temporada (o "Airbnb" do jogo): rende mais, exige gestão
    COMPANY_USE = "COMPANY_USE"            # cedido a uma empresa do usuário (contrato de locação interno)


class CostKind(StrEnum):
    IPTU = "IPTU"
    CONDO = "CONDO"
    MAINTENANCE = "MAINTENANCE"
    FUEL = "FUEL"
    INSURANCE = "INSURANCE"
    IPVA = "IPVA"
    LICENSING = "LICENSING"
    PARKING = "PARKING"
    OTHER = "OTHER"


class AmortizationSystem(StrEnum):
    PRICE = "PRICE"
    SAC = "SAC"


class LoanStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAID = "PAID"            # todas as parcelas pagas
    SETTLED = "SETTLED"      # quitado na venda do bem


class InstallmentStatus(StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class ValueSource(StrEnum):
    PURCHASE = "PURCHASE"
    MONTHLY = "MONTHLY"
    SALE = "SALE"
    WRITE_OFF = "WRITE_OFF"


class GoodEventType(StrEnum):
    PURCHASE = "PURCHASE"
    SALE = "SALE"
    OCCUPANCY = "OCCUPANCY"
    RENTED = "RENTED"
    VACATED = "VACATED"
    MAINTENANCE = "MAINTENANCE"
    COST_CHANGE = "COST_CHANGE"
    WRITE_OFF = "WRITE_OFF"


# ----------------------------------------------------------------- empresas (etapa 3)

class CompanySegment(StrEnum):
    RESTAURANT = "RESTAURANT"
    CAFE = "CAFE"
    CLOTHING = "CLOTHING"
    SUPERMARKET = "SUPERMARKET"
    WORKSHOP = "WORKSHOP"
    TECH = "TECH"
    AGENCY = "AGENCY"
    INDUSTRY = "INDUSTRY"
    CONSTRUCTION = "CONSTRUCTION"
    TRANSPORT = "TRANSPORT"
    REAL_ESTATE_AGENCY = "REAL_ESTATE_AGENCY"
    ECOMMERCE = "ECOMMERCE"


class CompanySize(StrEnum):
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"


class CompanyChannel(StrEnum):
    ONLINE = "ONLINE"
    PHYSICAL = "PHYSICAL"


class SiteMode(StrEnum):
    BUY = "BUY"
    RENT = "RENT"


class CompanyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class EmployeeLevel(StrEnum):
    JUNIOR = "JUNIOR"
    MID = "MID"
    SENIOR = "SENIOR"


class EmployeeStatus(StrEnum):
    ACTIVE = "ACTIVE"
    TERMINATED = "TERMINATED"


class EmployeeRegime(StrEnum):
    CLT = "CLT"                    # custa 2x o salário (encargos, benefícios e provisões)
    PJ = "PJ"                      # custa 1x o salário; risco alto de processo (reconhecimento de vínculo)


class WorkSchedule(StrEnum):
    ESC_6X1 = "6x1"
    ESC_5X2 = "5x2"
    ESC_12X36 = "12x36"
    ESC_4X3 = "4x3"


class EmployeeEducation(StrEnum):
    FUNDAMENTAL = "FUNDAMENTAL"
    MEDIO = "MEDIO"
    TECNICO = "TECNICO"
    SUPERIOR = "SUPERIOR"
    POS = "POS"


class CompanyCostKind(StrEnum):
    UTILITIES = "UTILITIES"
    TOOLS = "TOOLS"
    INSURANCE = "INSURANCE"
    MARKETING = "MARKETING"
    ACCOUNTING = "ACCOUNTING"
    OTHER = "OTHER"


class LeaseKind(StrEnum):
    EXTERNAL = "EXTERNAL"            # imóvel de terceiros
    OWN_GOOD = "OWN_GOOD"            # imóvel pessoal do usuário alugado à empresa (gera receita pessoal)
    COMPANY_GOOD = "COMPANY_GOOD"    # imóvel da própria empresa (sem aluguel)


class CompanyEventType(StrEnum):
    CREATED = "CREATED"
    CAPITAL = "CAPITAL"
    HIRE = "HIRE"
    FIRE = "FIRE"
    STOCK = "STOCK"
    EXPANSION = "EXPANSION"
    LEASE = "LEASE"
    LOAN = "LOAN"
    DISTRIBUTION = "DISTRIBUTION"
    EQUIPMENT = "EQUIPMENT"
    SETTINGS = "SETTINGS"
    MONTH = "MONTH"
    CLOSED = "CLOSED"
    COMPLIANCE = "COMPLIANCE"
