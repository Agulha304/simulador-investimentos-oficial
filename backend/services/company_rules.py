"""Regras de empresas: segmentos, canais, localizações, portes e fórmulas de demanda/capacidade.

Tudo é configuração em código (nenhum dado externo). Para acrescentar um setor, basta incluir um `Segment` em `SEGMENTS`
e o valor correspondente em `CompanySegment`. Os sorteios usam hash de (empresa, mês): o mesmo mês dá sempre o mesmo
resultado (testável e sem surpresa a cada recarga de tela).

Empresas v2 (fase 1): cada segmento define os canais permitidos (ONLINE/PHYSICAL), a sua própria lista de localizações
(com demanda, aluguel e preço do terreno) e o tipo de métricas (`MetricsKind`).
"""
import logging
import math
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum

from backend.core.money import quantize_money
from backend.models import CompanyChannel, CompanyCostKind, CompanySegment, CompanySize, EmployeeLevel, EmployeeRegime, SiteMode
from backend.services.goods_rules import hash01

log = logging.getLogger(__name__)

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

# ---- fase 3a: mercado, relevância, tetos e mudança de endereço
MANDATORY_MIN_HOURS = 20            # cargo obrigatório conta como PREENCHIDO com jornada >= 20 h/semana (meio período vale)
FULL_TIME_HOURS = 36                # abaixo disso o salário é proporcional à jornada (36 h = referência de tempo integral)
RESERVE_MONTHS = D("6")             # reserva do capital mínimo: meses de custos fixos + folha (obrigatórios e equipe sugerida)
DEMAND_FLOOR = 0.25                 # fator de demanda com relevância 0 (quase nada, mas não zero)
DEMAND_EXP = 1.10                   # fator = FLOOR + (1 - FLOOR) * (relevância/100) ** EXP
PRICE_GAIN_CAP = 1.30               # preço abaixo do mercado vende mais, mas satura em +30%
ZERO_MONTH_BASE = 0.30              # chance de mês sem nenhuma venda com relevância 0 (decresce até REL_END)
ZERO_MONTH_REL_END = 40.0
CEILING_FACTOR = 1.6                # teto de produção/atendimento = 1,6x a demanda "de referência" do porte
STORAGE_MONTHS = 2.5                # teto de estoque: 2,5 meses da demanda de referência do porte
RELOCATION_RENT_MONTHS = D("3")     # mudança: 3 meses do aluguel do novo ponto (corretagem, caução, frete)
RELOCATION_SETUP_SHARE = D("0.30")  # + 30% do custo de estruturação do porte (reinstalação)
RELOCATION_BREAK_MONTHS = D("2")    # + multa de 2 aluguéis se o contrato de aluguel em vigor for encerrado
RELOCATION_SALES_MULT = 0.35        # no fechamento do mês da mudança a empresa vende só 35% (ficou parte do mês sem operar)
LAND_RESALE = D("0.92")             # venda do terreno antigo (comprado) na mudança: 92% do valor contábil

# ---- fase 5: qualidade, campanhas e aportes em 3 níveis
QUALITY_BASE = 50.0                 # qualidade inicial (0..100)
QUALITY_PRICE_TOL = 0.20            # qualidade 100 tolera preço +20% sobre o de mercado (qualidade 0: -20%); 50 = neutro
QUALITY_COST_SLOPE = 0.25           # custo de insumos/variável: +25% com qualidade 100 (-25% com 0), proporcional a (q-50)/50
QUALITY_REL_GAIN = 0.40             # ganho mensal extra de relevância com qualidade 100 (proporcional a (q-50)/50)
TIERS = ("BARATO", "MEDIO", "CARO")
TIER_LABEL = {"BARATO": "Barato", "MEDIO": "Médio", "CARO": "Caro"}
# custo do aporte POR TIPO e NÍVEL (barato, médio, caro): fração de `setup_cost x porte` (CAPACITY, NEW_UNIT, QUALITY, LARGER_PREMISES: do
# porte seguinte) ou múltiplo do custo-base de marketing do segmento x fator fixo do porte (MARKETING)
TIER_COST = {
    "CAPACITY": (D("0.10"), D("0.22"), D("0.45")),
    "NEW_UNIT": (D("0.60"), D("1.00"), D("1.70")),
    "QUALITY": (D("0.05"), D("0.12"), D("0.28")),
    "MARKETING": (D("0.5"), D("1.5"), D("4.0")),
    "LARGER_PREMISES": (D("0.40"), D("0.60"), D("1.00")),
}
EXPANSION_KINDS = tuple(TIER_COST)
# resultado possível de cada nível: (chance de efeito COMPLETO, chance de efeito PARCIAL); o resto é fracasso. Nunca garantido.
TIER_ODDS = {"CAPACITY": ((0.35, 0.30), (0.55, 0.28), (0.72, 0.20)), "QUALITY": ((0.40, 0.30), (0.58, 0.27), (0.75, 0.18)),
             "LARGER_PREMISES": ((0.45, 0.25), (0.70, 0.18), (0.88, 0.09))}
CAPACITY_GAIN = (0.40, 0.80, 1.40)  # níveis de capacidade (1 nível = +25%) no efeito completo; parcial = metade
QUALITY_GAIN = (5.0, 10.0, 20.0)    # pontos de qualidade no efeito completo; parcial = metade
BRANCH_REL_FRAC = (0.25, 0.40, 0.60)  # relevância inicial da filial = fração da relevância da marca (matriz), por nível
BRANCH_FAIL = (0.12, 0.07, 0.03)    # chance de a filial nem abrir (ponto/licença não vingou: perde metade do custo)
BRANCH_VIAB_SHAPE = (1.25, 1.0, 0.8)  # viabilidade = 0,3 + 1,1 * u**forma: nível maior => forma menor => média maior
VIAB_MIN, VIAB_MAX = 0.3, 1.4
BRANCH_CLOSE_LOSS = D("0.60")       # filial fecha se o resultado acumulado cair abaixo de -60% do custo de abertura (>= 3 meses)
BRANCH_MIN_AGE = 3
BRANCH_LAND_RESALE = LAND_RESALE
CAMPAIGN_FAIL = (0.30, 0.18, 0.10)  # chance de a campanha não ter NENHUM efeito
CAMPAIGN_VIRAL = (0.10, 0.17, 0.28)  # chance de efeito viral (acima do esperado)
CAMPAIGN_BOOST = (0.08, 0.14, 0.25)  # alta de demanda durante a campanha (efeito normal)
CAMPAIGN_MONTHS = (2, 3, 4)
CAMPAIGN_REL = (0.8, 2.0, 4.5)      # pontos de relevância imediatos (encolhem perto de 100)


class MetricsKind(StrEnum):
    PRODUCTION = "PRODUCTION"       # produz e controla estoque/insumos
    RETAIL = "RETAIL"               # revende mercadorias (estoque)
    SERVICE = "SERVICE"             # presta serviços/contratos: sem estoque nem "produtos"


@dataclass(frozen=True)
class Role:
    key: str
    label: str
    salary: Decimal            # nível pleno, jornada integral (cargos gerais: depende do porte, ver `role_for_size`)
    units: float               # capacidade (unidades/mês) por pessoa com produtividade 1
    hours: int = 0             # jornada sugerida (cargos gerais por porte; 0 = a do candidato)


@dataclass(frozen=True)
class Stock:
    name: str
    unit: str
    unit_cost: Decimal
    units_per_sale: Decimal
    supplier: str
    waste_pct: Decimal = D(0)
    category: str = ""             # chave da categoria de fornecimento que abastece o item (fase 4)


@dataclass(frozen=True)
class SupplyCategory:
    """Categoria de fornecimento do segmento (fase 4). `weight` = fatia do custo do produto/serviço (soma 1,0 no segmento);
    `per_sale` = unidades da categoria consumidas por unidade vendida; `ref_price` = preço de referência por unidade de compra
    (derivado: custo de referência por venda x peso / consumo), base das ofertas dos fornecedores."""
    key: str
    label: str
    unit: str
    weight: Decimal
    per_sale: Decimal
    ref_price: Decimal
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
    setup_cost: Decimal
    marketing_cost: Decimal
    description: str = ""
    fractional: bool = False                       # vendas em frações (obras)
    channels: tuple[CompanyChannel, ...] = (CompanyChannel.PHYSICAL,)
    locations: tuple[Location, ...] = ()
    metrics_kind: MetricsKind = MetricsKind.PRODUCTION
    supply_categories: tuple[SupplyCategory, ...] = ()

    @property
    def needs_suppliers(self) -> bool:
        return bool(self.supply_categories)

    def supply(self, key: str) -> SupplyCategory:
        for c in self.supply_categories:
            if c.key == key:
                return c
        raise KeyError(key)

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

    def role_for(self, key: str, size: CompanySize) -> Role:
        """Cargo com salário e jornada do PORTE (só os cargos gerais variam com o porte; os demais valem para qualquer porte)."""
        r = self.role(key)
        if key in GENERIC_BY_SIZE:
            sal, hours = GENERIC_BY_SIZE[key][size]
            return replace(r, salary=sal, hours=hours)
        return r

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
    max_staff: int = 12        # teto de funcionários por unidade


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
    CompanySize.SMALL: SizeSpec("Pequena", 1.0, 1.0, D("1.0"), D("1.0"), D("1.0"), 1, 12),
    CompanySize.MEDIUM: SizeSpec("Média", 1.7, 1.8, D("1.8"), D("1.6"), D("1.9"), 2, 28),
    CompanySize.LARGE: SizeSpec("Grande", 2.8, 3.2, D("3.0"), D("2.6"), D("3.4"), 3, 60),
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
# Salário-base (jornada integral) e jornada sugerida dos cargos gerais POR PORTE: a empresa pequena contrata meio período
# (um contador e um advogado "de balcão"), a grande tem profissionais plenos. Valores de `GENERIC_ROLES` = referência (grande).
GENERIC_BY_SIZE: dict[str, dict[CompanySize, tuple[Decimal, int]]] = {
    "accountant": {CompanySize.SMALL: (D(1800), 20), CompanySize.MEDIUM: (D(3200), 30), CompanySize.LARGE: (D(4500), 40)},
    "lawyer": {CompanySize.SMALL: (D(2400), 20), CompanySize.MEDIUM: (D(4500), 30), CompanySize.LARGE: (D(7000), 40)},
    "cleaner": {CompanySize.SMALL: (D(1520), 20), CompanySize.MEDIUM: (D(1600), 30), CompanySize.LARGE: (D(1700), 40)},
}


def _locs(seg_rent, rows) -> tuple[Location, ...]:
    """rows: (chave, nome, demanda, fator de aluguel, meses de aluguel que valem o terreno)."""
    return tuple(Location(k, label, dem, D(str(rf)), quantize_money(D(seg_rent) * D(str(rf)) * months))
                 for k, label, dem, rf, months in rows)


def _supply(price, var_pct, stock, rows) -> tuple[tuple[SupplyCategory, ...], tuple[Stock, ...]]:
    """Categorias de fornecimento (fase 4). Custo de referência por venda: o do estoque antigo (segmentos com estoque) ou
    `preço x custo variável%` (serviços com fornecedor). rows: (chave, nome, unidade, peso, consumo por venda)."""
    if not rows:
        return (), tuple(stock)
    if stock:
        total = sum((x.unit_cost * x.units_per_sale for x in stock), D(0))
        waste = stock[0].waste_pct
    else:
        total, waste = D(price) * D(var_pct) / 100, D(0)
    cats = tuple(SupplyCategory(k, label, unit, D(str(w)), D(str(ps)), (total * D(str(w)) / D(str(ps))).quantize(D("0.0001")), waste)
                 for k, label, unit, w, ps in rows)
    assert sum((c.weight for c in cats), D(0)) == D(1), "pesos das categorias devem somar 1,0"
    items = tuple(Stock(c.label, c.unit, c.ref_price, c.per_sale, "", c.waste_pct, c.key) for c in cats) if stock else ()
    return cats, items


def _seg(key, label, unit_label, price, demand, elast, vol, owner_cap, roles, staff, stock, var_pct, fixed, rent, setup,
         mkt, desc, *, kind, channels, locations, fractional=False, supply=()) -> Segment:
    cats, items = _supply(price, var_pct, stock, supply)
    return Segment(CompanySegment(key), label, unit_label, D(price), demand, elast, vol, owner_cap,
                   tuple(roles) + GENERIC_ROLES, tuple(staff), items, D(var_pct),
                   tuple((k, n, D(a)) for k, n, a in fixed), D(rent), D(setup), D(mkt), desc, fractional,
                   tuple(channels), _locs(rent, locations), kind, cats)


SEGMENTS: dict[CompanySegment, Segment] = {s.key: s for s in [
    _seg("RESTAURANT", "Restaurante", "refeição", 60, 2800, 1.2, 0.15, 400,
         [Role("cook", "Cozinheiro", D(2600), 690), Role("waiter", "Garçom", D(1850), 580),
          Role("chef", "Chef de cozinha", D(5200), 1000), Role("kitchen_aide", "Auxiliar de cozinha", D(1750), 470),
          Role("cashier", "Caixa", D(1800), 360)], ["cook", "waiter", "waiter"],
         [Stock("Ingredientes", "porção", D(17), D(1), "Atacadista Alimentar", D(8))], 0,
         [(K.UTILITIES, "Energia, água e gás", 2200), (K.TOOLS, "Limpeza e utensílios", 500), (K.ACCOUNTING, "Contabilidade", 600)],
         6000, 40000, 3000, "Compra ingredientes, atende por capacidade de cozinha e salão e sofre com desperdício.",
         kind=PRODUCTION, channels=[PHYSICAL],
         supply=[("carnes", "Carnes e peixes", "kg", "0.40", "0.12"), ("horti", "Hortifrúti", "kg", "0.25", "0.35"),
                 ("bebidas", "Bebidas", "litro", "0.20", "0.25"), ("embalagens", "Embalagens e descartáveis", "un", "0.15", "1")],
         locations=[("gastro", "Rua gastronômica", 1.35, 1.7, 90), ("centro", "Centro da capital", 1.25, 1.6, 95),
                    ("shopping", "Praça de alimentação de shopping", 1.4, 2.2, 80), ("bairro", "Bairro residencial", 1.0, 1.0, 100),
                    ("beira_mar", "Beira-mar", 1.3, 2.0, 120), ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("CAFE", "Cafeteria", "atendimento", 20, 5800, 1.3, 0.12, 1510,
         [Role("barista", "Barista", D(1900), 1740), Role("attendant", "Atendente", D(1700), 1390),
          Role("pastry", "Confeiteiro", D(2300), 1040), Role("manager", "Gerente de salão", D(3300), 700)], ["barista", "attendant"],
         [Stock("Insumos de café", "porção", D("5.2"), D(1), "Torrefação Local", D(5))], 0,
         [(K.UTILITIES, "Energia e água", 1500), (K.TOOLS, "Manutenção de máquinas", 300), (K.ACCOUNTING, "Contabilidade", 600)],
         4500, 30000, 2500, "Alto volume e ticket baixo: depende do fluxo de pessoas e do preço.",
         kind=PRODUCTION, channels=[PHYSICAL],
         supply=[("graos", "Grãos e insumos de café", "kg", "0.45", "0.02"), ("laticinios", "Laticínios e padaria", "kg", "0.35", "0.1"),
                 ("embalagens", "Embalagens", "un", "0.20", "1")],
         locations=[("centro", "Centro da capital", 1.25, 1.6, 95), ("shopping", "Shopping center", 1.4, 2.2, 80),
                    ("bairro", "Bairro residencial", 1.0, 1.0, 100), ("universitario", "Entorno de universidade", 1.2, 1.2, 90),
                    ("corporativo", "Região corporativa", 1.3, 1.8, 110), ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("CLOTHING", "Loja de roupas", "peça vendida", 140, 1150, 1.4, 0.25, 260,
         [Role("seller", "Vendedor", D(1750), 330), Role("stylist", "Visual merchandiser", D(2800), 130),
          Role("cashier", "Operador de caixa", D(1650), 260), Role("stockist", "Estoquista", D(1650), 200)], ["seller", "seller"],
         [Stock("Mercadorias", "peça", D(62), D(1), "Confecções Reunidas", D(2))], 0,
         [(K.UTILITIES, "Energia e internet", 1100), (K.TOOLS, "Vitrine e sistema", 400), (K.ACCOUNTING, "Contabilidade", 500)],
         5500, 45000, 3500, "Estoque de mercadorias, margem de revenda e forte sazonalidade.",
         kind=RETAIL, channels=[PHYSICAL, ONLINE],
         supply=[("confeccoes", "Confecções no atacado", "peça", "0.78", "1"), ("acessorios", "Acessórios", "un", "0.14", "0.3"),
                 ("embalagens", "Embalagens", "un", "0.08", "1")],
         locations=[("centro", "Centro comercial", 1.25, 1.6, 95), ("shopping", "Shopping center", 1.4, 2.2, 80),
                    ("bairro", "Bairro residencial", 1.0, 1.0, 100), ("rua_popular", "Rua de comércio popular", 1.2, 1.1, 90),
                    ("outlet", "Polo de moda e outlet", 1.1, 0.9, 85), ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("SUPERMARKET", "Supermercado", "compra", 88, 4500, 2.0, 0.08, 600,
         [Role("cashier", "Operador de caixa", D(1700), 1050), Role("stocker", "Repositor", D(1650), 900),
          Role("butcher", "Açougueiro", D(2400), 750), Role("bagger", "Empacotador", D(1550), 820)], ["cashier", "cashier", "stocker"],
         [Stock("Mercadorias", "item", D(54), D(1), "Distribuidora Central", D(3))], 0,
         [(K.UTILITIES, "Energia (refrigeração)", 3500), (K.TOOLS, "Sistema e equipamentos", 700), (K.ACCOUNTING, "Contabilidade", 700)],
         8500, 120000, 6000, "Margem apertada e demanda sensível ao preço; perecíveis geram perdas.",
         kind=RETAIL, channels=[PHYSICAL],
         supply=[("secos", "Alimentos secos", "kg", "0.40", "4"), ("horti_frios", "Hortifrúti e frios", "kg", "0.30", "2.5"),
                 ("limpeza", "Limpeza e higiene", "un", "0.15", "1"), ("bebidas", "Bebidas", "litro", "0.15", "2")],
         locations=[("bairro", "Bairro residencial", 1.0, 1.0, 100), ("centro", "Centro da capital", 1.25, 1.6, 95),
                    ("avenida", "Avenida de grande fluxo", 1.3, 1.8, 110), ("conjunto", "Entorno de conjunto habitacional", 1.15, 0.9, 85),
                    ("rodovia", "Atacarejo na rodovia", 1.1, 0.8, 75), ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("WORKSHOP", "Oficina mecânica", "serviço", 386, 380, 1.0, 0.12, 72,
         [Role("mechanic", "Mecânico", D(2700), 150), Role("assistant", "Auxiliar", D(1700), 83),
          Role("electrician", "Eletricista automotivo", D(2900), 110), Role("bodyworker", "Funileiro e pintor", D(2800), 95),
          Role("counter", "Atendente de balcão", D(1700), 140)], ["mechanic", "assistant"],
         [], 32,
         [(K.UTILITIES, "Energia e água", 1800), (K.TOOLS, "Ferramental", 900), (K.ACCOUNTING, "Contabilidade", 600)],
         5000, 60000, 3000, "Serviço com peças: a capacidade depende dos mecânicos; peças e fluidos entram nos custos variáveis.",
         kind=SERVICE, channels=[PHYSICAL],
         supply=[("pecas", "Peças e fluidos", "kit", "0.75", "1"), ("ferramentas", "Ferramentas e consumíveis", "un", "0.25", "1")],
         locations=[("avenida", "Avenida de grande fluxo", 1.3, 1.5, 105), ("bairro", "Bairro residencial", 1.0, 1.0, 100),
                    ("rodovia", "Beira de rodovia", 1.1, 0.8, 75), ("polo_auto", "Polo automotivo", 1.2, 1.0, 90),
                    ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("TECH", "Empresa de tecnologia", "contrato", 11000, 18, 1.1, 0.10, 2.6,
         [Role("dev", "Desenvolvedor", D(6500), 5.9), Role("designer", "Designer", D(4600), 3.9),
          Role("qa", "Analista de testes", D(4200), 3.9), Role("pm", "Gerente de projetos", D(7500), 2.9),
          Role("devops", "Engenheiro DevOps", D(8500), 5.9)], ["dev", "dev"],
         [], 10,
         [(K.UTILITIES, "Energia e internet", 900), (K.TOOLS, "Licenças e ferramentas", 2200), (K.ACCOUNTING, "Contabilidade", 800)],
         4000, 25000, 4000, "Receita recorrente por contratos; custo concentrado em pessoas e infraestrutura.",
         kind=SERVICE, channels=[PHYSICAL, ONLINE],
         locations=[("centro", "Centro empresarial", 1.25, 1.6, 95), ("parque_tech", "Parque tecnológico", 1.3, 1.8, 105),
                    ("coworking", "Espaço de coworking", 1.0, 0.7, 60), ("bairro", "Bairro residencial", 1.0, 1.0, 100),
                    ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("AGENCY", "Agência de marketing", "conta atendida", 8500, 18, 1.2, 0.15, 3.7,
         [Role("designer", "Designer", D(3800), 5.1), Role("account", "Atendimento", D(4300), 5.6),
          Role("copywriter", "Redator", D(3400), 5.1), Role("social", "Social media", D(3100), 5.6),
          Role("strategist", "Estrategista de mídia", D(5400), 4.4)], ["designer", "account"],
         [], 8,
         [(K.UTILITIES, "Energia e internet", 800), (K.TOOLS, "Ferramentas criativas", 1800), (K.ACCOUNTING, "Contabilidade", 700)],
         4000, 20000, 3000, "Poucos clientes de alto valor; perder uma conta pesa.",
         kind=SERVICE, channels=[PHYSICAL, ONLINE],
         locations=[("centro", "Centro empresarial", 1.25, 1.6, 95), ("avenida_corp", "Avenida corporativa", 1.4, 2.2, 110),
                    ("coworking", "Espaço de coworking", 1.0, 0.7, 60), ("bairro", "Bairro residencial", 1.0, 1.0, 100),
                    ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("INDUSTRY", "Indústria", "unidade produzida", 207, 2100, 1.3, 0.12, 260,
         [Role("operator", "Operador de máquina", D(2400), 410), Role("technician", "Técnico", D(3400), 180),
          Role("supervisor", "Supervisor de produção", D(5000), 210), Role("maintenance", "Mecânico de manutenção", D(3300), 140),
          Role("inspector", "Inspetor de qualidade", D(2900), 160)],
         ["operator", "operator", "operator", "technician"],
         [Stock("Matéria-prima", "kg", D(90), D(1), "Insumos Industriais", D(4))], 4,
         [(K.UTILITIES, "Energia industrial", 4500), (K.TOOLS, "Manutenção de máquinas", 1800), (K.ACCOUNTING, "Contabilidade", 1000)],
         10000, 250000, 8000, "Matéria-prima, equipamentos e capacidade produtiva limitam a produção.",
         kind=PRODUCTION, channels=[PHYSICAL],
         supply=[("materia_prima", "Matéria-prima", "kg", "0.55", "1"), ("componentes", "Componentes", "un", "0.25", "2"),
                 ("embalagens", "Embalagens", "un", "0.08", "1"), ("insumos", "Insumos industriais", "un", "0.12", "1")],
         locations=[("polo", "Polo industrial/logístico", 0.9, 0.8, 100), ("distrito", "Distrito industrial", 1.1, 1.0, 105),
                    ("rural", "Zona rural", 0.7, 0.5, 60), ("rodovia", "Margem de rodovia", 1.0, 0.9, 85),
                    ("porto", "Região portuária", 1.3, 1.5, 120)]),
    _seg("CONSTRUCTION", "Construtora", "obra", 39500, 10, 1.0, 0.30, 3,
         [Role("crew", "Equipe de obra", D(2600), 1.8), Role("engineer", "Engenheiro", D(6500), 1.5),
          Role("mason", "Pedreiro", D(2500), 1.5), Role("electrician", "Eletricista", D(2800), 0.99),
          Role("foreman", "Mestre de obras", D(4500), 1.4), Role("architect", "Arquiteto", D(6500), 0.85)],
         ["crew", "crew", "engineer"],
         [Stock("Materiais de obra", "lote", D(17000), D(1), "Depósito de Construção", D(5))], 5,
         [(K.UTILITIES, "Energia e canteiro", 1500), (K.TOOLS, "Equipamentos e EPI", 3000), (K.ACCOUNTING, "Contabilidade", 1500)],
         6000, 80000, 5000, "Poucas obras grandes por mês: receita volátil e dependente de materiais.",
         kind=PRODUCTION, channels=[PHYSICAL], fractional=True,
         supply=[("cimento", "Cimento e agregados", "saco", "0.30", "100"), ("aco", "Aço e ferragens", "kg", "0.40", "1000"),
                 ("acabamentos", "Acabamentos", "m²", "0.30", "100")],
         locations=[("centro", "Centro empresarial", 1.25, 1.6, 95), ("bairro", "Bairro residencial", 1.0, 1.0, 100),
                    ("polo", "Polo industrial/logístico", 0.9, 0.8, 100), ("litoral", "Litoral de alto padrão", 1.35, 1.8, 115),
                    ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("TRANSPORT", "Empresa de transporte", "viagem", 2450, 92, 1.1, 0.10, 17,
         [Role("driver", "Motorista", D(2900), 28), Role("dispatcher", "Operador logístico", D(2600), 41),
          Role("fleet_mechanic", "Mecânico de frota", D(2800), 12), Role("loader", "Ajudante de carga", D(1800), 19)],
         ["driver", "driver"],
         [], 45,
         [(K.UTILITIES, "Rastreamento e pátio", 600), (K.INSURANCE, "Seguro da frota", 2500), (K.TOOLS, "Manutenção de frota", 900)],
         3500, 150000, 4000, "Capacidade da frota e dos motoristas; combustível e pedágios entram nos custos variáveis.",
         kind=SERVICE, channels=[PHYSICAL],
         supply=[("combustivel", "Combustível", "litro", "0.60", "110"), ("pneus", "Pneus e manutenção", "kit", "0.40", "1")],
         locations=[("polo", "Polo industrial/logístico", 0.9, 0.8, 100), ("rodovia", "Margem de rodovia", 1.0, 0.7, 80),
                    ("porto", "Região portuária", 1.3, 1.4, 115), ("cd_urbano", "Centro de distribuição urbano", 1.15, 1.1, 100),
                    ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("REAL_ESTATE_AGENCY", "Imobiliária", "negócio fechado", 10000, 12, 1.3, 0.35, 3.1,
         [Role("broker", "Corretor", D(2700), 3.2), Role("appraiser", "Avaliador de imóveis", D(4000), 1.6),
          Role("photographer", "Fotógrafo de imóveis", D(2300), 1.4), Role("property_manager", "Administrador de locações", D(3400), 1.2),
          Role("sales_support", "Atendimento comercial", D(2000), 1)], ["broker", "broker"],
         [], 12,
         [(K.UTILITIES, "Energia e internet", 900), (K.TOOLS, "Portais e CRM", 1200), (K.ACCOUNTING, "Contabilidade", 700)],
         5000, 30000, 3500, "Receita por comissão, muito volátil conforme o mercado.",
         kind=SERVICE, channels=[PHYSICAL, ONLINE], fractional=True,
         locations=[("centro", "Centro da capital", 1.25, 1.6, 95), ("bairro", "Bairro residencial", 1.0, 1.0, 100),
                    ("bairro_nobre", "Bairro nobre", 1.4, 2.0, 115), ("litoral", "Litoral", 1.3, 1.8, 115),
                    ("interior", "Cidade do interior", 0.7, 0.6, 70)]),
    _seg("ECOMMERCE", "Comércio eletrônico", "pedido", 120, 960, 1.6, 0.20, 220,
         [Role("support", "Atendimento", D(1800), 260), Role("logistics", "Logística", D(1750), 290),
          Role("digital_marketing", "Analista de marketing digital", D(3700), 130), Role("catalog", "Analista de catálogo", D(3300), 86),
          Role("packer", "Embalador", D(1650), 320)], ["support", "logistics"],
         [], 45,
         [(K.UTILITIES, "Internet e energia", 600), (K.TOOLS, "Plataforma e ferramentas", 1800), (K.ACCOUNTING, "Contabilidade", 700)],
         3500, 35000, 3000, "Margem apertada, concorrência por preço e dependência de logística; produtos e frete nos custos variáveis.",
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
    if legacy is None:                  # localização desconhecida (dado antigo/corrompido): nunca derruba a listagem
        log.warning("localização desconhecida %r no segmento %s: usando o local de menor demanda", key, seg.key)
        if seg.locations:
            return min(seg.locations, key=lambda x: (x.demand, x.key))
        return ONLINE_LOCATION
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


def wage_hours_factor(hours_week: int) -> Decimal:
    """Salário proporcional à jornada: 36 h/semana (ou mais) = salário integral; abaixo disso, horas/36 (20 h = 55,6%)."""
    return min(D(1), D(hours_week) / FULL_TIME_HOURS)


def mandatory_roles(channel: CompanyChannel) -> tuple[str, ...]:
    """Cargos obrigatórios: Contador e Advogado sempre; Auxiliar de limpeza só no canal físico."""
    return ("accountant", "lawyer", "cleaner") if channel == CompanyChannel.PHYSICAL else ("accountant", "lawyer")


def missing_mandatory(channel: CompanyChannel, active_roles) -> list[str]:
    have = set(active_roles)
    return [r for r in mandatory_roles(channel) if r not in have]


def counts_as_filled(hours_week: int) -> bool:
    """REGRA: o cargo obrigatório está preenchido com QUALQUER contratado de jornada >= 20 h/semana (meio período vale);
    jornada integral não é exigida. (A contratação já exige >= 20 h, então todo contratado cumpre.)"""
    return hours_week >= MANDATORY_MIN_HOURS


def compliance_fine(seg: "Segment", missing: list[str], size: CompanySize = CompanySize.SMALL) -> Decimal:
    """Multa por irregularidade: 1 salário-base (jornada integral, do porte) de cada cargo obrigatório faltante, somados."""
    return quantize_money(sum((seg.role_for(r, size).salary for r in missing), D(0)))


def mandatory_monthly_payroll(seg: "Segment", channel: CompanyChannel, size: CompanySize = CompanySize.SMALL) -> Decimal:
    """Folha mensal (CLT, 2x) dos cargos obrigatórios na jornada sugerida do porte, ao salário-base."""
    total = D(0)
    for r in mandatory_roles(channel):
        role = seg.role_for(r, size)
        total += payroll_cost(quantize_money(role.salary * wage_hours_factor(role.hours or FULL_TIME_HOURS)))
    return quantize_money(total)


def mandatory_setup_cost(seg: "Segment", channel: CompanyChannel, size: CompanySize = CompanySize.SMALL) -> Decimal:
    """Para o capital mínimo: 1 mês de folha (CLT) + o custo de contratação (meio salário) dos cargos obrigatórios."""
    hiring = D(0)
    for r in mandatory_roles(channel):
        role = seg.role_for(r, size)
        hiring += role.salary * wage_hours_factor(role.hours or FULL_TIME_HOURS) * HIRING_COST_MONTHS
    return quantize_money(mandatory_monthly_payroll(seg, channel, size) + hiring)


def suggested_payroll(seg: "Segment", size: CompanySize) -> Decimal:
    """Folha mensal (CLT, 2x) da equipe produtiva SUGERIDA do segmento, ao salário-base."""
    return quantize_money(sum((payroll_cost(seg.role(r).salary) for r in initial_staff(seg, size)), D(0)))


def default_rent(seg: Segment, location: str, size: CompanySize) -> Decimal:
    """Aluguel mensal de referência do ponto (zero no canal online)."""
    return quantize_money(seg.rent * resolve_location(seg, location).rent * SIZES[size].rent)


def reputation_factor(reputation: int) -> float:
    return 0.6 + 0.8 * (reputation / 100)


# --- relevância e demanda

def relevance_factor(relevance: float) -> float:
    """Fator de demanda pela relevância (0-100): 20% com relevância 0, 100% com relevância 100."""
    x = max(0.0, min(100.0, float(relevance))) / 100
    return DEMAND_FLOOR + (1 - DEMAND_FLOOR) * x ** DEMAND_EXP


PRICE_CEILING = {"REAL_ESTATE_AGENCY": 1.5, "CONSTRUCTION": 1.6, "SUPERMARKET": 1.6, "ECOMMERCE": 1.7, "CAFE": 1.9,
                 "RESTAURANT": 2.0}                                       # acima disto ninguém compra
DEFAULT_CEILING = 2.0


def price_ceiling(seg: Segment) -> float:
    return PRICE_CEILING.get(seg.key.value, DEFAULT_CEILING)


def quality_price_ref(seg: Segment, quality: float = QUALITY_BASE) -> float:
    """Preço de mercado ajustado pela qualidade: produto melhor aguenta preço maior sem derrubar as vendas."""
    return float(seg.price) * (1 + QUALITY_PRICE_TOL * (float(quality) - QUALITY_BASE) / 50)


def price_ratio(seg: Segment, price: Decimal, quality: float = QUALITY_BASE) -> float:
    return float(price) / quality_price_ref(seg, quality)


def quality_cost_mult(quality: float = QUALITY_BASE) -> Decimal:
    """Multiplicador do custo de insumos/variável pela qualidade (1,00 com 50; 1,25 com 100)."""
    return D(1) + D(str(QUALITY_COST_SLOPE)) * (D(str(float(quality))) - D(str(QUALITY_BASE))) / 50


def price_factor(seg: Segment, price: Decimal, quality: float = QUALITY_BASE) -> float:
    """Preço abaixo do mercado vende mais, mas o ganho SATURA (+30%); acima do mercado a demanda desaba (elasticidade alta)
    e, passando do teto do setor, ninguém compra. O "mercado" sobe com a qualidade (ver `quality_price_ref`)."""
    r = price_ratio(seg, price, quality)
    if r <= 1:
        return min(PRICE_GAIN_CAP, r ** -seg.elasticity)
    ceil = price_ceiling(seg)
    if r >= ceil:
        return 0.0
    return (r ** -(seg.elasticity * 2.2)) * ((ceil - r) / (ceil - 1)) ** 1.3


def season_factor(seg: Segment, company_id: int, ref) -> float:
    return 1 + (hash01("season", company_id, ref.isoformat()) - 0.5) * 2 * seg.volatility


def zero_month_prob(relevance: float, price_ratio: float) -> float:
    """Chance de o mês fechar com ZERO vendas: alta com relevância baixa, cai até sumir em ~45 de relevância; preço
    acima de ~1,25x o de mercado soma chance (até +60 pontos)."""
    p = ZERO_MONTH_BASE * max(0.0, 1 - float(relevance) / ZERO_MONTH_REL_END) ** 1.5
    if price_ratio > 1.25:
        p += min(0.6, (price_ratio - 1.25) * 1.5)
    return min(0.95, p)


def is_zero_month(seed: int, company_id: int, ref, relevance: float, price_ratio: float) -> bool:
    """Sorteio determinístico (semente da partida + empresa + mês): o mesmo mês dá sempre o mesmo resultado."""
    return hash01(seed, "zero-month", company_id, ref.isoformat()) < zero_month_prob(relevance, price_ratio)


def demand_units(seg: Segment, *, location: str, size: CompanySize, units: int, reputation: int, price: Decimal,
                 company_id: int, ref, marketing: bool, season: bool = True, relevance: float = 100.0,
                 quality: float = QUALITY_BASE, marketing_boost: float = float(MARKETING_BOOST)) -> float:
    """Demanda do mês (unidades). `relevance` padrão 100 = mercado maduro; o motor passa a relevância real da empresa.
    `quality` (fase 5) desloca o preço de mercado; `marketing_boost` = alta de demanda da campanha ativa (padrão: a antiga, 12%)."""
    base = seg.base_demand * resolve_location(seg, location).demand * SIZES[size].demand * units
    d = base * relevance_factor(relevance) * reputation_factor(reputation) * price_factor(seg, price, quality)
    if season:
        d *= season_factor(seg, company_id, ref)
    if marketing:
        d *= 1 + marketing_boost
    return d


def reference_units(seg: Segment, size: CompanySize, units: int = 1) -> float:
    """Demanda de REFERÊNCIA do porte (sem local, relevância ou preço): base dos tetos de produção e de estoque."""
    return seg.base_demand * SIZES[size].demand * units


def production_ceiling(seg: Segment, size: CompanySize, units: int, capacity_level: int = 0) -> float:
    """TETO de produção (PRODUCTION/RETAIL) ou de atendimento (SERVICE) por mês: nenhuma equipe passa disto sem ampliar as
    instalações. Capacidade ampliada (+25% por nível) e novas unidades elevam o teto."""
    return reference_units(seg, size, units) * CEILING_FACTOR * (1 + 0.25 * capacity_level)


def storage_cap_units(seg: Segment, size: CompanySize, units: int, boost: float = 0.0) -> float:
    """Capacidade de estoque/armazenagem em UNIDADES VENDÁVEIS (quanto de vendas o depósito comporta). `boost` = ampliações (fase 5)."""
    return reference_units(seg, size, units) * STORAGE_MONTHS * (1 + float(boost))


def storage_cap_qty(seg: Segment, size: CompanySize, units: int, stock: "InventoryLike", boost: float = 0.0) -> Decimal:
    """Teto de estoque de um item, na unidade do item (considera consumo por venda e desperdício)."""
    sold_units = D(str(storage_cap_units(seg, size, units, boost)))
    return (sold_units * D(stock.units_per_sale) * (1 + D(stock.waste_pct) / 100)).quantize(D("0.001"))


def max_staff(size: CompanySize, units: int) -> int:
    return SIZES[size].max_staff * max(units, 1)


def capacity_units(seg: Segment, *, size: CompanySize, units: int, capacity_level: float, staff: list[tuple[str, Decimal]],
                   equipment_factor: float = 1.0, people_share: float = 1.0) -> float:
    """Capacidade da equipe (dono + pessoas), limitada pelo TETO de produção/atendimento do porte. `capacity_level` pode ser
    fracionário (aportes parciais). `people_share` (fase 5, filiais) = fatia da capacidade dos cargos produtivos GLOBAIS que
    cabe a esta unidade (a fatia da matriz + a das filiais soma 1)."""
    people = sum(seg.role(r).units * float(prod) for r, prod in staff if any(x.key == r for x in seg.roles)) * people_share
    raw = (seg.owner_capacity * SIZES[size].capacity + people) * units * (1 + 0.25 * capacity_level) * equipment_factor
    return min(raw, production_ceiling(seg, size, units, capacity_level))


def expected_units(seg: Segment, location: str, size: CompanySize, units: int = 1) -> float:
    """Demanda de mercado MADURO (relevância 100) do ponto; a real é multiplicada pelo fator de relevância."""
    return seg.base_demand * resolve_location(seg, location).demand * SIZES[size].demand * units


def initial_staff(seg: Segment, size: CompanySize) -> list[str]:
    """Equipe SUGERIDA (a empresa não nasce com ela desde a fase 2): cargos produtivos para o jogador contratar."""
    return list(seg.initial_staff) * SIZES[size].staff


def setup_cost(seg: Segment, size: CompanySize, channel: CompanyChannel = PHYSICAL) -> Decimal:
    return quantize_money(seg.setup_cost * SIZES[size].setup * online_scale(seg, channel))


def initial_stock_quantities(seg: Segment, location: str, size: CompanySize) -> list[tuple[Stock, Decimal]]:
    """Estoque inicial: ~2 meses da demanda do começo (relevância 0): evita ruptura sem encalhar caixa.
    Segmentos de serviço não têm estoque."""
    if not seg.has_stock:
        return []
    exp = expected_units(seg, location, size) * relevance_factor(0) * 2
    out = []
    for s in seg.stock:
        qty = D(str(exp)) * s.units_per_sale * (1 + s.waste_pct / 100)
        out.append((s, qty.quantize(D("0.001")) if seg.fractional else D(math.ceil(qty))))
    return out


def first_purchase_reserve(seg: Segment, location: str, size: CompanySize) -> Decimal:
    """Fase 4: a empresa NÃO nasce com estoque. O capital mínimo reserva em caixa o valor da 1ª compra (~2 meses da demanda do
    começo, a preço de referência) para o jogador comprar dos fornecedores que contratar. Serviços: zero."""
    return quantize_money(sum((q * s.unit_cost for s, q in initial_stock_quantities(seg, location, size)), D(0)))


def supply_cost_per_sale(seg: Segment, price_mult: Decimal = D(1)) -> Decimal:
    """Custo de insumos/fornecedores por unidade vendida (com desperdício), com os contratos a `price_mult` x o preço de referência."""
    return sum((c.per_sale * c.ref_price * price_mult * (1 + c.waste_pct / 100) for c in seg.supply_categories), D(0))


def supply_capacity(seg: Segment, volumes: dict[str, float], *, missing_is_zero: bool = True) -> float:
    """Capacidade efetiva em UNIDADES VENDIDAS pelos fornecedores: o menor `max_units_month / (consumo por venda x (1 + perda))`
    entre as categorias. `volumes` = volume mensal disponível (já com falha de entrega) de cada categoria; categoria sem contrato
    conta 0 (serviços) ou é ignorada (`missing_is_zero=False`: nos segmentos com estoque o que limita é o estoque, não a capacidade)."""
    if not seg.supply_categories:
        return math.inf
    out = math.inf
    for c in seg.supply_categories:
        if c.key not in volumes and not missing_is_zero:
            continue
        per = float(c.per_sale * (1 + c.waste_pct / 100))
        out = min(out, volumes.get(c.key, 0.0) / per if per > 0 else math.inf)
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


def operating_reserve(seg: Segment, location: str, size: CompanySize, channel: CompanyChannel = PHYSICAL,
                      site_mode: SiteMode | None = SiteMode.RENT) -> Decimal:
    """Reserva de caixa do capital mínimo: `RESERVE_MONTHS` meses de custos fixos + aluguel, folha dos obrigatórios e folha da
    equipe produtiva sugerida (as vendas começam fracas: a empresa precisa aguentar os primeiros meses de prejuízo)."""
    burn = (monthly_fixed(seg, location, size, channel=channel, site_mode=site_mode)
            + mandatory_monthly_payroll(seg, channel, size) + suggested_payroll(seg, size))
    return quantize_money(burn * RESERVE_MONTHS)


def minimum_capital(seg: Segment, location: str, size: CompanySize, channel: CompanyChannel = PHYSICAL,
                    site_mode: SiteMode | None = SiteMode.RENT) -> Decimal:
    """Mínimo para abrir: estrutura + reserva da 1ª compra de fornecedores (fase 4: o estoque NÃO nasce pronto) + (terreno, se comprado) + a RESERVA de operação (`RESERVE_MONTHS` meses de
    custos fixos e folha) + o custo de contratar os cargos obrigatórios. A empresa nasce sem funcionários: o dono contrata a
    equipe depois e o caixa já cobre vários meses de operação com vendas fracas."""
    stock = first_purchase_reserve(seg, location, size)
    hiring = mandatory_setup_cost(seg, channel, size) - mandatory_monthly_payroll(seg, channel, size)
    return quantize_money(setup_cost(seg, size, channel) + stock + operating_reserve(seg, location, size, channel, site_mode)
                          + hiring + land_value(seg, channel, site_mode, location, size))


def expansion_cost(seg: Segment, kind: str, size: CompanySize, units: int, tier: str = "MEDIO") -> Decimal:
    """Custo do aporte `kind` no nível `tier` (BARATO/MEDIO/CARO). Cada tipo tem a sua escala (ver `TIER_COST`)."""
    if kind not in TIER_COST or tier not in TIERS:
        raise KeyError(kind)
    f = TIER_COST[kind][TIERS.index(tier)]
    if kind == "MARKETING":
        return quantize_money(seg.marketing_cost * SIZES[size].fixed * f)
    if kind == "LARGER_PREMISES":
        nxt = SIZE_ORDER[min(SIZE_ORDER.index(size) + 1, 2)]
        return quantize_money(seg.setup_cost * SIZES[nxt].setup * f)
    return quantize_money(seg.setup_cost * SIZES[size].setup * f)


# ------------------------------------------------------------------ vendas do mês e relevância (puras: motor e simulação)

@dataclass(frozen=True)
class Sales:
    demand: float          # demanda do mês (já com relevância, preço, sazonalidade, marketing, economia)
    capacity: float        # capacidade da equipe, limitada pelo teto de produção
    potential: float       # o que poderia vender (0 em mês zerado ou empresa irregular)
    sold: float            # vendido (limitado por estoque)
    zero_month: bool
    stockout: bool


def sales_month(seg: Segment, *, location: str, size: CompanySize, units: int, capacity_level: float, relevance: float, reputation: int,
                price: Decimal, company_id, ref, seed: int, marketing: bool, staff: list[tuple[str, Decimal]],
                econ_mult: float = 1.0, relocation_mult: float = 1.0, equipment_factor: float = 1.0, stock_cap: float = math.inf,
                irregular: bool = False, season: bool = True, supply_cap: float = math.inf, quality: float = QUALITY_BASE,
                marketing_boost: float = float(MARKETING_BOOST), people_share: float = 1.0) -> Sales:
    """Vendas do mês. UMA função usada pelo fechamento mensal e pela simulação de balanceamento. Fase 5: `quality`, campanha com
    alta própria e `people_share` (filiais: cada unidade é calculada com `units=1` e a sua fatia da equipe; `company_id` pode ser
    um texto "empresa-unidade" para sorteios próprios da unidade)."""
    demand = demand_units(seg, location=location, size=size, units=units, reputation=reputation, price=price, company_id=company_id,
                          ref=ref, marketing=marketing, season=season, relevance=relevance, quality=quality,
                          marketing_boost=marketing_boost) * econ_mult * relocation_mult
    capacity = min(capacity_units(seg, size=size, units=units, capacity_level=capacity_level, staff=staff,
                                  equipment_factor=equipment_factor, people_share=people_share),
                   supply_cap)          # fase 4: fornecedores limitam a capacidade
    zero = (not irregular) and is_zero_month(seed, company_id, ref, relevance, price_ratio(seg, price, quality))
    potential = 0.0 if irregular or zero else min(demand, capacity)
    sold = min(potential, stock_cap)
    sold = round(max(sold, 0), 2) if seg.fractional else math.floor(max(sold, 0))
    return Sales(demand, capacity, potential, sold, zero, bool(stock_cap != math.inf) and stock_cap < potential)


def next_relevance(relevance: float, *, sold: float, demand: float, reputation: int, marketing: bool, stockout: bool,
                   price_ratio: float, irregular: bool, quality: float = QUALITY_BASE) -> float:
    """Relevância do mês seguinte (0-100). Sobe devagar com clientes atendidos (vendas >= 60% da demanda), reputação, marketing e
    estoque em dia; o ganho encolhe perto de 100. Cai em meses sem vendas ou irregulares."""
    if irregular:
        return max(0.0, relevance - 1.2)
    if sold <= 0:
        return max(0.0, relevance - 0.3)
    served = sold >= 0.6 * demand
    gain = (1.0 if served else 0.3) + 0.5 * (reputation - 50) / 50 + (0.3 if marketing else 0.0) + (0.15 if not stockout else 0.0)
    gain += 0.1 if price_ratio <= 1.1 else (-0.3 if price_ratio > 1.3 else 0.0)
    gain += QUALITY_REL_GAIN * (float(quality) - QUALITY_BASE) / 50          # fase 5: produto melhor conquista a clientela mais rápido
    gain = max(0.05, min(1.5, gain)) * (1 - relevance / 100) ** 0.7
    return min(100.0, relevance + gain)


def next_reputation(reputation: int, *, served: bool, stockout: bool, irregular: bool) -> int:
    return max(5, min(100, reputation + (2 if served else -4 if stockout or irregular else -1)))


# ------------------------------------------------------------------ mudança de endereço

def relocation_cost(seg: Segment, new_location: str, size: CompanySize, *, current_rent: Decimal, breaks_lease: bool) -> dict[str, Decimal]:
    """Custos da mudança: meses de aluguel do novo ponto + reinstalação (parte do setup) + multa se encerrar um aluguel."""
    move = quantize_money(default_rent(seg, new_location, size) * RELOCATION_RENT_MONTHS)
    reinstall = quantize_money(seg.setup_cost * SIZES[size].setup * RELOCATION_SETUP_SHARE)
    fine = quantize_money(current_rent * RELOCATION_BREAK_MONTHS) if breaks_lease else D("0.00")
    return {"move": move, "reinstall": reinstall, "fine": fine, "total": quantize_money(move + reinstall + fine)}


def relevance_after_move(seg: Segment, relevance: float, old_location: str, new_location: str) -> float:
    """Mudar de ponto perde parte da clientela: mantém 60% a 95% da relevância, mais quanto melhor o novo ponto."""
    delta = resolve_location(seg, new_location).demand - resolve_location(seg, old_location).demand
    keep = max(0.60, min(0.95, 0.82 + 0.4 * delta))
    return round(float(relevance) * keep, 2)
