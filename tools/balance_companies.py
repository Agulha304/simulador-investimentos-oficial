"""Verificação de balanceamento das empresas (Empresas v2, fase 3a).

Simula N meses por segmento (porte pequeno, local padrão, preço de mercado, equipe sugerida + cargos obrigatórios em meio período)
com as MESMAS funções do fechamento mensal e imprime receita/lucro mês a mês e o mês de virada.

Uso (na raiz do projeto):
    .venv/bin/python tools/balance_companies.py                      # tabela-resumo dos 12 segmentos (36 meses, valor esperado)
    .venv/bin/python tools/balance_companies.py --segment CAFE       # mês a mês de um segmento
    .venv/bin/python tools/balance_companies.py --draw --seed 3      # com sorteio dos meses zerados (como no jogo)
    .venv/bin/python tools/balance_companies.py --regime PJ --marketing
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.models import CompanySegment, CompanySize, EmployeeRegime  # noqa: E402
from backend.services import company_balance as bal  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--months", type=int, default=36)
    ap.add_argument("--segment", help="chave do segmento (ex.: CAFE): imprime mês a mês")
    ap.add_argument("--size", default="SMALL", choices=[s.value for s in CompanySize])
    ap.add_argument("--regime", default="CLT", choices=[r.value for r in EmployeeRegime])
    ap.add_argument("--marketing", action="store_true", help="campanha de marketing ativa o tempo todo")
    ap.add_argument("--draw", action="store_true", help="sorteia os meses zerados (hash01) em vez do valor esperado")
    ap.add_argument("--seed", type=int, default=bal.SIM_SEED)
    a = ap.parse_args()
    kw = dict(size=CompanySize(a.size), regime=EmployeeRegime(a.regime), marketing=a.marketing, expected=not a.draw, seed=a.seed)
    if a.segment:
        r = bal.simulate(CompanySegment(a.segment), months=a.months, **kw)
        print(f"{r.segment}: capital mínimo {bal.brl(r.minimum_capital)} | caixa inicial {bal.brl(r.start_cash)} | custo fixo+folha {bal.brl(r.monthly_cost)}/mês")
        print(f"{'mês':>3} {'relev.':>6} {'rep.':>5} {'P(zero)':>7} {'vendas':>8} {'receita':>10} {'custos':>10} {'impostos':>9} {'regime':>7} {'lucro':>10} {'caixa':>11}")
        for m in r.rows:
            print(f"{m.month:>3} {m.relevance:6.1f} {m.reputation:5.0f} {m.zero_prob:7.2f} {m.sold:8.1f} {bal.brl(m.revenue):>10} "
                  f"{bal.brl(m.variable + m.fixed + m.payroll):>10} {bal.brl(m.taxes):>9} {m.tax_regime[:7]:>7} {bal.brl(m.profit):>10} {bal.brl(m.cash):>11}")
        print(f"mês de virada: {r.turn_month}")
        return
    print(f"{'segmento':<20} {'cap.mín.':>10} {'custo/mês':>10} {'rec.m6':>9} {'luc.m6':>9} {'rec.m12':>9} {'luc.m12':>9} "
          f"{'luc.m24':>9} {'luc.m36':>9} {'caixa mín.':>11} {'virada':>6} {'relev.m12/36':>12}")
    for r in bal.table(a.months, **kw):
        row = {m.month: m for m in r.rows}
        g = lambda n, attr: bal.brl(getattr(row[n], attr)) if n in row else "-"
        print(f"{r.segment:<20} {bal.brl(r.minimum_capital):>10} {bal.brl(r.monthly_cost):>10} {g(6, 'revenue'):>9} {g(6, 'profit'):>9} "
              f"{g(12, 'revenue'):>9} {g(12, 'profit'):>9} {g(24, 'profit'):>9} {g(36, 'profit'):>9} {bal.brl(r.min_cash):>11} "
              f"{str(r.turn_month or 'nunca'):>6} {row[min(12, a.months)].relevance:5.1f}/{row[a.months].relevance:5.1f}")


if __name__ == "__main__":
    main()
