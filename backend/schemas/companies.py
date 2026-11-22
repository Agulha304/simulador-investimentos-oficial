"""Schemas de empresas. Decimal sai como string no JSON."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from backend.models import (
    CompanyChannel, CompanyCostKind, CompanyEventType, CompanySegment, CompanySize, CompanyStatus, EmployeeEducation, EmployeeLevel, EmployeeRegime, EmployeeStatus, WorkSchedule,
    FlowKind, InstallmentStatus, LeaseKind, LoanStatus, SiteMode,
)

Pos = Field(gt=0, max_digits=20, decimal_places=2)


# ------------------------------------------------------------------ entrada

class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    segment: CompanySegment
    channel: CompanyChannel | None = None              # padrão: física (ou online se o segmento só permitir online)
    site_mode: SiteMode | None = None                  # só canal físico: BUY (compra o terreno) ou RENT (padrão)
    location: str | None = None                        # chave do catálogo do segmento (padrão: bairro/primeira)
    size: CompanySize = CompanySize.SMALL
    extra_capital: Decimal = Field(Decimal("0"), ge=0, max_digits=20, decimal_places=2)   # além do mínimo para abrir
    owner_share_pct: Decimal = Field(Decimal("100"), gt=0, le=100, max_digits=5, decimal_places=2)
    partner_invite_ids: list[int] = []


class PartnerInviteIn(BaseModel):
    person_id: int
    share_pct: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)
    capital: Decimal = Pos


class QuoteIn(BaseModel):
    segment: CompanySegment
    channel: CompanyChannel | None = None
    site_mode: SiteMode | None = None
    location: str | None = None
    size: CompanySize = CompanySize.SMALL
    extra_capital: Decimal = Field(Decimal("0"), ge=0, max_digits=20, decimal_places=2)
    owner_share_pct: Decimal = Field(Decimal("100"), gt=0, le=100, max_digits=5, decimal_places=2)


class MoneyIn(BaseModel):
    amount: Decimal = Pos
    idempotency_key: str = Field(min_length=8, max_length=100)


class SettingsIn(BaseModel):
    price: Decimal | None = Field(None, gt=0, max_digits=20, decimal_places=2)
    owner_salary: Decimal | None = Field(None, ge=0, max_digits=20, decimal_places=2)
    auto_restock: bool | None = None


class CandidatesIn(BaseModel):
    role: str
    regime: EmployeeRegime = EmployeeRegime.CLT


class HireIn(BaseModel):
    """Proposta a um candidato. Só o id do candidato identifica quem é: pretensão, nível e escolaridade são recalculados no servidor."""
    candidate_id: str = Field(min_length=3, max_length=80)
    salary: Decimal = Pos
    hours_week: int = Field(ge=20, le=70)
    schedule: WorkSchedule
    regime: EmployeeRegime
    confirm_risk: bool = False
    idempotency_key: str = Field(min_length=8, max_length=100)


class RecruiterHireIn(BaseModel):
    tier: str = Field(min_length=1, max_length=8)                 # BASIC | PRO | ELITE (validado no serviço: 400)
    idempotency_key: str = Field(min_length=8, max_length=100)


def _empty_to_none(v):
    """Campo opcional de fornecedor: "" / só espaços = vazio = sem restrição."""
    return None if isinstance(v, str) and not v.strip() else v


class SupplierLimitsBriefIn(BaseModel):
    """Critérios de UMA categoria no briefing (prevalecem sobre o geral)."""
    max_spend: Decimal | None = None
    min_reliability: float | None = None
    max_lead_days: int | None = None
    volume_cap: Decimal | None = None

    _blank = field_validator("max_spend", "min_reliability", "max_lead_days", "volume_cap", mode="before")(_empty_to_none)


class RecruiterSettingsIn(BaseModel):
    """Briefing do contratador (substitui o anterior). Os intervalos são validados no serviço (400 com mensagem clara)."""
    max_salary: Decimal | None = None
    schedule: str = "5x2"
    hours_week: int | None = None
    regime_policy: str = "BOTH"
    max_monthly_payroll: Decimal | None = None
    supplier_max_total_spend: Decimal | None = None
    supplier_min_reliability: float | None = None
    supplier_max_lead_days: int | None = None
    supplier_volume_cap: Decimal | None = None
    supplier_overrides: dict[str, SupplierLimitsBriefIn | None] = {}

    _blank = field_validator("max_salary", "max_monthly_payroll", "supplier_max_total_spend", "supplier_min_reliability",
                             "supplier_max_lead_days", "supplier_volume_cap", mode="before")(_empty_to_none)


class RecruiterRoleIn(BaseModel):
    role: str = Field(min_length=1, max_length=40)
    count: int = Field(ge=1, le=60)


class RecruiterTeamIn(BaseModel):
    roles: list[RecruiterRoleIn] = Field(min_length=1, max_length=40)
    idempotency_key: str = Field(min_length=8, max_length=100)


class RecruiterKeyIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=100)


class RecruiterSuppliersIn(BaseModel):
    categories: list[str] | None = None
    idempotency_key: str = Field(min_length=8, max_length=100)


class SupplierLimitsIn(BaseModel):
    """Limites do contrato: TODOS opcionais (ausente/null/"" = sem limite)."""
    max_monthly_spend: Decimal | None = None
    min_reliability: float | None = None
    max_lead_days: int | None = None
    volume_cap: Decimal | None = None

    _blank = field_validator("max_monthly_spend", "min_reliability", "max_lead_days", "volume_cap", mode="before")(_empty_to_none)


class StockIn(BaseModel):
    item_id: int
    quantity: Decimal = Field(gt=0, max_digits=16, decimal_places=3)
    idempotency_key: str = Field(min_length=8, max_length=100)


class SupplierSearchIn(BaseModel):
    category: str = Field(min_length=1, max_length=32)


class SupplierNegotiateIn(BaseModel):
    """Proposta de preço. Só o id do fornecedor identifica quem é: lista, piso, volume máximo e confiabilidade são recalculados no servidor."""
    supplier_id: str = Field(min_length=3, max_length=80)
    unit_price: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    monthly_volume: Decimal | None = Field(None, gt=0, max_digits=16, decimal_places=3)    # padrão: tudo o que o fornecedor aguenta
    idempotency_key: str = Field(min_length=8, max_length=100)


class RelocateIn(BaseModel):
    location: str = Field(min_length=1, max_length=32)
    site_mode: SiteMode | None = None
    size: CompanySize | None = None
    idempotency_key: str = Field(min_length=8, max_length=100)


class RelocateQuoteIn(BaseModel):
    location: str = Field(min_length=1, max_length=32)
    site_mode: SiteMode | None = None
    size: CompanySize | None = None


class ExpansionOptionsIn(BaseModel):
    kind: str = Field(pattern="^(CAPACITY|NEW_UNIT|QUALITY|MARKETING|LARGER_PREMISES)$")
    tier: str = Field(pattern="^(BARATO|MEDIO|CARO)$")


class ExpansionExecuteIn(ExpansionOptionsIn):
    option_key: str = Field(min_length=1, max_length=40)
    channel: CompanyChannel | None = None             # só NEW_UNIT
    site_mode: SiteMode | None = None                 # só NEW_UNIT
    location: str | None = Field(None, max_length=32)  # só NEW_UNIT
    idempotency_key: str = Field(min_length=8, max_length=100)


class LeaseIn(BaseModel):
    kind: LeaseKind
    good_id: int | None = None
    monthly_rent: Decimal | None = Field(None, ge=0, max_digits=20, decimal_places=2)
    name: str | None = Field(None, max_length=120)


class LoanIn(BaseModel):
    amount: Decimal = Pos
    term_months: int = Field(ge=1, le=60)


class CompanyGoodIn(BaseModel):
    listing_key: str
    idempotency_key: str = Field(min_length=8, max_length=100)


# ------------------------------------------------------------------ saída

class RoleOut(BaseModel):
    key: str
    label: str
    salary: Decimal
    units: float
    generic: bool = False              # cargo geral (Contador, Advogado, Auxiliar de limpeza): não produz unidades
    hours: int = 0                     # jornada sugerida (cargos gerais por porte: meio período no porte pequeno); 0 = a do candidato
    mandatory: bool = False            # obrigatório para esta empresa (limpeza só no canal físico)


class LocationOut(BaseModel):
    key: str
    label: str
    demand: float
    rent_factor: Decimal
    land_price: Decimal                # terreno/ponto de porte pequeno


class SegmentTaxInfoOut(BaseModel):
    """Regime/anexo provável do segmento (impostos reais; ver backend/services/company_taxes.py)."""
    regime: str                        # SIMPLES (regime provável de uma empresa pequena)
    annex: str                         # I, II, III, IV, V ou "III/V" (Fator R)
    regime_label: str
    effective_min_pct: Decimal         # alíquota efetiva do DAS com RBT12 de R$ 100 mil
    effective_max_pct: Decimal         # alíquota efetiva do DAS no limite do Simples (R$ 4,8 mi)
    mei_allowed: bool
    mei_das: Decimal | None = None
    lp_taxes: list[str] = []           # tributos no Lucro Presumido (acima de R$ 4,8 mi/ano)
    simplifications: list[str] = []


class SupplyCategoryOut(BaseModel):
    key: str
    label: str
    unit: str
    weight: Decimal                    # fatia do custo do produto/serviço (soma 1,0)
    per_sale: Decimal                  # consumo por unidade vendida
    reference_price: Decimal           # preço de referência por unidade de compra


class SegmentOut(BaseModel):
    key: CompanySegment
    label: str
    description: str
    unit_label: str
    price: Decimal
    tax: SegmentTaxInfoOut
    roles: list[RoleOut]
    stock: list[str]                   # vazio nos segmentos de serviço
    minimum_capital: Decimal           # para porte pequeno, canal padrão e ponto alugado
    channels: list[CompanyChannel]
    locations: list[LocationOut]
    metrics_kind: str                  # PRODUCTION | RETAIL | SERVICE
    default_location: str
    supply_categories: list[SupplyCategoryOut] = []    # vazio: o segmento não precisa de fornecedor


class CatalogOut(BaseModel):
    segments: list[SegmentOut]
    sizes: list[dict]


class QuoteOut(BaseModel):
    channel: CompanyChannel
    site_mode: SiteMode | None
    location: str
    owner_share_pct: Decimal
    minimum_capital: Decimal           # mínimo para abrir (empresa inteira)
    owner_cost: Decimal                # parte do dono do mínimo (participação% × mínimo)
    extra_capital: Decimal
    total_owner_cost: Decimal          # owner_cost + extra_capital: o que sai da conta pessoal
    setup_cost: Decimal
    initial_stock: Decimal             # fase 4: RESERVA em caixa para a 1ª compra de fornecedores (a empresa nasce sem estoque)
    first_purchase_reserve: Decimal = Decimal("0")   # o mesmo valor, com o nome certo
    supply_categories: list[SupplyCategoryOut] = []
    land_cost: Decimal
    monthly_fixed: Decimal             # custos fixos + aluguel, por mês
    monthly_rent: Decimal
    tax: SegmentTaxInfoOut | None = None   # regime/anexo provável (informativo)
    monthly_payroll: Decimal           # 1 mês de folha dos cargos obrigatórios (CLT, salário-base)
    mandatory_cost: Decimal            # folha de 1 mês + custo de contratação dos obrigatórios (já dentro do capital mínimo)
    mandatory_roles: list[str]         # nomes dos cargos obrigatórios
    expected_units: float              # demanda do mercado MADURO (relevância 100); no início a empresa vende uma fração
    first_month_units: float = 0       # demanda esperada no 1º mês (relevância 0, antes do sorteio de mês sem vendas)
    operating_reserve: Decimal = Decimal("0")   # parte do capital mínimo que é reserva de operação (meses de custos fixos + folha)
    reserve_months: int = 0
    max_staff: int = 0                 # teto de funcionários do porte


class CompanyOut(BaseModel):
    id: int
    name: str
    segment: CompanySegment
    segment_label: str
    unit_label: str
    metrics_kind: str
    channel: CompanyChannel
    site_mode: SiteMode | None
    site_value: Decimal
    location: str
    location_label: str
    size: CompanySize
    units: int
    capacity_level: int
    price: Decimal
    reputation: int
    relevance: float = 0               # 0-100: sobe devagar; multiplica a demanda (ver `MarketOut`)
    owner_share_pct: Decimal
    owner_salary: Decimal
    auto_restock: bool
    status: CompanyStatus
    founded_on: date
    marketing_until: date | None
    quality: float = 50                 # 0-100: sobe com aportes de qualidade (mais relevância e tolerância a preço; insumos mais caros)
    capacity_boost: float = 0           # níveis efetivos de capacidade ampliada (1 = +25%)
    storage_boost: float = 0
    marketing_boost: float = 0.12
    suspended_until: date | None = None   # despejo: sem operar até este mês ou até mudar de endereço
    cash: Decimal
    debts: Decimal
    equity: Decimal
    last_revenue: Decimal | None
    last_net_result: Decimal | None
    supplier_budget: Decimal = Decimal("0")     # gasto PREVISTO do mês com fornecedores (demanda esperada x consumo x preço contratado)
    supply_ready: bool = True                   # todas as categorias têm contrato ativo (true também sem categorias)


class EmployeeOut(BaseModel):
    id: int
    name: str
    role: str
    role_label: str
    level: EmployeeLevel
    regime: EmployeeRegime
    schedule: WorkSchedule
    education: EmployeeEducation
    education_label: str
    experience_years: int
    salary: Decimal                    # salário negociado
    total_cost: Decimal                # custo mensal real: CLT 2x, PJ 1x
    severance_estimate: Decimal        # rescisão se demitir hoje
    lawsuit_risk_pct: float            # chance de processo trabalhista ao demitir hoje (%)
    lawsuit_history: int = 0           # processos trabalhistas anteriores (0..3)
    hours_week: int
    productivity: Decimal
    status: EmployeeStatus
    hired_on: date
    terminated_on: date | None


class InventoryOut(BaseModel):
    id: int
    name: str
    unit: str
    quantity: Decimal
    unit_cost: Decimal
    value: Decimal
    supplier: str
    min_quantity: Decimal
    monthly_consumption_est: Decimal
    low: bool
    max_quantity: Decimal = Decimal("0")      # teto de estoque do porte (espaço de armazenagem)
    category: str | None = None               # categoria de fornecimento que abastece o item
    contracted: bool = True                   # há contrato ativo da categoria (sem ele o item não é reposto)


class CostOut(BaseModel):
    id: int
    kind: CompanyCostKind
    name: str
    amount: Decimal
    active: bool


class LeaseOut(BaseModel):
    kind: LeaseKind
    good_id: int | None
    name: str
    monthly_rent: Decimal
    start_month: date


class InstallmentOut(BaseModel):
    number: int
    due_month: date
    payment: Decimal
    interest: Decimal
    amortization: Decimal
    balance_after: Decimal
    status: InstallmentStatus


class LoanOut(BaseModel):
    id: int
    principal: Decimal
    annual_rate_pct: Decimal
    term_months: int
    start_month: date
    balance: Decimal
    status: LoanStatus
    installments: list[InstallmentOut]


class CompanyGoodOut(BaseModel):
    id: int
    name: str
    category: str
    current_value: Decimal
    status: str


class MonthOut(BaseModel):
    ref_month: date
    demand_units: Decimal
    capacity_units: Decimal
    units_sold: Decimal
    stockout: bool
    revenue: Decimal
    variable_costs: Decimal
    fixed_costs: Decimal
    payroll: Decimal
    taxes: Decimal
    tax_regime: str | None = None      # MEI | SIMPLES | LUCRO_PRESUMIDO (null em meses antigos)
    tax_breakdown: list[dict] | None = None   # [{name, base, rate_pct, amount}]
    interest: Decimal
    operating_result: Decimal
    net_result: Decimal
    cash_end: Decimal
    debts_end: Decimal
    equity_end: Decimal
    reputation_end: int
    relevance_end: float = 0
    zero_sales: bool = False           # mês sorteado sem nenhuma venda (relevância baixa ou preço fora do mercado)
    irregular: bool = False            # fechou sem cargos obrigatórios: vendas zeradas
    fines: Decimal = Decimal("0")      # multas do mês (dentro dos custos fixos)
    units_detail: list[dict] | None = None   # fase 5: resultado do mês por unidade (matriz + filiais)


class EventOut(BaseModel):
    ref_month: date
    type: CompanyEventType
    description: str
    amount: Decimal | None
    created_at: datetime


class LedgerLineOut(BaseModel):
    id: int
    kind: FlowKind
    amount: Decimal
    description: str
    line: str | None
    capital: bool
    ref_month: date


class RequiredRoleOut(BaseModel):
    role: str
    label: str
    present: bool


class ComplianceOut(BaseModel):
    regular: bool
    required: list[RequiredRoleOut]
    missing: list[str]                 # chaves dos cargos obrigatórios que faltam
    missing_labels: list[str]
    estimated_fine: Decimal            # multa que seria aplicada se o mês fechasse agora
    grace_months: int = 0              # período de adaptação (empresas legadas): meses restantes sem bloqueio/multa


class SupplyChecklistOut(BaseModel):
    category: str
    label: str
    present: bool
    supplier: str | None = None


class SupplierContractOut(BaseModel):
    id: int
    category: str
    category_label: str
    unit: str
    name: str
    unit_price: Decimal
    reference_price: Decimal
    price_vs_reference_pct: float
    min_monthly_order: Decimal
    max_units_month: Decimal
    reliability: float
    failure_probability_pct: float
    lead_days: int
    status: str
    started_month: date
    ended_month: date | None
    term_months: int
    is_default: bool
    volume_used: Decimal               # comprado neste mês
    early_end_fine: Decimal            # multa se encerrar hoje
    max_monthly_spend: Decimal | None = None   # limites do contrato (None = sem limite)
    volume_cap: Decimal | None = None
    min_reliability: float | None = None
    max_lead_days: int | None = None
    spend_used: Decimal = Decimal("0")         # gasto deste mês no contrato
    effective_volume: Decimal | None = None    # min(volume do contrato, limite de volume)


class SupplierBudgetRowOut(BaseModel):
    category: str
    label: str
    unit: str
    weight: Decimal
    supplier_id: int | None
    supplier: str | None
    unit_price: Decimal                # contratado (ou de referência, se `estimated`)
    estimated: bool
    planned_volume: Decimal
    planned_spend: Decimal
    last_actual: Decimal               # gasto realizado no último mês fechado
    max_units_month: Decimal | None
    max_monthly_spend: Decimal | None = None   # limite de gasto do contrato (previsto x limite)
    volume_cap: Decimal | None = None
    over_limit: bool = False


class SupplierBudgetOut(BaseModel):
    rows: list[SupplierBudgetRowOut]
    total_planned: Decimal             # total de insumos previsto (só categorias contratadas)
    total_last_actual: Decimal
    last_month: date | None = None
    total_limit: Decimal | None = None   # gasto máximo total com fornecedores do briefing do contratador (se ativo)
    over_total: bool = False


class SupplyOut(BaseModel):
    required: bool                     # o segmento usa fornecedores
    ready: bool                        # todas as categorias contratadas
    checklist: list[SupplyChecklistOut]
    contracts: list[SupplierContractOut]       # ativos
    ended: list[SupplierContractOut] = []
    effective_capacity: float | None = None    # capacidade efetiva (unidades/mês) limitada pelo menor volume contratado
    budget: SupplierBudgetOut
    warning: str | None = None


class SupplierOfferOut(BaseModel):
    id: str
    category: str
    category_label: str
    unit: str
    name: str
    unit_price: Decimal
    reference_price: Decimal
    price_vs_reference_pct: float
    min_monthly_order: Decimal
    max_units_month: Decimal
    reliability: float
    lead_days: int


class SupplierSearchOut(BaseModel):
    category: str
    month: date
    offers: list[SupplierOfferOut]


class CandidateOut(BaseModel):
    id: str
    name: str
    role: str
    role_label: str
    regime: EmployeeRegime
    education: EmployeeEducation
    education_label: str
    experience_years: int
    level: EmployeeLevel
    level_label: str
    productivity: Decimal
    asking_salary: Decimal             # pretensão salarial
    hours_week: int                    # jornada pretendida
    schedule: WorkSchedule             # escala preferida
    monthly_cost_at_asking: Decimal    # custo real mensal se pagar a pretensão (CLT 2x / PJ 1x)
    lawsuit_history: int = 0           # processos trabalhistas anteriores (0..3)


class CandidatesOut(BaseModel):
    role: str
    regime: EmployeeRegime
    month: date
    candidates: list[CandidateOut]


class UnitOut(BaseModel):
    id: int | None                      # None = matriz (a própria empresa)
    kind: str                           # HQ | BRANCH
    name: str
    location: str
    location_label: str
    channel: CompanyChannel
    site_mode: SiteMode | None
    site_value: Decimal
    monthly_rent: Decimal
    relevance: float
    viability: float | None = None      # 0,3-1,4 (só filiais): >1 vende mais que o esperado da matriz
    status: str
    opened_month: date | None = None
    closed_month: date | None = None
    closed_reason: str | None = None
    cumulative_result: Decimal | None = None
    investment: Decimal | None = None


class ExpansionOptionOut(BaseModel):
    key: str
    title: str
    description: str
    cost: Decimal
    side_effects: list[str]
    risk_hint: str


class ExpansionSiteOut(BaseModel):
    channel: CompanyChannel
    location: str
    label: str
    monthly_rent: Decimal
    land_cost: Decimal


class ExpansionOptionsOut(BaseModel):
    kind: str
    tier: str
    tier_label: str
    tier_cost: Decimal
    ref_month: date
    options: list[ExpansionOptionOut]
    sites: list[ExpansionSiteOut] = []      # só NEW_UNIT


class MarketOut(BaseModel):
    """Mercado da empresa: relevância, demanda esperada (com relevância e preço), tetos por porte e aviso de crise."""
    relevance: float
    demand_factor: float               # fator de demanda da relevância (0,25 a 1)
    zero_month_prob: float             # chance de o próximo mês fechar sem nenhuma venda
    price_ratio: float                 # preço / preço de mercado
    price_factor: float
    mature_demand: float               # demanda com relevância 100 (potencial do ponto)
    production_cap: float              # teto de produção (PRODUCTION/RETAIL) ou de atendimento (SERVICE) por mês
    storage_cap_units: float           # teto de estoque em unidades vendáveis (0 nos segmentos de serviço)
    max_staff: int
    staff_count: int
    relocated_this_month: bool = False
    crisis: dict


class RelocateQuoteOut(BaseModel):
    location: str
    location_label: str
    site_mode: SiteMode | None
    size: CompanySize
    move: Decimal
    reinstall: Decimal
    fine: Decimal
    land_cost: Decimal
    land_resale: Decimal
    total: Decimal
    relevance_after: float
    sales_mult: float


class CompanyDetailOut(BaseModel):
    company: CompanyOut
    distributable_profit: Decimal
    runway_months: Decimal | None
    monthly_obligations: Decimal
    loan_limit: Decimal
    expected_demand: float
    expected_capacity: float
    market: MarketOut | None = None
    expansion_costs: dict[str, dict[str, Decimal]]     # por tipo e nível (BARATO/MEDIO/CARO)
    expansion_tiers: dict[str, list[dict]] = {}        # por tipo: nível, rótulo, custo e chances (para a escolha do nível)
    units_list: list["UnitOut"] = []                   # matriz + filiais (abertas e fechadas)
    roles: list[RoleOut]
    employees: list[EmployeeOut]
    inventory: list[InventoryOut]
    costs: list[CostOut]
    lease: LeaseOut | None
    loans: list[LoanOut]
    goods: list[CompanyGoodOut]
    months: list[MonthOut]
    events: list[EventOut]
    ledger: list[LedgerLineOut]
    partners: list[dict] = []
    compliance: ComplianceOut | None = None
    supply: SupplyOut | None = None
    recruiter: "RecruiterOut | None" = None            # contratador (headhunter) opcional
    recruiter_tiers: list["RecruiterTierOut"] = []     # níveis e custos para o porte da empresa


class RecruiterTierOut(BaseModel):
    tier: str
    label: str
    monthly_fee: Decimal
    commission_pct: float
    pool: int                          # pessoas avaliadas por vaga
    offers: int                        # ofertas avaliadas por categoria de fornecedor
    find_chance_pct: int
    discount_pct: float
    success_pct: int


class RecruiterOut(BaseModel):
    tier: str
    tier_label: str
    status: str                        # ACTIVE | ENDED
    hired_month: date
    ended_month: date | None = None
    monthly_fee: Decimal
    commission_pct: float
    settings: dict                     # briefing (ver RecruiterSettingsIn)
    pool: int
    offers: int
    find_chance_pct: int
    discount_pct: float
    success_pct: int


class ExpansionResultOut(BaseModel):
    success: bool                 # efeito completo ou parcial
    outcome: str                  # FULL | PARTIAL | FAIL
    message: str
    effects: list[str]
    cost: Decimal
    replayed: bool = False
    company: "CompanyDetailOut"


class HireOut(BaseModel):
    accepted: bool
    status: str                        # ACCEPTED | COUNTER | REFUSED
    message: str
    counter_offer: Decimal | None = None
    company: CompanyDetailOut | None = None


class RecruiterReportOut(BaseModel):
    kind: str                          # MANDATORY | TEAM | SUPPLIERS
    message: str
    replayed: bool = False
    hired: list[dict] = []             # nome, cargo, regime, salário, jornada, escala, custo mensal, comissão, histórico, motivo do regime
    skipped: list[dict] = []           # o que NÃO foi contratado e o motivo
    contracted: list[dict] = []        # fornecedores contratados
    total_monthly_cost: Decimal
    total_commission: Decimal
    total_expected_spend: Decimal
    company: CompanyDetailOut


class SupplierNegotiateOut(BaseModel):
    accepted: bool
    status: str                        # ACCEPTED | COUNTER | REFUSED
    message: str
    counter_offer: Decimal | None = None
    company: CompanyDetailOut | None = None


class OverviewOut(BaseModel):
    count: int
    equity_total: Decimal              # patrimônio empresarial (100%)
    equity_user_share: Decimal         # parte do usuário (entra no patrimônio total)
    cash_total: Decimal
    debts_total: Decimal
    revenue_last_month: Decimal
    expenses_last_month: Decimal
    net_last_month: Decimal
    companies: list[CompanyOut]


CompanyDetailOut.model_rebuild()
ExpansionResultOut.model_rebuild()
RecruiterReportOut.model_rebuild()
