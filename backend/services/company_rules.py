"""Regras de empresas: segmentos, localizações, portes e fórmulas de demanda/capacidade.

Tudo é configuração em código (nenhum dado externo). Para acrescentar um setor, basta incluir um `Segment` em `SEGMENTS`
e o valor correspondente em `CompanySegment`. Os sorteios usam hash de (empresa, mês): o mesmo mês dá sempre o mesmo
resultado (testável e sem surpresa a cada recarga de tela).
"""
import math
from dataclasses import dataclass
from decimal import Decimal

from backend.core.money import quantize_money
from backend.models import CompanyCostKind, CompanySegment, CompanySize, EmployeeLevel
from backend.services.goods_rules import hash01

D = Decimal
ENCARGOS_PCT = D("0.35")            # encargos sobre salário (modelo simplificado: INSS patronal, FGTS, 13º, férias)
HIRING_COST_MONTHS = D("0.5")       # custo de recrutamento = meio salário
SEVERANCE_MONTHS = D("1.0")         # rescisão = um salário
OVERDRAFT_RATE_MONTHLY = D("0.04")  # juros do saldo negativo (cheque especial empresarial)
LOAN_ANNUAL_RATE = D("18.0")
LOAN_MAX_TERM = 60
MARKETING_BOOST = D("0.12")
MARKETING_MONTHS = 3
MAX_CAPACITY_LEVEL = 4
MAX_UNITS = 10


@dataclass(frozen=True)
class Role:
    key: str
    label: str
    salary: Decimal            # nível pleno
    units: float               # capacidade (unidades/mês) por pessoa com produtividade 1


@dataclass(frozen=True)
class Stock:
    name: str
    unit: str
    unit_cost: Decimal
    units_per_sale: Decimal
    supplier: str
    waste_pct: Decimal = D(0)


@dataclass(frozen=True)
class Segment:
    key: CompanySegment
    label: str
    unit_label: str
    price: Decimal
    base_demand: float
    elasticity: float
    volatility: float
    owner_capacity: float
    roles: tuple[Role, ...]
    initial_staff: tuple[str, ...]
    stock: tuple[Stock, ...]
    variable_pct: Decimal
    fixed: tuple[tuple[CompanyCostKind, str, Decimal], ...]
    rent: Decimal
    tax_pct: Decimal
    setup_cost: Decimal
    marketing_cost: Decimal
    description: str = ""
    fractional: bool = False                       # vendas em frações (obras)

    def role(self, key: str) -> Role:
        for r in self.roles:
            if r.key == key:
                return r
        raise KeyError(key)


@dataclass(frozen=True)
class Location:
    label: str
    demand: float
    rent: Decimal


@dataclass(frozen=True)
class SizeSpec:
    label: str
    demand: float
    capacity: float
    rent: Decimal
    fixed: Decimal
    setup: Decimal
    staff: int


LOCATIONS = {
    "centro": Location("Centro da capital", 1.25, D("1.6")),
    "bairro": Location("Bairro residencial", 1.0, D("1.0")),
    "shopping": Location("Shopping center", 1.4, D("2.2")),
    "interior": Location("Cidade do interior", 0.7, D("0.6")),
    "polo": Location("Polo industrial/logístico", 0.9, D("0.8")),
}
SIZES = {
    CompanySize.SMALL: SizeSpec("Pequena", 1.0, 1.0, D("1.0"), D("1.0"), D("1.0"), 1),
    CompanySize.MEDIUM: SizeSpec("Média", 1.7, 1.8, D("1.8"), D("1.6"), D("1.9"), 2),
    CompanySize.LARGE: SizeSpec("Grande", 2.8, 3.2, D("3.0"), D("2.6"), D("3.4"), 3),
}
SIZE_ORDER = [CompanySize.SMALL, CompanySize.MEDIUM, CompanySize.LARGE]
LEVELS = {  # multiplicador de salário e de produtividade
    EmployeeLevel.JUNIOR: (D("0.80"), D("0.80")),
    EmployeeLevel.MID: (D("1.00"), D("1.00")),
    EmployeeLevel.SENIOR: (D("1.50"), D("1.25")),
}

K = CompanyCostKind


def _seg(key, label, unit_label, price, demand, elast, vol, owner_cap, roles, staff, stock, var_pct, fixed, rent, tax, setup,
         mkt, desc, fractional=False) -> Segment:
    return Segment(CompanySegment(key), label, unit_label, D(price), demand, elast, vol, owner_cap, tuple(roles), tuple(staff),
                   tuple(stock), D(var_pct), tuple((k, n, D(a)) for k, n, a in fixed), D(rent), D(tax), D(setup), D(mkt), desc, fractional)


SEGMENTS: dict[CompanySegment, Segment] = {s.key: s for s in [
    _seg("RESTAURANT", "Restaurante", "refeição", 55, 650, 1.2, 0.15, 150,
         [Role("cook", "Cozinheiro", D(2800), 260), Role("waiter", "Garçom", D(2000), 220)], ["cook", "waiter", "waiter"],
         [Stock("Ingredientes", "porção", D(17), D(1), "Atacadista Alimentar", D(8))], 0,
         [(K.UTILITIES, "Energia, água e gás", 2200), (K.TOOLS, "Limpeza e utensílios", 500), (K.ACCOUNTING, "Contabilidade", 600)],
         7000, 6, 40000, 3000, "Compra ingredientes, atende por capacidade de cozinha e salão e sofre com desperdício."),
    _seg("CAFE", "Cafeteria", "atendimento", 18, 1500, 1.3, 0.12, 500,
         [Role("barista", "Barista", D(2100), 700), Role("attendant", "Atendente", D(1900), 600)], ["barista", "attendant"],
         [Stock("Insumos de café", "porção", D("5.2"), D(1), "Torrefação Local", D(5))], 0,
         [(K.UTILITIES, "Energia e água", 1500), (K.TOOLS, "Manutenção de máquinas", 300), (K.ACCOUNTING, "Contabilidade", 600)],
         5000, 6, 30000, 2500, "Alto volume e ticket baixo: depende do fluxo de pessoas e do preço."),
    _seg("CLOTHING", "Loja de roupas", "peça vendida", 140, 280, 1.4, 0.25, 120,
         [Role("seller", "Vendedor", D(1900), 160)], ["seller", "seller"],
         [Stock("Mercadorias", "peça", D(62), D(1), "Confecções Reunidas", D(2))], 0,
         [(K.UTILITIES, "Energia e internet", 1100), (K.TOOLS, "Vitrine e sistema", 400), (K.ACCOUNTING, "Contabilidade", 500)],
         6000, 6, 45000, 3500, "Estoque de mercadorias, margem de revenda e forte sazonalidade."),
    _seg("SUPERMARKET", "Supermercado", "compra", 85, 1500, 2.0, 0.08, 300,
         [Role("cashier", "Operador de caixa", D(1900), 500), Role("stocker", "Repositor", D(1850), 450)], ["cashier", "cashier", "stocker"],
         [Stock("Mercadorias", "item", D(60), D(1), "Distribuidora Central", D(3))], 0,
         [(K.UTILITIES, "Energia (refrigeração)", 4500), (K.TOOLS, "Sistema e equipamentos", 800), (K.ACCOUNTING, "Contabilidade", 900)],
         11000, 5, 120000, 6000, "Margem apertada e demanda sensível ao preço; perecíveis geram perdas."),
    _seg("WORKSHOP", "Oficina mecânica", "serviço", 380, 85, 1.0, 0.12, 40,
         [Role("mechanic", "Mecânico", D(2900), 55), Role("assistant", "Auxiliar", D(1900), 35)], ["mechanic", "assistant"],
         [Stock("Peças e fluidos", "kit", D(120), D(1), "Auto Peças Brasil", D(2))], 0,
         [(K.UTILITIES, "Energia e água", 1800), (K.TOOLS, "Ferramental", 900), (K.ACCOUNTING, "Contabilidade", 600)],
         5500, 6, 60000, 3000, "Serviço com peças: capacidade depende de mecânicos e do estoque de peças."),
    _seg("TECH", "Empresa de tecnologia", "contrato", 4800, 8, 1.1, 0.10, 3,
         [Role("dev", "Desenvolvedor", D(7500), 3.2), Role("designer", "Designer", D(5200), 2.0)], ["dev", "dev"],
         [], 10,
         [(K.UTILITIES, "Energia e internet", 900), (K.TOOLS, "Licenças e ferramentas", 2500), (K.ACCOUNTING, "Contabilidade", 800)],
         4500, 6, 25000, 4000, "Receita recorrente por contratos; custo concentrado em pessoas e infraestrutura."),
    _seg("AGENCY", "Agência de marketing", "conta atendida", 5200, 5, 1.2, 0.15, 2,
         [Role("designer", "Designer", D(4200), 2.0), Role("account", "Atendimento", D(4800), 2.5)], ["designer", "account"],
         [], 8,
         [(K.UTILITIES, "Energia e internet", 800), (K.TOOLS, "Ferramentas criativas", 1800), (K.ACCOUNTING, "Contabilidade", 700)],
         4000, 6, 20000, 3000, "Poucos clientes de alto valor; perder uma conta pesa."),
    _seg("INDUSTRY", "Indústria", "unidade produzida", 200, 700, 1.3, 0.12, 150,
         [Role("operator", "Operador de máquina", D(2600), 230), Role("technician", "Técnico", D(3800), 100)],
         ["operator", "operator", "operator", "technician"],
         [Stock("Matéria-prima", "kg", D(105), D(1), "Insumos Industriais", D(4))], 4,
         [(K.UTILITIES, "Energia industrial", 5500), (K.TOOLS, "Manutenção de máquinas", 2200), (K.ACCOUNTING, "Contabilidade", 1200)],
         14000, 7, 250000, 8000, "Matéria-prima, equipamentos e capacidade produtiva limitam a produção."),
    _seg("CONSTRUCTION", "Construtora", "obra", 38000, 3, 1.0, 0.30, 1,
         [Role("crew", "Equipe de obra", D(3000), 0.6), Role("engineer", "Engenheiro", D(8000), 0.5)], ["crew", "crew", "engineer"],
         [Stock("Materiais de obra", "lote", D(17000), D(1), "Depósito de Construção", D(5))], 5,
         [(K.UTILITIES, "Energia e canteiro", 1500), (K.TOOLS, "Equipamentos e EPI", 3000), (K.ACCOUNTING, "Contabilidade", 1500)],
         6000, 6, 80000, 5000, "Poucas obras grandes por mês: receita volátil e dependente de materiais.", fractional=True),
    _seg("TRANSPORT", "Empresa de transporte", "viagem", 1700, 40, 1.1, 0.10, 8,
         [Role("driver", "Motorista", D(3200), 14)], ["driver", "driver"],
         [Stock("Combustível", "litro", D("6.2"), D(130), "Posto Atacadista", D(0))], 6,
         [(K.UTILITIES, "Rastreamento e pátio", 600), (K.INSURANCE, "Seguro da frota", 2500), (K.TOOLS, "Manutenção de frota", 900)],
         4000, 6, 150000, 4000, "Combustível por viagem e capacidade da frota e dos motoristas."),
    _seg("REAL_ESTATE_AGENCY", "Imobiliária", "negócio fechado", 5500, 4.5, 1.3, 0.35, 1.5,
         [Role("broker", "Corretor", D(3000), 1.6)], ["broker", "broker"],
         [], 12,
         [(K.UTILITIES, "Energia e internet", 900), (K.TOOLS, "Portais e CRM", 1200), (K.ACCOUNTING, "Contabilidade", 700)],
         5000, 6, 30000, 3500, "Receita por comissão, muito volátil conforme o mercado.", fractional=True),
    _seg("ECOMMERCE", "Comércio eletrônico", "pedido", 120, 420, 1.6, 0.20, 150,
         [Role("support", "Atendimento", D(2000), 180), Role("logistics", "Logística", D(1900), 200)], ["support", "logistics"],
         [Stock("Produtos", "un", D(54), D(1), "Atacado Digital", D("1.5"))], 12,
         [(K.UTILITIES, "Internet e energia", 600), (K.TOOLS, "Plataforma e ferramentas", 1800), (K.ACCOUNTING, "Contabilidade", 700)],
         3500, 6, 35000, 3000, "Margem apertada, concorrência por preço e dependência de logística."),
]}


# ------------------------------------------------------------------ fórmulas (puras)

def level_salary(role: Role, level: EmployeeLevel) -> Decimal:
    return quantize_money(role.salary * LEVELS[level][0])


def level_productivity(level: EmployeeLevel) -> Decimal:
    return LEVELS[level][1]


def payroll_cost(salary: Decimal) -> Decimal:
    return quantize_money(salary * (1 + ENCARGOS_PCT))


def default_rent(seg: Segment, location: str, size: CompanySize) -> Decimal:
    return quantize_money(seg.rent * LOCATIONS[location].rent * SIZES[size].rent)


def reputation_factor(reputation: int) -> float:
    return 0.6 + 0.8 * (reputation / 100)


PRICE_CEILING = {"REAL_ESTATE_AGENCY": 1.6, "CONSTRUCTION": 1.8, "SUPERMARKET": 1.8, "CAFE": 2.2, "RESTAURANT": 2.4}     # acima disto ninguém compra
DEFAULT_CEILING = 3.0


def price_ceiling(seg: Segment) -> float:
    return PRICE_CEILING.get(seg.key.value, DEFAULT_CEILING)


def price_factor(seg: Segment, price: Decimal) -> float:
    """Preço barato vende mais; acima do preço de mercado a demanda despenca e, passando do teto do setor, ninguém compra."""
    r = float(price) / float(seg.price)
    if r <= 1:
        return min(3.0, r ** -seg.elasticity)
    ceil = price_ceiling(seg)
    if r >= ceil:
        return 0.0
    return (r ** -(seg.elasticity * 1.6)) * (ceil - r) / (ceil - 1)


def season_factor(seg: Segment, company_id: int, ref) -> float:
    return 1 + (hash01("season", company_id, ref.isoformat()) - 0.5) * 2 * seg.volatility


def demand_units(seg: Segment, *, location: str, size: CompanySize, units: int, reputation: int, price: Decimal,
                 company_id: int, ref, marketing: bool, season: bool = True) -> float:
    base = seg.base_demand * LOCATIONS[location].demand * SIZES[size].demand * units
    d = base * reputation_factor(reputation) * price_factor(seg, price)
    if season:
        d *= season_factor(seg, company_id, ref)
    if marketing:
        d *= 1 + float(MARKETING_BOOST)
    return d


def capacity_units(seg: Segment, *, size: CompanySize, units: int, capacity_level: int, staff: list[tuple[str, Decimal]],
                   equipment_factor: float = 1.0) -> float:
    people = sum(seg.role(r).units * float(prod) for r, prod in staff if any(x.key == r for x in seg.roles))
    return (seg.owner_capacity * SIZES[size].capacity + people) * units * (1 + 0.25 * capacity_level) * equipment_factor


def expected_units(seg: Segment, location: str, size: CompanySize, units: int = 1) -> float:
    return seg.base_demand * LOCATIONS[location].demand * SIZES[size].demand * units


def initial_staff(seg: Segment, size: CompanySize) -> list[str]:
    return list(seg.initial_staff) * SIZES[size].staff


def setup_cost(seg: Segment, size: CompanySize) -> Decimal:
    return quantize_money(seg.setup_cost * SIZES[size].setup)


def initial_stock_quantities(seg: Segment, location: str, size: CompanySize) -> list[tuple[Stock, Decimal]]:
    """Estoque inicial: cerca de 115% da demanda esperada do primeiro mês (evita ruptura logo na abertura)."""
    exp = expected_units(seg, location, size) * 1.15
    out = []
    for s in seg.stock:
        qty = D(str(exp)) * s.units_per_sale * (1 + s.waste_pct / 100)
        out.append((s, qty.quantize(D("0.001")) if seg.fractional else D(math.ceil(qty))))
    return out


def monthly_fixed(seg: Segment, location: str, size: CompanySize, units: int = 1) -> Decimal:
    scale = SIZES[size].fixed * units
    return quantize_money(sum((a for _, _, a in seg.fixed), D(0)) * scale + default_rent(seg, location, size) * units)


def required_capital(seg: Segment, location: str, size: CompanySize) -> Decimal:
    """Mínimo para abrir: estrutura + estoque inicial + um mês de custos fixos e folha."""
    stock = sum((q * s.unit_cost for s, q in initial_stock_quantities(seg, location, size)), D(0))
    payroll = sum((payroll_cost(level_salary(seg.role(r), EmployeeLevel.MID)) for r in initial_staff(seg, size)), D(0))
    return quantize_money(setup_cost(seg, size) + stock + monthly_fixed(seg, location, size) + payroll)


def expansion_cost(seg: Segment, kind: str, size: CompanySize, units: int) -> Decimal:
    if kind == "CAPACITY":
        return quantize_money(seg.setup_cost * D("0.15") * SIZES[size].setup)
    if kind == "NEW_UNIT":
        return quantize_money(seg.setup_cost * D("0.8") * SIZES[size].setup)
    if kind == "LARGER_PREMISES":
        nxt = SIZE_ORDER[min(SIZE_ORDER.index(size) + 1, 2)]
        return quantize_money(seg.setup_cost * D("0.6") * SIZES[nxt].setup)
    if kind == "MARKETING":
        return quantize_money(seg.marketing_cost * SIZES[size].fixed)
    raise KeyError(kind)

