import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type DividendItem, type Transaction } from "../services/api";
import { KIND_LABEL, SOURCE_LABEL, STATUS_LABEL, TX_LABEL, fmtBRL, fmtDate, fmtDay, fmtMoney, fmtQty, trend } from "../lib/format";

const FILTERS = [
  { id: "ALL", label: "Tudo" }, { id: "BUY", label: "Compras" }, { id: "SELL", label: "Vendas" },
  { id: "DIVIDEND", label: "Proventos" }, { id: "FIXED", label: "Renda fixa" },
];
// o histórico mostra só operações de INVESTIMENTO: ficam de fora depósitos, saques e movimentos do orçamento
const INVEST_TYPES = new Set(["BUY", "SELL", "DIVIDEND", "FIXED_INCOME_APPLY", "FIXED_INCOME_REDEEM", "FIXED_INCOME_COUPON", "FIXED_INCOME_MATURITY"]);

export function HistoryPage() {
  const [tab, setTab] = useState<"tx" | "div">("tx");
  const [filter, setFilter] = useState("ALL");
  const [txs, setTxs] = useState<Transaction[] | null>(null);
  const [divs, setDivs] = useState<DividendItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.transactions(500).then(setTxs).catch((e: Error) => setError(e.message));
    api.dividends().then(setDivs).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  async function sync() {
    setBusy(true); setInfo(null); setError(null);
    try {
      const r = await api.syncDividends();
      setInfo(`${r.new_rights} novo(s) direito(s) reconhecido(s), ${r.paid} pagamento(s) efetuado(s).`);
      load();
    } catch (e) { setError(e instanceof Error ? e.message : "Erro"); }
    finally { setBusy(false); }
  }

  const rows = (txs ?? []).filter((t) => INVEST_TYPES.has(t.type) && (filter === "ALL" || t.type === filter || (filter === "FIXED" && t.type.startsWith("FIXED_INCOME"))));

  return (
    <div className="page">
      <header className="page-head"><h1>Histórico de operações</h1></header>
      {error && <div className="alert">{error}</div>}
      <div className="seg compact tabs">
        <button className={tab === "tx" ? "on" : ""} onClick={() => setTab("tx")}>Transações</button>
        <button className={tab === "div" ? "on" : ""} onClick={() => setTab("div")}>Proventos e rendimentos</button>
      </div>

      {tab === "tx" && (
        <section className="card">
          <div className="chart-toolbar">
            {FILTERS.map((f) => <button key={f.id} className={`tool${filter === f.id ? " on" : ""}`} onClick={() => setFilter(f.id)}>{f.label}</button>)}
          </div>
          {!txs ? <div className="muted">Carregando…</div> : rows.length === 0 ? <div className="empty">Nenhuma transação.</div> : (
            <div className="table-wrap"><table>
              <thead><tr><th>Data</th><th>Tipo</th><th>Ativo</th><th className="r">Qtd.</th><th className="r">Preço (R$)</th><th className="r">Bruto</th><th className="r">Imposto</th><th className="r">Resultado</th><th className="r">Caixa</th><th className="r">Saldo</th><th>Origem</th></tr></thead>
              <tbody>{rows.map((t) => (
                <tr key={t.id} title={t.note ?? undefined}>
                  <td className="num">{fmtDate(t.created_at)}</td>
                  <td><span className="tag">{TX_LABEL[t.type] ?? t.type}</span></td>
                  <td>{t.asset ? <Link to={`/ativo/${t.asset.id}`}>{t.asset.symbol}</Link> : <span className="muted">{t.note ?? "—"}</span>}</td>
                  <td className="r num">{fmtQty(t.quantity)}</td>
                  <td className="r num">{t.unit_price_brl ? fmtBRL(t.unit_price_brl) : "—"}</td>
                  <td className="r num">{fmtBRL(t.gross_amount_brl)}</td>
                  <td className="r num">{Number(t.tax_brl) > 0 ? fmtBRL(t.tax_brl) : "—"}</td>
                  <td className={`r num tone-${trend(t.realized_pnl_brl)}`}>{t.realized_pnl_brl != null ? fmtBRL(t.realized_pnl_brl) : "—"}</td>
                  <td className={`r num tone-${trend(t.cash_amount_brl)}`}>{fmtBRL(t.cash_amount_brl)}</td>
                  <td className="r num">{fmtBRL(t.cash_balance_after)}</td>
                  <td className="muted small">{SOURCE_LABEL[t.source] ?? t.source}</td>
                </tr>))}</tbody>
            </table></div>
          )}
        </section>
      )}

      {tab === "div" && (
        <section className="card">
          <div className="chart-toolbar">
            <button className="btn primary small" disabled={busy} onClick={sync}>{busy ? "Consultando…" : "Atualizar proventos"}</button>
            {info && <span className="muted small">{info}</span>}
          </div>
          <p className="muted small">
            O direito vale para quem possuía o ativo antes da data EX. A data de pagamento é uma estimativa (a fonte informa só a data EX),
            e o crédito é feito automaticamente a cada 15 minutos.
          </p>
          {!divs ? <div className="muted">Carregando…</div> : divs.length === 0 ? <div className="empty">Nenhum provento reconhecido ainda.</div> : (
            <div className="table-wrap"><table>
              <thead><tr><th>Ativo</th><th>Tipo</th><th>Data EX</th><th>Pagamento</th><th className="r">Qtd.</th><th className="r">Valor/unid.</th><th>Status</th><th className="r">Bruto</th><th className="r">Imposto</th><th className="r">Líquido</th></tr></thead>
              <tbody>{divs.map((d) => (
                <tr key={d.id}>
                  <td><Link to={`/ativo/${d.asset.id}`}><b>{d.asset.symbol}</b></Link></td>
                  <td>{KIND_LABEL[d.kind]}</td>
                  <td className="num">{fmtDay(d.ex_date)}</td>
                  <td className="num">{fmtDay(d.pay_date)}{d.status === "PENDING" && d.pay_date_estimated ? <span className="muted small"> (est.)</span> : null}</td>
                  <td className="r num">{fmtQty(d.quantity)}</td>
                  <td className="r num">{fmtMoney(d.amount_per_unit, d.currency)}</td>
                  <td><span className={`tag${d.status === "PAID" ? " paid" : ""}`}>{STATUS_LABEL[d.status]}</span></td>
                  <td className="r num">{d.gross_brl ? fmtBRL(d.gross_brl) : <span className="muted">~ {fmtMoney(d.expected_gross_native, d.currency)}</span>}</td>
                  <td className="r num">{d.tax_brl && Number(d.tax_brl) > 0 ? fmtBRL(d.tax_brl) : "—"}</td>
                  <td className="r num tone-up">{d.net_brl ? fmtBRL(d.net_brl) : "—"}</td>
                </tr>))}</tbody>
            </table></div>
          )}
        </section>
      )}
    </div>
  );
}
