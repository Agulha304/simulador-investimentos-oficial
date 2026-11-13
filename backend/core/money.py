"""Utilitários de precisão financeira.

Regra do projeto: todo cálculo interno usa Decimal. Valores vindos de APIs
externas (float/str/int) entram pelo `to_decimal`, que passa por `str()` para
não herdar o erro binário do float.
"""
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, InvalidOperation, getcontext

getcontext().prec = 38  # alinhado ao maior Numeric usado no banco

# Escalas de armazenamento (casas decimais)
MONEY_PLACES = Decimal("0.01")              # reais
PRICE_PLACES = Decimal("0.0000000001")      # 10 casas: cotações e câmbio
QUANTITY_PLACES = Decimal("0.000000000000000001")  # 18 casas: cripto fracionada

# Tipos de coluna (precision, scale) — usados nos models
MONEY_COL = (20, 2)
PRICE_COL = (28, 10)
QUANTITY_COL = (38, 18)


class MoneyError(ValueError):
    pass


def to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or value is None:
        raise MoneyError(f"valor numérico inválido: {value!r}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MoneyError(f"valor numérico inválido: {value!r}") from exc
    if not result.is_finite():
        raise MoneyError(f"valor não finito: {value!r}")
    return result


def quantize_money(value: Decimal) -> Decimal:
    """Arredondamento bancário para centavos."""
    return to_decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_EVEN)


def quantize_price(value: Decimal) -> Decimal:
    return to_decimal(value).quantize(PRICE_PLACES, rounding=ROUND_HALF_EVEN)


def quantize_quantity(value: Decimal) -> Decimal:
    """Quantidades são truncadas: nunca compramos mais do que o dinheiro paga."""
    return to_decimal(value).quantize(QUANTITY_PLACES, rounding=ROUND_DOWN)
