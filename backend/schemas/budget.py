"""Schemas do orçamento mensal. Decimal sai como string no JSON (sem perda de precisão)."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from backend.models import EntryOrigin, FlowKind, Frequency, MonthStatus

Money = Field(gt=0, max_digits=20, decimal_places=2)


# ------------------------------------------------------------------ entrada

class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: FlowKind


class CategoryPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=60)
    active: bool | None = None


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: FlowKind
    category_id: int
    planned_amount: Decimal = Money
    recurring: bool = False
    frequency: Frequency = Frequency.MONTHLY
    end_month: str | None = Field(None, pattern=r"^\d{4}-\d{2}$")   # AAAA-MM


class ItemPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    category_id: int | None = None
    planned_amount: Decimal | None = Field(None, gt=0, max_digits=20, decimal_places=2)
    frequency: Frequency | None = None
    end_month: str | None = Field(None, pattern=r"^\d{4}-\d{2}$")
    clear_end_month: bool = False
    # True: vale a partir deste mês nas próximas ocorrências. False: só este mês.
    apply_to_future: bool = True


class EntryCreate(BaseModel):
    kind: FlowKind
    amount: Decimal = Money
    description: str = Field("", max_length=200)
    category_id: int | None = None
    budget_item_id: int | None = None
    entry_date: date | None = None
    idempotency_key: str | None = Field(None, min_length=8, max_length=100)


class MonthPatch(BaseModel):
    planned_investment: Decimal = Field(ge=0, max_digits=20, decimal_places=2)


class CloseRequest(BaseModel):
    ref_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    confirm: bool = False


# ------------------------------------------------------------------ saída

class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    kind: FlowKind
    active: bool
    is_default: bool


class ItemOut(BaseModel):
    id: int
    name: str
    kind: FlowKind
    category_id: int
    category_name: str
    planned_amount: Decimal
    realized: Decimal
    remaining: Decimal
    recurring: bool
    frequency: Frequency | None
    end_month: date | None
    entry_count: int
    capital: bool = False             # movimentação patrimonial (ex.: amortização)
    source: str | None = None         # gerado por um bem/financiamento (não editável aqui)


class CategoryTotalOut(BaseModel):
    category_id: int | None
    category_name: str
    kind: FlowKind
    planned: Decimal
    realized: Decimal
    remaining: Decimal


class AccountOut(BaseModel):
    id: int
    name: str
    kind: str
    balance: Decimal


class MonthSummaryOut(BaseModel):
    ref_month: date
    status: MonthStatus
    opening_balance: Decimal
    closing_balance: Decimal | None
    planned_investment: Decimal
    balance: Decimal                 # caixa atual (mês aberto) ou saldo final (fechado)
    planned_income: Decimal
    planned_expense: Decimal
    realized_income: Decimal
    realized_expense: Decimal
    forecast_income: Decimal         # valor previsto para o mês (planejado ou realizado, o maior)
    forecast_expense: Decimal
    remaining_income: Decimal        # planejado ainda não realizado
    remaining_expense: Decimal
    invested: Decimal
    result: Decimal                  # receitas − despesas realizadas
    projected_closing_balance: Decimal
    free_after_investment: Decimal   # saldo projetado − investimento planejado
    capital_in: Decimal = Decimal("0.00")     # movimentações patrimoniais (compra/venda de bens, amortizações)
    capital_out: Decimal = Decimal("0.00")
    items: list[ItemOut]
    by_category: list[CategoryTotalOut]


class ClosePreviewOut(BaseModel):
    ref_month: date
    next_month: date
    income: Decimal                  # realizado + recorrentes pendentes
    expense: Decimal
    invested: Decimal
    result: Decimal
    carried_balance: Decimal
    pending: list[str]               # nomes dos itens que serão lançados no fechamento
    shortfall: Decimal
    can_close: bool
    overdraft_needed: Decimal = Decimal("0.00")      # partidas: quanto vai para o saldo negativo (cheque especial)
    bankruptcy_risk: bool = False                  # o saldo negativo passaria do limite: falência
    overdraft_limit: Decimal = Decimal("100000.00")


class OverviewOut(BaseModel):
    account: AccountOut
    month: MonthSummaryOut
    close: ClosePreviewOut


class MonthRowOut(BaseModel):
    ref_month: date
    status: MonthStatus
    opening_balance: Decimal
    closing_balance: Decimal | None
    income: Decimal
    expense: Decimal
    invested: Decimal
    result: Decimal


class EntryOut(BaseModel):
    id: int
    kind: FlowKind
    amount: Decimal
    description: str
    category_id: int | None
    category_name: str | None
    entry_date: date
    ref_month: date
    origin: EntryOrigin
    budget_item_id: int | None
    reverses_id: int | None
    reversed: bool
    created_at: datetime
    capital: bool = False
    origin_ref: str | None = None
