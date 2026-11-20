"""Impostos brasileiros sobre bens (valores de referência, simplificados): ITBI, registro, IPTU, IPVA, IR sobre aluguel,
ISS da hospedagem por temporada e imposto de renda sobre o ganho de capital na venda.

As alíquotas variam por cidade e mudam com a lei; aqui são ordens de grandeza realistas e configuráveis neste arquivo.
"""
from decimal import Decimal

from backend.core.money import quantize_money
from backend.models import GoodCategory, REAL_ESTATE

D = Decimal
# ITBI por cidade (% do valor); cidades sem entrada usam o padrão
ITBI_BY_CITY = {"São Paulo": "3.0", "Rio de Janeiro": "3.0", "Belo Horizonte": "3.0", "Curitiba": "2.7", "Porto Alegre": "3.0",
                "Florianópolis": "2.0", "Campinas": "3.0", "Salvador": "3.0", "Fortaleza": "2.0", "Recife": "3.0", "Gramado": "2.0",
                "Brasília": "3.0", "Goiânia": "2.0"}
ITBI_DEFAULT = D("2.0")
REGISTRY_PCT = D("1.0")                  # escritura + registro em cartório
VEHICLE_TRANSFER_PCT = D("1.5")          # transferência, vistoria e despachante
IPTU_BY_CITY = {"São Paulo": "1.0", "Rio de Janeiro": "1.2", "Belo Horizonte": "1.0", "Curitiba": "0.9", "Porto Alegre": "1.0",
                "Florianópolis": "0.7", "Salvador": "1.0", "Recife": "1.1", "Fortaleza": "0.9"}
IPTU_DEFAULT = D("0.8")                   # % do valor por ano
ISS_STAY_PCT = D("3.0")                  # ISS da hospedagem de temporada
CAP_GAINS_TIERS = ((D("5000000"), D("15")), (D("10000000"), D("17.5")), (D("30000000"), D("20")), (None, D("22.5")))
SOLE_PROPERTY_EXEMPT_UP_TO = D("440000")  # imóvel único residencial até este valor: isento
MOVABLE_EXEMPT_UP_TO = D("35000")         # venda de bens (não imóveis) até este valor no mês: isenta
# carnê-leão (IR progressivo mensal sobre aluguéis): (limite, alíquota %, parcela a deduzir)
RENT_TABLE = ((D("2259.20"), D("0"), D("0")), (D("2826.65"), D("7.5"), D("169.44")), (D("3751.05"), D("15"), D("381.44")),
              (D("4664.68"), D("22.5"), D("662.77")), (None, D("27.5"), D("896.00")))


def city_of(location: str | None) -> str:
    return (location or "").split(",")[0].strip()


def itbi_rate(location: str | None) -> Decimal:
    return D(ITBI_BY_CITY.get(city_of(location), ITBI_DEFAULT))


def iptu_rate(location: str | None) -> Decimal:
    return D(IPTU_BY_CITY.get(city_of(location), IPTU_DEFAULT))


def purchase_taxes(category: GoodCategory, price: Decimal, location: str | None) -> list[tuple[str, Decimal, Decimal]]:
    """[(nome, alíquota %, valor)] pagos na compra."""
    q = quantize_money
    if category in REAL_ESTATE:
        r = itbi_rate(location)
        return [("ITBI", r, q(price * r / 100)), ("Escritura e registro", REGISTRY_PCT, q(price * REGISTRY_PCT / 100))]
    if category in (GoodCategory.CAR, GoodCategory.MOTORCYCLE):
        return [("Transferência e vistoria", VEHICLE_TRANSFER_PCT, q(price * VEHICLE_TRANSFER_PCT / 100))]
    return []


def rent_income_tax(monthly_rent: Decimal) -> Decimal:
    """IR mensal (carnê-leão) sobre o total de aluguéis recebidos no mês."""
    base = D(monthly_rent)
    for limit, rate, deduction in RENT_TABLE:
        if limit is None or base <= limit:
            return max(quantize_money(base * rate / 100 - deduction), D("0.00"))
    return D("0.00")


def capital_gains_tax(category: GoodCategory, sale_price: Decimal, acquisition_cost: Decimal, *, sole_property: bool) -> tuple[Decimal, str]:
    """(imposto, explicação) sobre o ganho de capital da venda."""
    gain = D(sale_price) - D(acquisition_cost)
    if gain <= 0:
        return D("0.00"), "sem ganho de capital: sem imposto"
    if category in REAL_ESTATE:
        if category == GoodCategory.RESIDENTIAL and sole_property and sale_price <= SOLE_PROPERTY_EXEMPT_UP_TO:
            return D("0.00"), "imóvel único até R$ 440 mil: isento"
        tax, prev = D("0.00"), D("0")
        for limit, rate in CAP_GAINS_TIERS:
            top = gain if limit is None else min(gain, limit)
            if top > prev:
                tax += (top - prev) * rate / 100
            prev = top if limit is None else limit
            if limit is None or gain <= limit:
                break
        return quantize_money(tax), "IR sobre ganho de capital (15% a 22,5%)"
    if sale_price <= MOVABLE_EXEMPT_UP_TO:
        return D("0.00"), "venda de bens até R$ 35 mil no mês: isenta"
    return quantize_money(gain * D("15") / 100), "IR sobre ganho de capital (15%)"
