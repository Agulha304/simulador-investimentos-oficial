"""Cálculo de financiamentos (Price e SAC). Funções puras, sem banco.

A soma das amortizações é SEMPRE exatamente o principal (a última parcela absorve o resto do arredondamento).
"""
from dataclasses import dataclass
from decimal import Decimal

from backend.core.money import quantize_money
from backend.models import AmortizationSystem

ONE = Decimal(1)


@dataclass(frozen=True)
class Row:
    number: int
    payment: Decimal
    interest: Decimal
    amortization: Decimal
    balance_after: Decimal


def monthly_rate(annual_pct: Decimal) -> Decimal:
    """Taxa mensal equivalente a uma taxa efetiva anual (juros compostos)."""
    return (ONE + annual_pct / 100) ** (ONE / 12) - ONE


def schedule(principal: Decimal, annual_pct: Decimal, term: int, system: AmortizationSystem) -> list[Row]:
    if principal <= 0 or term <= 0:
        raise ValueError("principal e prazo devem ser positivos")
    i = monthly_rate(annual_pct)
    balance = quantize_money(principal)
    rows: list[Row] = []
    if system == AmortizationSystem.PRICE:
        pmt = principal / term if i == 0 else principal * i / (ONE - (ONE + i) ** (-term))
    else:
        const_amort = quantize_money(principal / term)
    for n in range(1, term + 1):
        interest = quantize_money(balance * i)
        if n == term:
            amort = balance                                   # última parcela zera o saldo
        elif system == AmortizationSystem.PRICE:
            amort = quantize_money(pmt) - interest
        else:
            amort = const_amort
        amort = min(amort, balance)
        balance = quantize_money(balance - amort)
        rows.append(Row(n, quantize_money(amort + interest), interest, amort, balance))
    return rows
