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
from backend.services import br_taxes
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


def purchase_fee(category: GoodCategory, price: Decimal, location: str | None) -> tuple[Decimal, list[tuple[str, Decimal, Decimal]]]:
    """Impostos e taxas da compra (ITBI, registro, transferência...): total e detalhamento."""
    parts = br_taxes.purchase_taxes(category, price, location)
    return quantize_money(sum((a for _, _, a in parts), D(0))), parts


def market_nightly(category: GoodCategory, value: Decimal) -> Decimal:
    """Diária sugerida para hospedagem de temporada: rende mais que o aluguel fixo, mas dá trabalho e tem custos."""
    return quantize_money(market_rent(category, value) * D("0.10"))


GROUPS = {"realty": REAL_ESTATE, "vehicles": (GoodCategory.CAR, GoodCategory.MOTORCYCLE),
          "goods": (GoodCategory.INSTRUMENT, GoodCategory.EQUIPMENT, GoodCategory.ANTIQUE, GoodCategory.COLLECTIBLE, GoodCategory.OTHER)}


def market_rent(category: GoodCategory, value: Decimal) -> Decimal:
    pct = D("0.70") if category == GoodCategory.COMMERCIAL else D("0.50")
    return quantize_money(value * pct / 100)


def monthly_factor(rule: Rule, key: str, month: date) -> Decimal:
    noise = Decimal(str(hash01("value", key, month.isoformat()) * 2 - 1))
    return D(1) + (rule.drift_pct + rule.volatility_pct * noise) / 100


def default_costs(category: GoodCategory, value: Decimal, *, area_m2: Decimal | None = None,
                  property_type: str | None = None, km_month: int = VEHICLE_DEFAULT_KM_MONTH, location: str | None = None):
    """Custos padrão ao comprar: lista de (kind, amount, frequency_name)."""
    q = quantize_money
    out: list[tuple[CostKind, Decimal, str]] = []
    if category in (GoodCategory.RESIDENTIAL, GoodCategory.COMMERCIAL):
        out.append((CostKind.IPTU, q(value * br_taxes.iptu_rate(location) / 100 / 12), "MONTHLY"))
        if property_type == "apartment" or category == GoodCategory.COMMERCIAL:
            out.append((CostKind.CONDO, q((area_m2 or D(60)) * D("7.5")), "MONTHLY"))
        out.append((CostKind.MAINTENANCE, q(value * D("0.005") / 12), "MONTHLY"))
    elif category == GoodCategory.LAND:
        out.append((CostKind.IPTU, q(value * br_taxes.iptu_rate(location) * D("0.6") / 100 / 12), "MONTHLY"))      # terreno: alíquota menor
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

    # ---- imóveis (mais cidades, tipos e perfis: bom para morar, alugar ou hospedar por temporada)
    _l("kitnet-sp", R, "Kitnet na Barra Funda", "Compacta, perto do metrô e de faculdades.", "190000", "São Paulo, SP", "FAIR",
       property_type="apartment", address="Rua Vitorino Carmilo, 400", area_m2="24", bedrooms=1),
    _l("apto-recife-2q", R, "Apartamento 2 quartos em Boa Viagem", "A duas quadras da praia.", "620000", "Recife, PE", "GOOD",
       property_type="apartment", address="Av. Boa Viagem, 3000", area_m2="72", bedrooms=2),
    _l("flat-salvador", R, "Flat mobiliado na Barra", "Prédio com recepção e piscina, ótimo para temporada.", "480000", "Salvador, BA", "EXCELLENT",
       property_type="apartment", address="Av. Oceânica, 1500", area_m2="38", bedrooms=1),
    _l("apto-fortaleza-3q", R, "Apartamento 3 quartos na Meireles", "Vista para o mar e lazer completo.", "960000", "Fortaleza, CE", "EXCELLENT",
       property_type="apartment", address="Av. Beira Mar, 2200", area_m2="105", bedrooms=3),
    _l("cobertura-rj", R, "Cobertura duplex em Ipanema", "Terraço com vista para a Lagoa.", "4200000", "Rio de Janeiro, RJ", "EXCELLENT",
       property_type="apartment", address="Rua Visconde de Pirajá, 90", area_m2="230", bedrooms=4),
    _l("chale-gramado", R, "Chalé em Gramado", "Charmoso, a 5 minutos do centro: sucesso em temporada.", "850000", "Gramado, RS", "EXCELLENT",
       property_type="house", address="Rua das Hortênsias, 120", area_m2="85", bedrooms=2),
    _l("casa-praia-flo", R, "Casa de praia em Jurerê", "Piscina e quatro suítes.", "3100000", "Florianópolis, SC", "EXCELLENT",
       property_type="house", address="Rua dos Búzios, 35", area_m2="260", bedrooms=4),
    _l("sobrado-campinas", R, "Sobrado 3 quartos em Campinas", "Bairro tranquilo, perto de escolas.", "720000", "Campinas, SP", "GOOD",
       property_type="house", address="Rua Barão de Itapura, 800", area_m2="150", bedrooms=3),
    _l("casa-bsb", R, "Casa 3 quartos no Lago Sul", "Ampla, com quintal arborizado.", "1900000", "Brasília, DF", "GOOD",
       property_type="house", address="QL 12, conjunto 4", area_m2="280", bedrooms=3),
    _l("apto-goiania", R, "Apartamento 2 quartos no Setor Bueno", "Condomínio novo com academia.", "430000", "Goiânia, GO", "NEW",
       property_type="apartment", address="Rua T-30, 700", area_m2="64", bedrooms=2),
    _l("casa-popular-poa", R, "Casa popular em Porto Alegre", "Duas peças, bom para quem está começando.", "260000", "Porto Alegre, RS", "FAIR",
       property_type="house", address="Rua Frederico Mentz, 55", area_m2="70", bedrooms=2),
    _l("sitio-atibaia", R, "Sítio com lago em Atibaia", "Casa de campo e pomar.", "1100000", "Atibaia, SP", "GOOD",
       property_type="house", address="Estrada do Rio Abaixo, km 4", area_m2="500", bedrooms=3),
    _l("loja-shopping-bh", C, "Loja em shopping de BH", "Quiosque amplo em corredor de grande circulação.", "640000", "Belo Horizonte, MG", "GOOD",
       property_type="commercial", address="Shopping Del Rey, loja 214", area_m2="38"),
    _l("sala-recife", C, "Sala comercial no Recife Antigo", "Prédio histórico restaurado.", "380000", "Recife, PE", "GOOD",
       property_type="commercial", address="Rua do Bom Jesus, 90", area_m2="32"),
    _l("terreno-gramado", L, "Terreno em Gramado", "Lote com vista para o vale.", "540000", "Gramado, RS", None,
       property_type="land", address="Rua das Azaleias, lote 3", area_m2="600"),
    _l("terreno-goiania", L, "Terreno em condomínio em Goiânia", "Esquina, pronto para construir.", "310000", "Goiânia, GO", None,
       property_type="land", address="Alameda dos Ipês, lote 18", area_m2="420"),
    # ---- automóveis
    _l("carro-popular-usado", GoodCategory.CAR, "Carro popular 2015", "Econômico, bom para o dia a dia.", "38000", "Goiânia, GO", "GOOD", km=110000),
    _l("carro-hatch-medio", GoodCategory.CAR, "Hatch médio 2020", "Completo, com central multimídia.", "74000", "Recife, PE", "GOOD", km=48000),
    _l("carro-sedan-novo", GoodCategory.CAR, "Sedan executivo 0 km", "Motor 2.0 turbo, couro e teto solar.", "165000", "Concessionária", "NEW"),
    _l("carro-pickup", GoodCategory.CAR, "Picape cabine dupla 2021", "Diesel, ideal para trabalho e estrada.", "225000", "Goiânia, GO", "GOOD", km=70000),
    _l("carro-minivan", GoodCategory.CAR, "Minivan 7 lugares 2019", "Espaço para a família toda.", "112000", "Campinas, SP", "GOOD", km=88000),
    _l("carro-esportivo", GoodCategory.CAR, "Esportivo conversível", "Dois lugares, muita potência.", "480000", "Concessionária", "EXCELLENT", km=9000),
    _l("carro-van-utilitaria", GoodCategory.CAR, "Van utilitária 2020", "Boa para entregas e pequenos negócios.", "132000", "São Paulo, SP", "GOOD", km=65000),
    _l("carro-classico", GoodCategory.CAR, "Clássico dos anos 70 restaurado", "Peça de colecionador, uso eventual.", "88000", "Colecionador", "GOOD", km=30000),
    _l("moto-scooter", GoodCategory.MOTORCYCLE, "Scooter urbana 125 cc", "Prática e econômica na cidade.", "13500", "Concessionária", "NEW"),
    _l("moto-custom", GoodCategory.MOTORCYCLE, "Moto custom 650 cc", "Estilo clássico para viagens.", "46000", "Curitiba, PR", "GOOD", km=22000),
    _l("moto-esportiva", GoodCategory.MOTORCYCLE, "Moto esportiva 600 cc 2021", "Rápida e potente.", "52000", "São Paulo, SP", "EXCELLENT", km=12000),
    _l("moto-eletrica", GoodCategory.MOTORCYCLE, "Moto elétrica urbana", "Silenciosa, recarga em casa.", "29000", "Concessionária", "NEW"),
    _l("moto-entregas", GoodCategory.MOTORCYCLE, "Moto 150 cc para entregas", "Econômica, ótima para trabalhar com apps.", "11500", "Goiânia, GO", "GOOD", km=40000),
    # ---- outros bens (instrumentos, equipamentos, antiguidades, coleções)
    _l("bateria-acustica", GoodCategory.INSTRUMENT, "Bateria acústica completa", "Cinco peças com pratos.", "9800", "Loja de instrumentos", "GOOD"),
    _l("saxofone", GoodCategory.INSTRUMENT, "Saxofone alto profissional", "Revisado, com estojo.", "14500", "Loja de instrumentos", "EXCELLENT"),
    _l("teclado-sintetizador", GoodCategory.INSTRUMENT, "Teclado sintetizador", "88 teclas pesadas.", "7200", "Loja de instrumentos", "NEW"),
    _l("drone-pro", GoodCategory.EQUIPMENT, "Drone profissional 4K", "Para fotografia e mapeamento.", "16500", "Loja especializada", "NEW"),
    _l("notebook-pro", GoodCategory.EQUIPMENT, "Notebook de alto desempenho", "Para edição e programação.", "13500", "Loja especializada", "NEW"),
    _l("equip-academia", GoodCategory.EQUIPMENT, "Equipamentos de academia domiciliar", "Esteira, banco e halteres.", "11000", "Loja especializada", "GOOD"),
    _l("trator-pequeno", GoodCategory.EQUIPMENT, "Micro trator agrícola", "Para pequenas propriedades.", "78000", "Revenda agrícola", "GOOD"),
    _l("quadro-aquarela", GoodCategory.ANTIQUE, "Aquarela de paisagista do século XX", "Com certificado de autenticidade.", "34000", "Galeria", "GOOD"),
    _l("escultura-bronze", GoodCategory.ANTIQUE, "Escultura em bronze (1930)", "Peça de ateliê numerada.", "26000", "Leilão", "EXCELLENT"),
    _l("tapete-persa", GoodCategory.ANTIQUE, "Tapete persa antigo", "Feito à mão, lã e seda.", "21000", "Antiquário", "GOOD"),
    _l("joia-colar", GoodCategory.OTHER, "Colar de ouro e esmeraldas", "Joia com certificado.", "38000", "Joalheria", "EXCELLENT"),
    _l("relogio-luxo", GoodCategory.OTHER, "Relógio suíço de luxo", "Automático, com caixa e garantia.", "52000", "Joalheria", "EXCELLENT"),
    _l("vinhos-safra", GoodCategory.COLLECTIBLE, "Coleção de vinhos de guarda", "Doze garrafas de safras premiadas.", "24000", "Adega", "EXCELLENT"),
    _l("figurinhas-album", GoodCategory.COLLECTIBLE, "Álbum de figurinhas raro completo", "Edição de 1970 completa.", "9000", "Colecionador", "GOOD"),
    _l("cartas-colecao", GoodCategory.COLLECTIBLE, "Cartas colecionáveis raras", "Lote lacrado de primeira edição.", "15500", "Colecionador", "EXCELLENT"),
    _l("selo-raro", GoodCategory.COLLECTIBLE, "Selo postal raro do Império", "Certificado e moldura de proteção.", "12500", "Filatelia", "GOOD"),
]
CATALOG_BY_KEY = {l.key: l for l in CATALOG}
EPOCH = date(2026, 11, 1)


def month_index(month: date) -> int:
    return (month.year - EPOCH.year) * 12 + (month.month - EPOCH.month)


# ------------------------------------------------------------------ construir imóveis (prazos reais)
@dataclass(frozen=True)
class BuildPlan:
    key: str
    category: GoodCategory
    name: str
    property_type: str
    area_m2: Decimal
    bedrooms: int | None
    cost_m2: Decimal           # custo de construção por m²
    land: Decimal              # terreno de referência (multiplicado pela cidade)
    months: int                # prazo da obra


BUILD_PLANS: dict[str, BuildPlan] = {p.key: p for p in [
    BuildPlan("casa-popular", GoodCategory.RESIDENTIAL, "Casa popular (60 m²)", "house", Decimal(60), 2, Decimal(2600), Decimal(70000), 3),
    BuildPlan("casa-media", GoodCategory.RESIDENTIAL, "Casa de 3 quartos (120 m²)", "house", Decimal(120), 3, Decimal(3400), Decimal(140000), 3),
    BuildPlan("sobrado", GoodCategory.RESIDENTIAL, "Sobrado de alto padrão (220 m²)", "house", Decimal(220), 4, Decimal(5200), Decimal(320000), 4),
    BuildPlan("mansao", GoodCategory.RESIDENTIAL, "Mansão (450 m²)", "house", Decimal(450), 6, Decimal(8200), Decimal(900000), 6),
    BuildPlan("predio-aptos", GoodCategory.RESIDENTIAL, "Prédio de 8 apartamentos (800 m²)", "apartment", Decimal(800), None, Decimal(4300), Decimal(600000), 6),
    BuildPlan("loja", GoodCategory.COMMERCIAL, "Loja de rua (80 m²)", "commercial", Decimal(80), None, Decimal(3600), Decimal(180000), 3),
    BuildPlan("galpao", GoodCategory.COMMERCIAL, "Galpão comercial (600 m²)", "commercial", Decimal(600), None, Decimal(2400), Decimal(420000), 5),
]}
BUILD_CITIES: dict[str, tuple[str, Decimal]] = {
    "sp": ("São Paulo, SP", Decimal("1.60")), "rj": ("Rio de Janeiro, RJ", Decimal("1.50")), "bh": ("Belo Horizonte, MG", Decimal("1.10")),
    "cwb": ("Curitiba, PR", Decimal("1.05")), "flo": ("Florianópolis, SC", Decimal("1.30")), "poa": ("Porto Alegre, RS", Decimal("1.00")),
    "interior": ("Interior", Decimal("0.60")),
}
CLOSING_MONTHS_CASH = 1            # compra à vista: escritura e registro levam ~1 mês
CLOSING_MONTHS_FINANCED = 2        # financiada: análise do banco + escritura levam ~2 meses


def build_quote(plan_key: str, city_key: str) -> dict:
    plan, (city, mult) = BUILD_PLANS[plan_key], BUILD_CITIES[city_key]
    construction = quantize_money(plan.area_m2 * plan.cost_m2)
    land = quantize_money(plan.land * mult)
    return {"plan": plan, "city": city, "construction": construction, "land": land, "total": quantize_money(construction + land), "months": plan.months}
