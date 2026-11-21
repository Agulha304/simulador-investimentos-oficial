"""Regras de empresas: segmentos, canais, localizações, portes e fórmulas de demanda/capacidade.

Tudo é configuração em código (nenhum dado externo). Para acrescentar um setor, basta incluir um `Segment` em `SEGMENTS`
e o valor correspondente em `CompanySegment`. Os sorteios usam hash de (empresa, mês): o mesmo mês dá sempre o mesmo
resultado (testável e sem surpresa a cada recarga de tela).

Empresas v2 (fase 1): cada segmento define os canais permitidos (ONLINE/PHYSICAL), a sua própria lista de localizações
(com demanda, aluguel e preço do terreno) e o tipo de métricas (`MetricsKind`).
"""
import math
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from backend.core.money import quantize_money
from backend.models import CompanyChannel, CompanyCostKind, CompanySegment, CompanySize, EmployeeLevel, EmployeeRegime, SiteMode
from backend.services.goods_rules import hash01

D = Decimal
CLT_COST_MULT = D("2.0")            # CLT custa 2x o salário negociado (encargos, benefícios, 13º, férias e provisões)
PJ_COST_MULT = D("1.0")             # PJ custa 1x o salário (sem encargos), mas tem risco alto de processo ao demitir
HIRING_COST_MONTHS = D("0.5")       # custo de recrutamento = meio salário
SEVERANCE_MONTHS = D("1.0")         # rescisão = um salário
OVERDRAFT_RATE_MONTHLY = D("0.04")  # juros do saldo negativo (cheque especial empresarial)
LOAN_ANNUAL_RATE = D("18.0")
LOAN_MAX_TERM = 60
MARKETING_BOOST = D("0.12")
MARKETING_MONTHS = 3
MAX_CAPACITY_LEVEL = 4
MAX_UNITS = 10
ONLINE_LOCATION_KEY = "online"
ONLINE_COST_MULT = D("0.55")        # canal online em segmentos que também têm loja: estrutura e custos fixos menores
ONLINE_DEMAND = 1.0                 # alcance digital no lugar da demanda local


class MetricsKind(StrEnum):
    PRODUCTION = "PRODUCTION"       # produz e controla estoque/insumos
    RETAIL = "RETAIL"               # revende mercadorias (estoque)
    SERVICE = "SERVICE"             # presta serviços/contratos: sem estoque nem "produtos"


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
class Location:
    key: str
    label: str
    demand: float
    rent: Decimal              # multiplicador sobre o aluguel-base do segmento
    land_price: Decimal        # preço do terreno/ponto (porte pequeno); escala com o porte


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
    channels: tuple[CompanyChannel, ...] = (CompanyChannel.PHYSICAL,)
    locations: tuple[Location, ...] = ()
    metrics_kind: MetricsKind = MetricsKind.PRODUCTION

    def role(self, key: str) -> Role:
        for r in self.roles:
            if r.key == key:
                return r
        raise KeyError(key)

    @property
    def has_stock(self) -> bool:
        return self.metrics_kind != MetricsKind.SERVICE and bool(self.stock)

    @property
    def online_only(self) -> bool:
        return self.channels == (CompanyChannel.ONLINE,)

    def location(self, key: str) -> Location | None:
        return next((x for x in self.locations if x.key == key), None)

    @property
    def default_location(self) -> str:
        return "bairro" if self.location("bairro") else (self.locations[0].key if self.locations else ONLINE_LOCATION_KEY)


@dataclass(frozen=True)
class SizeSpec:
    label: str
    demand: float
    capacity: float
    rent: Decimal
    fixed: Decimal
    setup: Decimal
    staff: int


ONLINE_LOCATION = Location(ONLINE_LOCATION_KEY, "Operação online", ONLINE_DEMAND, D(0), D(0))

# Chaves do dicionário global antigo (antes de cada segmento ter a sua lista): empresas já existentes continuam com elas
# em `Company.location` e são resolvidas para o local equivalente do segmento (ver `resolve_location`).
LEGACY_LOCATIONS = {
    "centro": (1.25, D("1.6")),
    "bairro": (1.0, D("1.0")),
    "shopping": (1.4, D("2.2")),
    "interior": (0.7, D("0.6")),
    "polo": (0.9, D("0.8")),
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
ONLINE, PHYSICAL = CompanyChannel.ONLINE, CompanyChannel.PHYSICAL
PRODUCTION, RETAIL, SERVICE = MetricsKind.PRODUCTION, MetricsKind.RETAIL, MetricsKind.SERVICE

# cargos disponíveis em qualquer empresa (obrigatoriedade e contratação nova: fase 2); não produzem unidades
GENERIC_ROLES = (
    Role("accountant", "Contador", D(4500), 0),
    Role("lawyer", "Advogado", D(7000), 0),
    Role("cleaner", "Auxiliar de limpeza", D(1650), 0),
)


def _locs(seg_rent, rows) -> tuple[Location, ...]:
    """rows: (chave, nome, demanda, fator de aluguel, meses de aluguel que valem o terreno)."""
    return tuple(Location(k, label, dem, D(str(rf)), quantize_money(D(seg_rent) * D(str(rf)) * months))
                 for k, label, dem, rf, months in rows)


def _seg(key, label, unit_label, price, demand, elast, vol, owner_cap, roles, staff, stock, var_pct, fixed, rent, tax, setup,
         mkt, desc, *, kind, channels, locations, fractional=False) -> Segment:
    return Segment(CompanySegment(key), label, unit_label, D(price), demand, elast, vol, owner_cap,
                   tuple(roles) + GENERIC_ROLES, tuple(staff), tuple(stock), D(var_pct),
                   tuple((k, n, D(a)) for k, n, a in fixed), D(rent), D(tax), D(setup), D(mkt), desc, fractional,
                   tuple(channels), _locs(rent, locations), kind)


SEGMENTS: dict[CompanySegment, Segment] = {s.key: s for s in [
    _seg("RESTAURANT", "Restaurante", "refeição", 55, 650, 1.2, 0.15, 150,
         [Role("cook", "Cozinheiro", D(2800), 260), Role("waiter", "Garçom", D(2000), 220),
          Role("chef", "Chef de cozinha", D(5500), 380), Role("kitchen_aide", "Auxiliar de cozinha", D(1850), 180),
          Role("cashier", "Caixa", D(2000), 140)], ["cook", "waiter", "waiter"],
         [Stock("Ingredientes", "porção", D(17), D(1), "Atacadista Alimentar", D(8))], 0,
         [(K.UTILITIES, "Energia, água e gás", 2200), (K.TOOLS, "Limpeza e utensílios", 500), (K.ACCOUNTING, "Contabilidade", 600)],
         7000, 6, 40000, 3000, "Compra ingredientes, atende por capacidade de cozinha e salão e sofre com desperdício.",
         kind=PRODUCTION, channels=[PHYSICAL, ONLINE],
         locations=[("gastro", "Rua gastronômica", 1.35, 1.7, 90), ("centro", "Centro da capital", 1.25, 1.6, 95),
                    ("shopping", "Praça de alimentação de shopping", 1.4, 2.2, 80), ("bairro", "Bairro residencial", 1.0, 1.0, 100),
                    ("beira_mar", "Beira-mar", 1.3, 2.0, 120), ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("CAFE", "Cafeteria", "atendimento", 18, 1500, 1.3, 0.12, 500,
         [Role("barista", "Barista", D(2100), 700), Role("attendant", "Atendente", D(1900), 600),
          Role("pastry", "Confeiteiro", D(2600), 450), Role("manager", "Gerente de salão", D(3800), 300)], ["barista", "attendant"],
         [Stock("Insumos de café", "porção", D("5.2"), D(1), "Torrefação Local", D(5))], 0,
         [(K.UTILITIES, "Energia e água", 1500), (K.TOOLS, "Manutenção de máquinas", 300), (K.ACCOUNTING, "Contabilidade", 600)],
         5000, 6, 30000, 2500, "Alto volume e ticket baixo: depende do fluxo de pessoas e do preço.",
         kind=PRODUCTION, channels=[PHYSICAL, ONLINE],
         locations=[("centro", "Centro da capital", 1.25, 1.6, 95), ("shopping", "Shopping center", 1.4, 2.2, 80),
                    ("bairro", "Bairro residencial", 1.0, 1.0, 100), ("universitario", "Entorno de universidade", 1.2, 1.2, 90),
                    ("corporativo", "Região corporativa", 1.3, 1.8, 110), ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("CLOTHING", "Loja de roupas", "peça vendida", 140, 280, 1.4, 0.25, 120,
         [Role("seller", "Vendedor", D(1900), 160), Role("stylist", "Visual merchandiser", D(3200), 60),
          Role("cashier", "Operador de caixa", D(1800), 120), Role("stockist", "Estoquista", D(1800), 100)], ["seller", "seller"],
         [Stock("Mercadorias", "peça", D(62), D(1), "Confecções Reunidas", D(2))], 0,
         [(K.UTILITIES, "Energia e internet", 1100), (K.TOOLS, "Vitrine e sistema", 400), (K.ACCOUNTING, "Contabilidade", 500)],
         6000, 6, 45000, 3500, "Estoque de mercadorias, margem de revenda e forte sazonalidade.",
         kind=RETAIL, channels=[PHYSICAL, ONLINE],
         locations=[("centro", "Centro comercial", 1.25, 1.6, 95), ("shopping", "Shopping center", 1.4, 2.2, 80),
                    ("bairro", "Bairro residencial", 1.0, 1.0, 100), ("rua_popular", "Rua de comércio popular", 1.2, 1.1, 90),
                    ("outlet", "Polo de moda e outlet", 1.1, 0.9, 85), ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("SUPERMARKET", "Supermercado", "compra", 85, 1500, 2.0, 0.08, 300,
         [Role("cashier", "Operador de caixa", D(1900), 500), Role("stocker", "Repositor", D(1850), 450),
          Role("butcher", "Açougueiro", D(2600), 380), Role("bagger", "Empacotador", D(1650), 420)], ["cashier", "cashier", "stocker"],
         [Stock("Mercadorias", "item", D(60), D(1), "Distribuidora Central", D(3))], 0,
         [(K.UTILITIES, "Energia (refrigeração)", 4500), (K.TOOLS, "Sistema e equipamentos", 800), (K.ACCOUNTING, "Contabilidade", 900)],
         11000, 5, 120000, 6000, "Margem apertada e demanda sensível ao preço; perecíveis geram perdas.",
         kind=RETAIL, channels=[PHYSICAL, ONLINE],
         locations=[("bairro", "Bairro residencial", 1.0, 1.0, 100), ("centro", "Centro da capital", 1.25, 1.6, 95),
                    ("avenida", "Avenida de grande fluxo", 1.3, 1.8, 110), ("conjunto", "Entorno de conjunto habitacional", 1.15, 0.9, 85),
                    ("rodovia", "Atacarejo na rodovia", 1.1, 0.8, 75), ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("WORKSHOP", "Oficina mecânica", "serviço", 380, 85, 1.0, 0.12, 40,
         [Role("mechanic", "Mecânico", D(2900), 55), Role("assistant", "Auxiliar", D(1900), 35),
          Role("electrician", "Eletricista automotivo", D(3200), 45), Role("bodyworker", "Funileiro e pintor", D(3100), 40),
          Role("counter", "Atendente de balcão", D(1900), 60)], ["mechanic", "assistant"],
         [], 32,
         [(K.UTILITIES, "Energia e água", 1800), (K.TOOLS, "Ferramental", 900), (K.ACCOUNTING, "Contabilidade", 600)],
         5500, 6, 60000, 3000, "Serviço com peças: a capacidade depende dos mecânicos; peças e fluidos entram nos custos variáveis.",
         kind=SERVICE, channels=[PHYSICAL],
         locations=[("avenida", "Avenida de grande fluxo", 1.3, 1.5, 105), ("bairro", "Bairro residencial", 1.0, 1.0, 100),
                    ("rodovia", "Beira de rodovia", 1.1, 0.8, 75), ("polo_auto", "Polo automotivo", 1.2, 1.0, 90),
                    ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("TECH", "Empresa de tecnologia", "contrato", 4800, 8, 1.1, 0.10, 3,
         [Role("dev", "Desenvolvedor", D(7500), 3.2), Role("designer", "Designer", D(5200), 2.0),
          Role("qa", "Analista de testes", D(4800), 2.2), Role("pm", "Gerente de projetos", D(8500), 1.5),
          Role("devops", "Engenheiro DevOps", D(9500), 3.0)], ["dev", "dev"],
         [], 10,
         [(K.UTILITIES, "Energia e internet", 900), (K.TOOLS, "Licenças e ferramentas", 2500), (K.ACCOUNTING, "Contabilidade", 800)],
         4500, 6, 25000, 4000, "Receita recorrente por contratos; custo concentrado em pessoas e infraestrutura.",
         kind=SERVICE, channels=[PHYSICAL, ONLINE],
         locations=[("centro", "Centro empresarial", 1.25, 1.6, 95), ("parque_tech", "Parque tecnológico", 1.3, 1.8, 105),
                    ("coworking", "Espaço de coworking", 1.0, 0.7, 60), ("bairro", "Bairro residencial", 1.0, 1.0, 100),
                    ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("AGENCY", "Agência de marketing", "conta atendida", 5200, 5, 1.2, 0.15, 2,
         [Role("designer", "Designer", D(4200), 2.0), Role("account", "Atendimento", D(4800), 2.5),
          Role("copywriter", "Redator", D(3800), 2.2), Role("social", "Social media", D(3500), 2.5),
          Role("strategist", "Estrategista de mídia", D(6000), 2.0)], ["designer", "account"],
         [], 8,
         [(K.UTILITIES, "Energia e internet", 800), (K.TOOLS, "Ferramentas criativas", 1800), (K.ACCOUNTING, "Contabilidade", 700)],
         4000, 6, 20000, 3000, "Poucos clientes de alto valor; perder uma conta pesa.",
         kind=SERVICE, channels=[PHYSICAL, ONLINE],
         locations=[("centro", "Centro empresarial", 1.25, 1.6, 95), ("avenida_corp", "Avenida corporativa", 1.4, 2.2, 110),
                    ("coworking", "Espaço de coworking", 1.0, 0.7, 60), ("bairro", "Bairro residencial", 1.0, 1.0, 100),
                    ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("INDUSTRY", "Indústria", "unidade produzida", 200, 700, 1.3, 0.12, 150,
         [Role("operator", "Operador de máquina", D(2600), 230), Role("technician", "Técnico", D(3800), 100),
          Role("supervisor", "Supervisor de produção", D(5500), 120), Role("maintenance", "Mecânico de manutenção", D(3600), 80),
          Role("inspector", "Inspetor de qualidade", D(3200), 90)],
         ["operator", "operator", "operator", "technician"],
         [Stock("Matéria-prima", "kg", D(105), D(1), "Insumos Industriais", D(4))], 4,
         [(K.UTILITIES, "Energia industrial", 5500), (K.TOOLS, "Manutenção de máquinas", 2200), (K.ACCOUNTING, "Contabilidade", 1200)],
         14000, 7, 250000, 8000, "Matéria-prima, equipamentos e capacidade produtiva limitam a produção.",
         kind=PRODUCTION, channels=[PHYSICAL],
         locations=[("polo", "Polo industrial/logístico", 0.9, 0.8, 100), ("distrito", "Distrito industrial", 1.1, 1.0, 105),
                    ("rural", "Zona rural", 0.7, 0.5, 60), ("rodovia", "Margem de rodovia", 1.0, 0.9, 85),
                    ("porto", "Região portuária", 1.3, 1.5, 120)]),
    _seg("CONSTRUCTION", "Construtora", "obra", 38000, 3, 1.0, 0.30, 1,
         [Role("crew", "Equipe de obra", D(3000), 0.6), Role("engineer", "Engenheiro", D(8000), 0.5),
          Role("mason", "Pedreiro", D(2800), 0.5), Role("electrician", "Eletricista", D(3100), 0.35),
          Role("foreman", "Mestre de obras", D(5200), 0.45), Role("architect", "Arquiteto", D(7500), 0.3)],
         ["crew", "crew", "engineer"],
         [Stock("Materiais de obra", "lote", D(17000), D(1), "Depósito de Construção", D(5))], 5,
         [(K.UTILITIES, "Energia e canteiro", 1500), (K.TOOLS, "Equipamentos e EPI", 3000), (K.ACCOUNTING, "Contabilidade", 1500)],
         6000, 6, 80000, 5000, "Poucas obras grandes por mês: receita volátil e dependente de materiais.",
         kind=PRODUCTION, channels=[PHYSICAL], fractional=True,
         locations=[("centro", "Centro empresarial", 1.25, 1.6, 95), ("bairro", "Bairro residencial", 1.0, 1.0, 100),
                    ("polo", "Polo industrial/logístico", 0.9, 0.8, 100), ("litoral", "Litoral de alto padrão", 1.35, 1.8, 115),
                    ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("TRANSPORT", "Empresa de transporte", "viagem", 1700, 40, 1.1, 0.10, 8,
         [Role("driver", "Motorista", D(3200), 14), Role("dispatcher", "Operador logístico", D(2900), 20),
          Role("fleet_mechanic", "Mecânico de frota", D(3100), 6), Role("loader", "Ajudante de carga", D(2000), 10)],
         ["driver", "driver"],
         [], 53,
         [(K.UTILITIES, "Rastreamento e pátio", 600), (K.INSURANCE, "Seguro da frota", 2500), (K.TOOLS, "Manutenção de frota", 900)],
         4000, 6, 150000, 4000, "Capacidade da frota e dos motoristas; combustível e pedágios entram nos custos variáveis.",
         kind=SERVICE, channels=[PHYSICAL],
         locations=[("polo", "Polo industrial/logístico", 0.9, 0.8, 100), ("rodovia", "Margem de rodovia", 1.0, 0.7, 80),
                    ("porto", "Região portuária", 1.3, 1.4, 115), ("cd_urbano", "Centro de distribuição urbano", 1.15, 1.1, 100),
                    ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("REAL_ESTATE_AGENCY", "Imobiliária", "negócio fechado", 5500, 4.5, 1.3, 0.35, 1.5,
         [Role("broker", "Corretor", D(3000), 1.6), Role("appraiser", "Avaliador de imóveis", D(4500), 0.8),
          Role("photographer", "Fotógrafo de imóveis", D(2600), 0.7), Role("property_manager", "Administrador de locações", D(3800), 0.6),
          Role("sales_support", "Atendimento comercial", D(2300), 0.5)], ["broker", "broker"],
         [], 12,
         [(K.UTILITIES, "Energia e internet", 900), (K.TOOLS, "Portais e CRM", 1200), (K.ACCOUNTING, "Contabilidade", 700)],
         5000, 6, 30000, 3500, "Receita por comissão, muito volátil conforme o mercado.",
         kind=SERVICE, channels=[PHYSICAL, ONLINE], fractional=True,
         locations=[("centro", "Centro da capital", 1.25, 1.6, 95), ("bairro", "Bairro residencial", 1.0, 1.0, 100),
                    ("bairro_nobre", "Bairro nobre", 1.4, 2.0, 115), ("litoral", "Litoral", 1.3, 1.8, 115),
                    ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("ECOMMERCE", "Comércio eletrônico", "pedido", 120, 420, 1.6, 0.20, 150,
         [Role("support", "Atendimento", D(2000), 180), Role("logistics", "Logística", D(1900), 200),
          Role("digital_marketing", "Analista de marketing digital", D(4200), 90), Role("catalog", "Analista de catálogo", D(3800), 60),
          Role("packer", "Embalador", D(1750), 220)], ["support", "logistics"],
         [], 57,
         [(K.UTILITIES, "Internet e energia", 600), (K.TOOLS, "Plataforma e ferramentas", 1800), (K.ACCOUNTING, "Contabilidade", 700)],
         3500, 6, 35000, 3000, "Margem apertada, concorrência por preço e dependência de logística; produtos e frete nos custos variáveis.",
         kind=SERVICE, channels=[ONLINE], locations=[]),
]}


# ------------------------------------------------------------------ canal, localização e terreno

def resolve_location(seg: Segment, key: str) -> Location:
    """Local do segmento. "online" é o alcance digital; chaves antigas (empresas já existentes) viram o local equivalente
    do segmento (o de demanda mais próxima) ou, se o segmento não tem locais físicos, o valor antigo da chave."""
    if key == ONLINE_LOCATION_KEY:
        return ONLINE_LOCATION
    found = seg.location(key)
    if found:
        return found
    legacy = LEGACY_LOCATIONS.get(key)
    if legacy is None:
        raise KeyError(key)
    demand, rent = legacy
    if seg.locations:
        return min(seg.locations, key=lambda x: (abs(x.demand - demand), x.key))
    return Location(key, key.capitalize(), demand, rent, D(0))


def validate_site(seg: Segment, channel: CompanyChannel, location: str | None, site_mode: SiteMode | None) -> tuple[str, SiteMode | None]:
    """Valida a combinação canal/local/terreno de uma NOVA empresa; devolve (chave do local, modo do terreno)."""
    if channel not in seg.channels:
        allowed = " e ".join("online" if c == ONLINE else "física" for c in seg.channels)
        raise ValueError(f"{seg.label}: canal não permitido (apenas {allowed})")
    if channel == ONLINE:
        if site_mode == SiteMode.BUY:
            raise ValueError("empresa online não compra terreno nem ponto")
        return ONLINE_LOCATION_KEY, None
    loc = location or seg.default_location
    if seg.location(loc) is None:
        raise ValueError("localização inválida para este segmento")
    return loc, site_mode or SiteMode.RENT


def online_scale(seg: Segment, channel: CompanyChannel) -> Decimal:
    """Custos fixos e de estruturação do canal online (segmentos só-online já têm esses valores como base)."""
    return ONLINE_COST_MULT if channel == ONLINE and not seg.online_only else D(1)


def land_value(seg: Segment, channel: CompanyChannel, site_mode: SiteMode | None, location: str, size: CompanySize) -> Decimal:
    if channel != PHYSICAL or site_mode != SiteMode.BUY:
        return D("0.00")
    return quantize_money(resolve_location(seg, location).land_price * SIZES[size].rent)


# ------------------------------------------------------------------ fórmulas (puras)

def level_salary(role: Role, level: EmployeeLevel) -> Decimal:
    return quantize_money(role.salary * LEVELS[level][0])


def level_productivity(level: EmployeeLevel) -> Decimal:
    return LEVELS[level][1]


def payroll_cost(salary: Decimal, regime=EmployeeRegime.CLT) -> Decimal:
    """Custo REAL mensal do funcionário: CLT = 2x o salário negociado; PJ = 1x."""
    return quantize_money(salary * (PJ_COST_MULT if regime == EmployeeRegime.PJ else CLT_COST_MULT))


def mandatory_roles(channel: CompanyChannel) -> tuple[str, ...]:
    """Cargos obrigatórios: Contador e Advogado sempre; Auxiliar de limpeza só no canal físico."""
    return ("accountant", "lawyer", "cleaner") if channel == CompanyChannel.PHYSICAL else ("accountant", "lawyer")


def missing_mandatory(channel: CompanyChannel, active_roles) -> list[str]:
    have = set(active_roles)
    return [r for r in mandatory_roles(channel) if r not in have]


def compliance_fine(seg: "Segment", missing: list[str]) -> Decimal:
    """Multa por irregularidade: 1 salário-base (pleno) de cada cargo obrigatório faltante, somados."""
    return quantize_money(sum((seg.role(r).salary for r in missing), D(0)))


def mandatory_setup_cost(seg: "Segment", channel: CompanyChannel) -> Decimal:
    """Para o capital mínimo: 1 mês de folha (CLT, salário-base) + o custo de contratação dos cargos obrigatórios."""
    return quantize_money(sum((payroll_cost(seg.role(r).salary) + seg.role(r).salary * HIRING_COST_MONTHS
                               for r in mandatory_roles(channel)), D(0)))


def default_rent(seg: Segment, location: str, size: CompanySize) -> Decimal:
    """Aluguel mensal de referência do ponto (zero no canal online)."""
    return quantize_money(seg.rent * resolve_location(seg, location).rent * SIZES[size].rent)


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
    base = seg.base_demand * resolve_location(seg, location).demand * SIZES[size].demand * units
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
    return seg.base_demand * resolve_location(seg, location).demand * SIZES[size].demand * units


def initial_staff(seg: Segment, size: CompanySize) -> list[str]:
    """Equipe SUGERIDA (a empresa não nasce com ela desde a fase 2): cargos produtivos para o jogador contratar."""
    return list(seg.initial_staff) * SIZES[size].staff


def setup_cost(seg: Segment, size: CompanySize, channel: CompanyChannel = PHYSICAL) -> Decimal:
    return quantize_money(seg.setup_cost * SIZES[size].setup * online_scale(seg, channel))


def initial_stock_quantities(seg: Segment, location: str, size: CompanySize) -> list[tuple[Stock, Decimal]]:
    """Estoque inicial: cerca de 115% da demanda esperada do primeiro mês (evita ruptura logo na abertura).
    Segmentos de serviço não têm estoque."""
    if not seg.has_stock:
        return []
    exp = expected_units(seg, location, size) * 1.15
    out = []
    for s in seg.stock:
        qty = D(str(exp)) * s.units_per_sale * (1 + s.waste_pct / 100)
        out.append((s, qty.quantize(D("0.001")) if seg.fractional else D(math.ceil(qty))))
    return out


def monthly_rent(seg: Segment, location: str, size: CompanySize, units: int = 1, *, channel: CompanyChannel = PHYSICAL,
                 site_mode: SiteMode | None = SiteMode.RENT) -> Decimal:
    """Aluguel mensal do ponto: zero no canal online e com terreno comprado."""
    if channel != PHYSICAL or site_mode == SiteMode.BUY:
        return D("0.00")
    return quantize_money(default_rent(seg, location, size) * units)


def cost_scale(size: CompanySize, channel: CompanyChannel, seg: Segment) -> Decimal:
    return SIZES[size].fixed * online_scale(seg, channel)


def monthly_fixed(seg: Segment, location: str, size: CompanySize, units: int = 1, *, channel: CompanyChannel = PHYSICAL,
                  site_mode: SiteMode | None = SiteMode.RENT) -> Decimal:
    scale = cost_scale(size, channel, seg) * units
    return quantize_money(sum((a for _, _, a in seg.fixed), D(0)) * scale
                          + monthly_rent(seg, location, size, units, channel=channel, site_mode=site_mode))


def minimum_capital(seg: Segment, location: str, size: CompanySize, channel: CompanyChannel = PHYSICAL,
                    site_mode: SiteMode | None = SiteMode.RENT) -> Decimal:
    """Mínimo para abrir: estrutura + estoque inicial + um mês de custos fixos + equipe OBRIGATÓRIA (1 mês de folha e o custo
    de contratação de Contador, Advogado e, no canal físico, Auxiliar de limpeza) (+ terreno, se comprado). A empresa nasce
    sem funcionários: o dono contrata a equipe depois, mas já abre com caixa para os cargos obrigatórios."""
    stock = sum((q * s.unit_cost for s, q in initial_stock_quantities(seg, location, size)), D(0))
    return quantize_money(setup_cost(seg, size, channel) + stock + monthly_fixed(seg, location, size, channel=channel, site_mode=site_mode)
                          + mandatory_setup_cost(seg, channel) + land_value(seg, channel, site_mode, location, size))


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
