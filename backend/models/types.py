from sqlalchemy import Enum as SAEnum, Numeric

from backend.core.money import MONEY_COL, PRICE_COL, QUANTITY_COL


def Money():  # noqa: N802
    return Numeric(*MONEY_COL, asdecimal=True)


def Price():  # noqa: N802
    return Numeric(*PRICE_COL, asdecimal=True)


def Quantity():  # noqa: N802
    return Numeric(*QUANTITY_COL, asdecimal=True)


def StrEnumType(enum_cls, name: str):  # noqa: N802
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )
