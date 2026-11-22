"""Fornecedores das empresas (Empresas v2, fase 4): ofertas, negociação de preço e falha de entrega.

Tudo aqui é PURO e determinístico (sem banco, sem `random`), no mesmo estilo de `company_team`: os sorteios usam `hash01` com a
semente da partida, o id da empresa, o mês e a categoria. O `id` do fornecedor é um token (mês-categoria-índice): o servidor sempre
RECALCULA a oferta a partir do token, então o cliente nunca informa preço de lista, volume ou confiabilidade.

Decisões (ver também docs/EMPRESAS_V2.md, fase 4):
  * UM contrato ATIVO por (empresa, categoria): o volume vem do `max_units_month` do contrato; para mais volume, encerre e contrate
    outro (multa pequena se faltar menos de `MIN_TENURE_MONTHS` meses de casa).
  * preço de lista = preço de referência da categoria x índice de preços da economia (`supplier_mult`) x fator do fornecedor
    (0,92 a 1,06); piso de negociação = 85% a 100% da lista, mais baixo com relevância alta e com volume maior.
  * confiabilidade r (0,84 a 0,99): em cada mês o fornecedor falha com probabilidade (1 - r), de forma determinística por
    (semente, fornecedor, mês); na falha entrega só 30% a 70% do pedido (ou limita a capacidade do mês, nos serviços).
"""
import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.services import company_rules as rules
from backend.services.goods_rules import hash01

D = Decimal

OFFERS_MIN, OFFERS_SPAN = 3, 3                  # 3 a 5 fornecedores por busca
PRICE_FACTOR_MIN, PRICE_FACTOR_SPAN = 0.92, 0.14
FLOOR_BASE_MIN, FLOOR_BASE_SPAN = 0.85, 0.15     # piso base: 85% a 100% da lista
FLOOR_RELEVANCE_BONUS = 0.05                     # relevância 100 abaixa o piso em até 5 pontos
FLOOR_VOLUME_BONUS = 0.03                        # contratar todo o volume do fornecedor abaixa mais 3 pontos
FLOOR_MIN = 0.80
COUNTER_RATIO = D("0.92")                        # proposta >= 92% do mínimo aceito recebe contraproposta; abaixo recusa
MIN_ORDER_SHARE = (0.02, 0.06)                   # pedido mínimo = 2% a 6% do volume máximo que o fornecedor aguenta
VOLUME_RANGE = (0.60, 1.60)                      # volume máximo do fornecedor = 0,6x a 1,6x o consumo no teto de produção
RELIABILITY_MIN, RELIABILITY_SPAN = 0.84, 0.15
CONTRACT_TERM_MONTHS = 6
MIN_TENURE_MONTHS = 3                            # encerrar antes de 3 meses: multa de 2 pedidos mínimos
EARLY_END_FINE_ORDERS = D("2")
FAIL_DELIVERY_MIN, FAIL_DELIVERY_SPAN = 0.30, 0.40
DEFAULT_SUPPLIER_NAME = "Fornecedor padrão"
DEFAULT_MAX_UNITS = D("9999999")
LEGACY_MIN_ORDER = D("1")

NAME_PARTS = {
    "carnes": ("Frigorífico", "Açougue Atacadista", "Pescados"),
    "horti": ("Hortifruti", "Central de Abastecimento", "Sítio"),
    "bebidas": ("Distribuidora de Bebidas", "Bebidas", "Atacado de Bebidas"),
    "embalagens": ("Embalagens", "Descartáveis", "Plásticos e Papéis"),
    "graos": ("Torrefação", "Cafeicultura", "Cafés Especiais"),
    "laticinios": ("Laticínios", "Padaria Industrial", "Cooperativa de Leite"),
    "confeccoes": ("Confecções", "Atacado de Moda", "Malharia"),
    "acessorios": ("Acessórios", "Bijuterias e Cia", "Importadora"),
    "secos": ("Atacadista", "Distribuidora de Alimentos", "Armazém"),
    "horti_frios": ("Hortifruti e Frios", "Entreposto", "Frios e Laticínios"),
    "limpeza": ("Higiene e Limpeza", "Distribuidora de Limpeza", "Produtos de Limpeza"),
    "materia_prima": ("Metalúrgica", "Química", "Indústria de Base"),
    "componentes": ("Componentes", "Eletrônica", "Peças Industriais"),
    "insumos": ("Insumos Industriais", "Lubrificantes e Cia", "Suprimentos"),
    "cimento": ("Cimento", "Depósito de Construção", "Areial e Pedreira"),
    "aco": ("Aço", "Ferragens", "Siderúrgica"),
    "acabamentos": ("Revestimentos", "Cerâmica", "Acabamentos"),
    "pecas": ("Autopeças", "Distribuidora de Peças", "Peças e Fluidos"),
    "ferramentas": ("Ferramentas", "Casa do Mecânico", "Consumíveis"),
    "combustivel": ("Posto", "Distribuidora de Combustíveis", "Petro"),
    "pneus": ("Pneus", "Centro de Pneus", "Borracharia Atacadista"),
}
NAME_TAILS = ("Boa Vista", "Santa Clara", "Nova Era", "Brasil Central", "do Vale", "Rio Verde", "Planalto", "São Jorge", "Litoral Sul",
              "Três Irmãos", "Ouro Fino", "Minas Gerais", "Paulista", "Serra Azul", "Estrela", "Atlântico", "Cruzeiro", "Mantiqueira",
              "Pampa", "Sertão", "União", "Aurora", "Horizonte", "Bandeirantes")


@dataclass(frozen=True)
class SupplierOffer:
    id: str
    category: str
    name: str
    unit_price: Decimal               # preço de lista por unidade de compra
    reference_price: Decimal          # preço de referência do segmento (sem a economia)
    min_monthly_order: Decimal        # pedido mínimo (unidades por compra)
    max_units_month: Decimal          # volume que o fornecedor aguenta por mês
    reliability: float
    lead_days: int
    floor_base: float                 # piso base de negociação (fração da lista)


def make_token(ref: date, category: str, idx: int) -> str:
    return f"{ref:%Y%m}-{category}-{idx}"


def parse_token(token: str) -> tuple[str, str, int]:
    """(AAAAMM, categoria, índice). ValueError se o token for inválido."""
    try:
        ym, category, tail = token.split("-")
        if len(ym) != 6 or not ym.isdigit() or not tail.isdigit() or not category:
            raise ValueError
        return ym, category, int(tail)
    except ValueError:
        raise ValueError("fornecedor inválido") from None


def offer_count(seed: int, company_id: int, ref: date, category: str) -> int:
    return OFFERS_MIN + int(hash01(seed, "sup-n", company_id, f"{ref:%Y-%m}", category) * OFFERS_SPAN)


def _money2(v: Decimal) -> Decimal:
    return v.quantize(D("0.01"))


def build_offer(seed: int, company_id: int, ref: date, seg: rules.Segment, cat: rules.SupplyCategory, idx: int, *, size: rules.CompanySize,
                units: int, capacity_level: int, price_mult: Decimal = D(1)) -> SupplierOffer:
    def h(tag: str) -> float:
        return hash01(seed, "sup", tag, company_id, f"{ref:%Y-%m}", cat.key, idx)

    parts = NAME_PARTS.get(cat.key, ("Fornecedor",))
    name = f"{parts[int(h('n1') * len(parts))]} {NAME_TAILS[int(h('n2') * len(NAME_TAILS))]}"
    pf = PRICE_FACTOR_MIN + PRICE_FACTOR_SPAN * h("price")
    price = max(_money2(cat.ref_price * price_mult * D(str(round(pf, 4)))), D("0.01"))
    consume = rules.production_ceiling(seg, size, units, capacity_level) * float(cat.per_sale * (1 + cat.waste_pct / 100))
    max_units = D(max(1, int(consume * (VOLUME_RANGE[0] + (VOLUME_RANGE[1] - VOLUME_RANGE[0]) * h("vol")))))
    share = MIN_ORDER_SHARE[0] + (MIN_ORDER_SHARE[1] - MIN_ORDER_SHARE[0]) * h("min")
    min_order = D(max(1, int(float(max_units) * share)))
    # fornecedor barato tende a ser menos confiável
    reliability = round(RELIABILITY_MIN + RELIABILITY_SPAN * (0.5 * ((pf - PRICE_FACTOR_MIN) / PRICE_FACTOR_SPAN) + 0.5 * h("rel")), 3)
    return SupplierOffer(
        id=make_token(ref, cat.key, idx), category=cat.key, name=name, unit_price=price, reference_price=cat.ref_price,
        min_monthly_order=min_order, max_units_month=max_units, reliability=reliability, lead_days=2 + int(h("lead") * 12),
        floor_base=FLOOR_BASE_MIN + FLOOR_BASE_SPAN * h("floor"))


def search(seed: int, company_id: int, ref: date, seg: rules.Segment, category: str, *, size: rules.CompanySize, units: int,
           capacity_level: int, price_mult: Decimal = D(1)) -> list[SupplierOffer]:
    cat = seg.supply(category)                                   # KeyError se a categoria não existir
    n = offer_count(seed, company_id, ref, category)
    return [build_offer(seed, company_id, ref, seg, cat, i, size=size, units=units, capacity_level=capacity_level, price_mult=price_mult)
            for i in range(n)]


def resolve_token(seed: int, company_id: int, ref: date, token: str, seg: rules.Segment, *, size: rules.CompanySize, units: int,
                  capacity_level: int, price_mult: Decimal = D(1)) -> SupplierOffer:
    """Recalcula a oferta a partir do token. ValueError se for de outro mês, de outra categoria ou não existir."""
    ym, category, idx = parse_token(token)
    if ym != f"{ref:%Y%m}":
        raise ValueError("a lista de fornecedores é de outro mês: pesquise novamente")
    try:
        cat = seg.supply(category)
    except KeyError:
        raise ValueError("categoria inexistente neste segmento") from None
    if idx >= offer_count(seed, company_id, ref, category):
        raise ValueError("fornecedor inexistente")
    return build_offer(seed, company_id, ref, seg, cat, idx, size=size, units=units, capacity_level=capacity_level, price_mult=price_mult)


# ------------------------------------------------------------------ negociação

@dataclass(frozen=True)
class Deal:
    status: str                       # ACCEPTED | COUNTER | REFUSED
    message: str
    minimum_price: Decimal            # menor preço que o fornecedor aceita (nestas condições)
    counter_offer: Decimal | None = None
    price: Decimal | None = None      # preço do contrato (se aceito)

    @property
    def accepted(self) -> bool:
        return self.status == "ACCEPTED"


def floor_fraction(offer: SupplierOffer, relevance: float, volume: Decimal) -> float:
    """Piso do fornecedor (fração do preço de lista): base de 85% a 100%, menos até 5 pontos com relevância alta e até 3 pontos
    com o volume contratado (fração do que ele aguenta); nunca abaixo de 80%."""
    share = min(1.0, float(volume / offer.max_units_month)) if offer.max_units_month > 0 else 0.0
    f = offer.floor_base - FLOOR_RELEVANCE_BONUS * max(0.0, min(100.0, relevance)) / 100 - FLOOR_VOLUME_BONUS * share
    return max(FLOOR_MIN, min(1.0, f))


def minimum_price(offer: SupplierOffer, relevance: float, volume: Decimal) -> Decimal:
    return D(math.ceil(float(offer.unit_price) * floor_fraction(offer, relevance, volume) * 100 - 1e-9)) / 100


def evaluate(offer: SupplierOffer, price: Decimal, relevance: float, volume: Decimal) -> Deal:
    """Aceita se o preço >= piso; contrapõe o piso se a proposta ficou até 8% abaixo dele; recusa abaixo disso (o fornecedor
    fica indisponível no mês). Proposta acima da lista fecha na LISTA (ninguém paga mais do que o anunciado)."""
    required = max(minimum_price(offer, relevance, volume), D("0.01"))
    if price >= required:
        final = min(price, offer.unit_price)
        return Deal("ACCEPTED", f"{offer.name} aceitou fornecer a {final} por unidade.", required, price=final)
    if price / required >= COUNTER_RATIO:
        return Deal("COUNTER", f"{offer.name} não aceitou {price}, mas fecha por {required} por unidade.", required, required)
    return Deal("REFUSED", f"{offer.name} recusou: a proposta ficou muito abaixo do que ele pratica. Não está mais disponível neste mês.",
                required)


# ------------------------------------------------------------------ entrega

def failure_probability(reliability: float) -> float:
    return round(1.0 - float(reliability), 4)


def delivery_factor(seed: int, company_id: int, supplier_id: int, ref: date, reliability: float) -> float:
    """1.0 = entrega normal. Com probabilidade (1 - confiabilidade) o fornecedor falha no mês e entrega só 30% a 70% do que foi
    pedido (determinístico por semente, empresa, contrato e mês: repetir a mesma compra dá o mesmo resultado)."""
    ym = f"{ref:%Y-%m}"
    if hash01(seed, "deliver", company_id, supplier_id, ym) < failure_probability(reliability):
        return round(FAIL_DELIVERY_MIN + FAIL_DELIVERY_SPAN * hash01(seed, "deliver-qty", company_id, supplier_id, ym), 3)
    return 1.0
