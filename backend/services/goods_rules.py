"""Regras configuráveis de bens: valorização por categoria, taxas, financiamento e catálogo simulado.

Nada aqui depende de serviços externos. Os padrões podem ser sobrescritos pela tabela `valuation_rules`
(valorização) sem mudar o código. O ruído mensal é DETERMINÍSTICO (hash), então os mesmos meses
produzem sempre os mesmos valores (testável e sem surpresa a cada recarga de tela).
"""
import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.core.money import quantize_money
from backend.models import REAL_ESTATE, CostKind, GoodCategory

D = Decimal


@dataclass(frozen=True)
class Rule:
    drift_pct: Decimal          # variação média mensal (negativa = depreciação)
    volatility_pct: Decimal     # amplitude do ruído mensal
    uncertainty_pct: Decimal    # incerteza da avaliação (faixa ao avaliar)


DEFAULT_RULES: dict[GoodCategory, Rule] = {
    GoodCategory.RESIDENTIAL: Rule(D("0.45"), D("1.0"), D("5")),
    GoodCategory.COMMERCIAL: Rule(D("0.35"), D("1.4"), D("8")),
    GoodCategory.LAND: Rule(D("0.50"), D("1.8"), D("10")),
    GoodCategory.CAR: Rule(D("-1.00"), D("0.6"), D("3")),
    GoodCategory.MOTORCYCLE: Rule(D("-0.90"), D("0.7"), D("3")),
    GoodCategory.INSTRUMENT: Rule(D("0.05"), D("1.2"), D("6")),
    GoodCategory.EQUIPMENT: Rule(D("-1.30"), D("0.8"), D("4")),
    GoodCategory.ANTIQUE: Rule(D("0.25"), D("3.5"), D("20")),
    GoodCategory.COLLECTIBLE: Rule(D("0.30"), D("4.5"), D("25")),
    GoodCategory.OTHER: Rule(D("0.00"), D("1.0"), D("10")),
}

# taxas e impostos de compra / custos de venda (% do preço)
PURCHASE_FEE_PCT = {GoodCategory.RESIDENTIAL: D("4.0"), GoodCategory.COMMERCIAL: D("4.0"), GoodCategory.LAND: D("4.0"),
                    GoodCategory.CAR: D("1.5"), GoodCategory.MOTORCYCLE: D("1.5")}
SALE_FEE_PCT = {GoodCategory.RESIDENTIAL: D("5.0"), GoodCategory.COMMERCIAL: D("5.0"), GoodCategory.LAND: D("5.0"),
                GoodCategory.CAR: D("1.0"), GoodCategory.MOTORCYCLE: D("1.0"), GoodCategory.INSTRUMENT: D("3.0"),
                GoodCategory.EQUIPMENT: D("2.0"), GoodCategory.ANTIQUE: D("10.0"), GoodCategory.COLLECTIBLE: D("10.0"),
                GoodCategory.OTHER: D("3.0")}


@dataclass(frozen=True)
class FinancingTerms:
    max_ltv_pct: Decimal        # máximo financiado sobre o preço
    annual_rate_pct: Decimal    # taxa padrão
    max_term_months: int


FINANCING: dict[GoodCategory, FinancingTerms] = {
    GoodCategory.RESIDENTIAL: FinancingTerms(D("80"), D("10.5"), 420),
    GoodCategory.COMMERCIAL: FinancingTerms(D("70"), D("12.0"), 240),
    GoodCategory.LAND: FinancingTerms(D("60"), D("12.0"), 180),
    GoodCategory.CAR: FinancingTerms(D("80"), D("21.0"), 60),
    GoodCategory.MOTORCYCLE: FinancingTerms(D("80"), D("22.0"), 48),
    GoodCategory.EQUIPMENT: FinancingTerms(D("70"), D("24.0"), 36),
}

COST_LABEL = {CostKind.IPTU: "IPTU", CostKind.CONDO: "Condomínio", CostKind.MAINTENANCE: "Manutenção",
              CostKind.FUEL: "Combustível", CostKind.INSURANCE: "Seguro", CostKind.IPVA: "IPVA",
              CostKind.LICENSING: "Licenciamento", CostKind.PARKING: "Estacionamento", CostKind.OTHER: "Outros custos"}
# categoria do orçamento onde cada custo aparece (despesas padrão de ensure_categories)
COST_BUDGET_CATEGORY = {CostKind.IPTU: "Moradia", CostKind.CONDO: "Moradia", CostKind.MAINTENANCE: "Moradia",
                        CostKind.FUEL: "Transporte", CostKind.INSURANCE: "Transporte", CostKind.IPVA: "Impostos",
                        CostKind.LICENSING: "Impostos", CostKind.PARKING: "Transporte", CostKind.OTHER: "Outros"}

FUEL_PRICE_PER_LITER = D("6.20")
VEHICLE_DEFAULT_KM_MONTH = 800
VEHICLE_KM_PER_LITER = D("11")

# vacância / ocupação simuladas (probabilidades mensais)
VACATE_PROB = 0.08
FILL_BASE_PROB = 0.55


def hash01(*parts: object) -> float:
    """Número determinístico em [0, 1) a partir de uma chave."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def market_rent(category: GoodCategory, value: Decimal) -> Decimal:
    pct = D("0.70") if category == GoodCategory.COMMERCIAL else D("0.50")
    return quantize_money(value * pct / 100)


def monthly_factor(rule: Rule, key: str, month: date) -> Decimal:
    noise = Decimal(str(hash01("value", key, month.isoformat()) * 2 - 1))
    return D(1) + (rule.drift_pct + rule.volatility_pct * noise) / 100


def default_costs(category: GoodCategory, value: Decimal, *, area_m2: Decimal | None = None,
                  property_type: str | None = None, km_month: int = VEHICLE_DEFAULT_KM_MONTH):
    """Custos padrão ao comprar: lista de (kind, amount, frequency_name)."""
    q = quantize_money
    out: list[tuple[CostKind, Decimal, str]] = []
    if category in (GoodCategory.RESIDENTIAL, GoodCategory.COMMERCIAL):
        out.append((CostKind.IPTU, q(value * D("0.008") / 12), "MONTHLY"))
        if property_type == "apartment" or category == GoodCategory.COMMERCIAL:
            out.append((CostKind.CONDO, q((area_m2 or D(60)) * D("7.5")), "MONTHLY"))
        out.append((CostKind.MAINTENANCE, q(value * D("0.005") / 12), "MONTHLY"))
    elif category == GoodCategory.LAND:
        out.append((CostKind.IPTU, q(value * D("0.005") / 12), "MONTHLY"))
    elif category in (GoodCategory.CAR, GoodCategory.MOTORCYCLE):
        car = category == GoodCategory.CAR
        out.append((CostKind.FUEL, q(D(km_month) / VEHICLE_KM_PER_LITER * FUEL_PRICE_PER_LITER), "MONTHLY"))
        out.append((CostKind.INSURANCE, q(value * D("0.04") / 12), "MONTHLY"))
        out.append((CostKind.IPVA, q(value * (D("0.04") if car else D("0.02"))), "ANNUAL"))
        out.append((CostKind.LICENSING, q(D("160") if car else D("90")), "ANNUAL"))
        out.append((CostKind.MAINTENANCE, q(value * D("0.02") / 12), "MONTHLY"))
    elif category in (GoodCategory.INSTRUMENT, GoodCategory.EQUIPMENT):
        out.append((CostKind.MAINTENANCE, q(value * D("0.01") / 12), "MONTHLY"))
    return [c for c in out if c[1] > 0]


# ------------------------------------------------------------------ catálogo simulado (sem fontes externas)

@dataclass(frozen=True)
class Listing:
    key: str
    category: GoodCategory
    name: str
    description: str
    base_price: Decimal
    location: str
    condition: str | None = None
    property_type: str | None = None
    address: str | None = None
    area_m2: Decimal | None = None
    bedrooms: int | None = None
    km: int | None = None


def _l(key, cat, name, desc, price, loc, cond=None, **kw) -> Listing:
    return Listing(key, cat, name, desc, D(price), loc, cond, **{k: (D(v) if k == "area_m2" else v) for k, v in kw.items()})


R, C, L = GoodCategory.RESIDENTIAL, GoodCategory.COMMERCIAL, GoodCategory.LAND
CATALOG: list[Listing] = [
    _l("apto-sp-studio", R, "Studio na Vila Mariana", "Studio mobiliado perto do metrô.", "320000", "São Paulo, SP", "GOOD",
       property_type="apartment", address="Rua Domingos de Morais, 1200", area_m2="32", bedrooms=1),
    _l("apto-bh-2q", R, "Apartamento 2 quartos em Savassi", "Prédio com portaria e uma vaga.", "540000", "Belo Horizonte, MG", "EXCELLENT",
       property_type="apartment", address="Rua Pernambuco, 800", area_m2="68", bedrooms=2),
    _l("apto-rj-3q", R, "Apartamento 3 quartos no Leblon", "Vista parcial para o mar.", "1850000", "Rio de Janeiro, RJ", "EXCELLENT",
       property_type="apartment", address="Rua Dias Ferreira, 300", area_m2="110", bedrooms=3),
    _l("casa-cwb-3q", R, "Casa 3 quartos no Bacacheri", "Casa com quintal e garagem para dois carros.", "780000", "Curitiba, PR", "GOOD",
       property_type="house", address="Rua Nilo Cairo, 45", area_m2="180", bedrooms=3),
    _l("casa-flo-2q", R, "Casa 2 quartos em Campeche", "A 600 m da praia, precisa de reformas leves.", "690000", "Florianópolis, SC", "FAIR",
       property_type="house", address="Rua das Gaivotas, 210", area_m2="95", bedrooms=2),
    _l("casa-poa-4q", R, "Casa 4 quartos em Moinhos de Vento", "Casa ampla com piscina.", "2400000", "Porto Alegre, RS", "EXCELLENT",
       property_type="house", address="Rua Padre Chagas, 77", area_m2="320", bedrooms=4),
    _l("sala-sp-comercial", C, "Sala comercial na Faria Lima", "Sala de 45 m² em torre corporativa.", "890000", "São Paulo, SP", "EXCELLENT",
       property_type="commercial", address="Av. Brig. Faria Lima, 2000", area_m2="45"),
    _l("loja-cwb-rua", C, "Loja de rua no Batel", "Loja térrea com vitrine.", "1300000", "Curitiba, PR", "GOOD",
       property_type="commercial", address="Rua Alferes Poli, 500", area_m2="120"),
    _l("galpao-campinas", C, "Galpão logístico em Campinas", "Galpão de 600 m² com doca.", "2900000", "Campinas, SP", "GOOD",
       property_type="commercial", address="Rod. D. Pedro I, km 100", area_m2="600"),
    _l("terreno-atibaia", L, "Terreno em condomínio em Atibaia", "Terreno plano de 1.000 m².", "260000", "Atibaia, SP", None,
       property_type="land", address="Condomínio Vale Verde, lote 12", area_m2="1000"),
    _l("terreno-bombinhas", L, "Terreno perto da praia em Bombinhas", "Lote de 450 m² a 400 m do mar.", "420000", "Bombinhas, SC", None,
       property_type="land", address="Rua dos Corais, lote 7", area_m2="450"),
    _l("carro-hatch-novo", GoodCategory.CAR, "Hatch compacto 0 km", "Motor 1.0, câmbio manual.", "82000", "Concessionária", "NEW"),
    _l("carro-sedan-usado", GoodCategory.CAR, "Sedan médio 2021", "62 mil km, único dono.", "98000", "São Paulo, SP", "GOOD", km=62000),
    _l("carro-suv-usado", GoodCategory.CAR, "SUV 2019", "80 mil km, revisões em dia.", "135000", "Curitiba, PR", "GOOD", km=80000),
    _l("carro-eletrico", GoodCategory.CAR, "Hatch elétrico 2023", "Autonomia de 300 km.", "190000", "Concessionária", "EXCELLENT", km=15000),
    _l("moto-125", GoodCategory.MOTORCYCLE, "Moto 160 cc", "Econômica para o dia a dia.", "17500", "Concessionária", "NEW"),
    _l("moto-trail", GoodCategory.MOTORCYCLE, "Moto trail 300 cc 2020", "30 mil km.", "28000", "Belo Horizonte, MG", "GOOD", km=30000),
    _l("violao-aco", GoodCategory.INSTRUMENT, "Violão de aço profissional", "Tampo maciço de cedro.", "6500", "Loja de instrumentos", "EXCELLENT"),
    _l("guitarra-vintage", GoodCategory.INSTRUMENT, "Guitarra elétrica 1978 (vintage)", "Instrumento de coleção, conservado.", "42000", "Colecionador", "GOOD"),
    _l("piano-vertical", GoodCategory.INSTRUMENT, "Piano vertical", "Afinado e revisado.", "18000", "São Paulo, SP", "GOOD"),
    _l("violino-luthier", GoodCategory.INSTRUMENT, "Violino de luthier", "Feito à mão no Brasil.", "24000", "Cremona Ateliê", "EXCELLENT"),
    _l("camera-pro", GoodCategory.EQUIPMENT, "Câmera mirrorless profissional", "Com duas lentes.", "21000", "Loja especializada", "EXCELLENT"),
    _l("estudio-audio", GoodCategory.EQUIPMENT, "Kit de estúdio de gravação", "Interface, microfones e monitores.", "14000", "Loja especializada", "NEW"),
    _l("relogio-antigo", GoodCategory.ANTIQUE, "Relógio de bolso suíço (1910)", "Funcionando, com certificado.", "9500", "Leilão", "GOOD"),
    _l("movel-colonial", GoodCategory.ANTIQUE, "Cômoda colonial do século XIX", "Jacarandá, restauro parcial.", "16000", "Antiquário", "FAIR"),
    _l("moeda-rara", GoodCategory.COLLECTIBLE, "Moeda de ouro rara (1822)", "Coleção numismática.", "28000", "Leilão", "GOOD"),
    _l("hq-primeira-edicao", GoodCategory.COLLECTIBLE, "HQ de primeira edição lacrada", "Edição limitada, em estojo.", "7500", "Colecionador", "EXCELLENT"),
]
CATALOG_BY_KEY = {l.key: l for l in CATALOG}
EPOCH = date(2026, 11, 1)


def month_index(month: date) -> int:
    return (month.year - EPOCH.year) * 12 + (month.month - EPOCH.month)
