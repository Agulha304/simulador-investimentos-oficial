import { useEffect, useState } from "react";
import { StatCard } from "../components/StatCard";
import { api, type PortfolioSummary, type Transaction } from "../services/api";
import { useAuth } from "../services/auth";
import { fmtBRL, fmtDate, fmtPct, fmtQty, TX_LABEL, trend } from "../lib/format";

export function DashboardPage() {
  const { user } = useAuth();
  const [data, setData] = useState<PortfolioSummary | null>(null);
  const [txs, setTxs] = useState<Transaction[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.portfolio(), api.transactions(10)])
      .then(([p, t]) => { setData(p); setTxs(t); })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <div className="alert">Não foi possível carregar a carteira: {error}</div>;
  if (!data) return <div className="muted">Carregando carteira…</div>;

  const pnlTone = trend(data.pnl_brl);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Olá, {user?.name.split(" ")[0]}</h1>
          <p className="muted">{data.name}</p>
        </div>
      </header>

      <section className="stats-grid">
        <StatCard label="Patrimônio total" value={fmtBRL(data.total_equity_brl)} emphasis />
        <StatCard label="Saldo disponível" value={fmtBRL(data.cash_balance)} />
        <StatCard label="Ativos (valor atual)" value={fmtBRL(data.market_value_brl)} sub={`custo ${fmtBRL(data.invested_brl)}`} />
        <StatCard label="Renda fixa (líquido est.)" value={fmtBRL(data.fixed_income_value_brl)} sub={`aplicado ${fmtBRL(data.fixed_income_invested_brl)}`} />
        <StatCard label="Lucro / prejuízo" value={fmtBRL(data.pnl_brl)} sub={fmtPct(data.pnl_pct)} tone={pnlTone} />
      </section>

      <section className="card">
        <h2>Ativos da carteira</h2>
        {data.holdings.length === 0 ? (
          <div className="empty">Você ainda não possui ativos. A compra de ativos chega na próxima fase.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Ativo</th><th className="r">Qtd.</th><th className="r">Preço médio</th><th className="r">Valor atual</th><th className="r">Resultado</th></tr>
              </thead>
              <tbody>
                {data.holdings.map((h) => (
                  <tr key={h.asset.id}>
                    <td><b>{h.asset.symbol}</b> <span className="muted small">{h.asset.name}</span></td>
                    <td className="r num">{fmtQty(h.quantity)}</td>
                    <td className="r num">{fmtBRL(h.avg_price_brl)}</td>
                    <td className="r num">{fmtBRL(h.market_value_brl)}</td>
                    <td className={`r num tone-${trend(h.pnl_brl)}`}>{fmtBRL(h.pnl_brl)} ({fmtPct(h.pnl_pct)})</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>Movimentações recentes</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Data</th><th>Tipo</th><th>Descrição</th><th className="r">Valor</th><th className="r">Saldo após</th></tr>
            </thead>
            <tbody>
              {txs.map((t) => (
                <tr key={t.id}>
                  <td className="num">{fmtDate(t.created_at)}</td>
                  <td><span className="tag">{TX_LABEL[t.type] ?? t.type}</span></td>
                  <td>{t.asset ? t.asset.symbol : t.note ?? "—"}</td>
                  <td className={`r num tone-${trend(t.cash_amount_brl)}`}>{fmtBRL(t.cash_amount_brl)}</td>
                  <td className="r num">{fmtBRL(t.cash_balance_after)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
