import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { StatCard } from "../components/StatCard";
import { api, type PortfolioSummary } from "../services/api";
import { CLASS_LABEL, fmtBRL, fmtMoney, fmtPct, fmtQty, trend } from "../lib/format";

export function PortfolioPage() {
  const [data, setData] = useState<PortfolioSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => { api.portfolio().then(setData).catch((e: Error) => setError(e.message)); }, []);
  useEffect(load, [load]);

  async function deposit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await api.deposit(amount.replace(",", ".")); setAmount(""); load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Erro"); }
    finally { setBusy(false); }
  }

  if (!data) return error ? <div className="alert">{error}</div> : <div className="muted">Carregando…</div>;

  return (
    <div className="page">
      <header className="page-head"><h1>Carteira</h1></header>
      <section className="stats-grid">
        <StatCard label="Patrimônio" value={fmtBRL(data.total_equity_brl)} emphasis />
        <StatCard label="Saldo disponível" value={fmtBRL(data.cash_balance)} />
        <StatCard label="Posições (valor atual)" value={fmtBRL(data.market_value_brl)} sub={`custo ${fmtBRL(data.invested_brl)}`} />
        <StatCard label="Renda fixa (líquido est.)" value={fmtBRL(data.fixed_income_value_brl)} sub={`aplicado ${fmtBRL(data.fixed_income_invested_brl)}`} />
        <StatCard label="Lucro / prejuízo" value={fmtBRL(data.pnl_brl)} sub={fmtPct(data.pnl_pct)} tone={trend(data.pnl_brl)} />
      </section>

      <section className="card">
        <h2>Posições</h2>
        {data.holdings.length === 0 ? <div className="empty">Nenhuma posição. Use a busca para encontrar um ativo.</div> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Ativo</th><th className="r">Qtd.</th><th className="r">Preço médio</th><th className="r">Preço atual</th><th className="r">Valor atual</th><th className="r">Resultado</th><th className="r">Stop Loss</th><th className="r">Take Profit</th></tr></thead>
            <tbody>{data.holdings.map((h) => (
              <tr key={h.asset.id}>
                <td><Link to={`/ativo/${h.asset.id}`}><b>{h.asset.symbol}</b></Link> <span className="tag">{CLASS_LABEL[h.asset.asset_class]}</span></td>
                <td className="r num">{fmtQty(h.quantity)}</td>
                <td className="r num">{fmtBRL(h.avg_price_brl)}</td>
                <td className="r num">{h.current_price_brl ? fmtBRL(h.current_price_brl) : <span className="tone-warn">indisp.</span>}</td>
                <td className="r num">{fmtBRL(h.market_value_brl)}</td>
                <td className={`r num tone-${trend(h.pnl_brl)}`}>{fmtBRL(h.pnl_brl)} ({fmtPct(h.pnl_pct)})</td>
                <td className="r num tone-down">{h.stop_loss ? fmtMoney(h.stop_loss, h.asset.currency) : <span className="muted">—</span>}</td>
                <td className="r num tone-up">{h.take_profit ? fmtMoney(h.take_profit, h.asset.currency) : <span className="muted">—</span>}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </section>

      <form className="card inline-form" onSubmit={deposit}>
        <h2>Depósito virtual</h2>
        <p className="muted small">Adicione mais saldo fictício para continuar praticando.</p>
        <div className="row-gap">
          <input inputMode="decimal" placeholder="Valor em R$" value={amount} onChange={(e) => setAmount(e.target.value)} required />
          <button className="btn primary" disabled={busy}>Depositar</button>
        </div>
        {error && <div className="alert">{error}</div>}
      </form>
    </div>
  );
}
