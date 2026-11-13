import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { StatCard } from "../components/StatCard";
import {
  api, type FiIndexes, type FiInvestment, type FiProduct, type FiSimulation, type PortfolioSummary,
} from "../services/api";
import {
  FI_STATUS_LABEL, FI_TYPE_LABEL, FREQ_LABEL, LIQUIDITY_LABEL, RISK_LABEL, fmtBRL, fmtDay, fmtPct, trend,
} from "../lib/format";

const TYPE_FILTERS = [
  { id: "", label: "Todos" }, { id: "TESOURO", label: "Tesouro Direto" }, { id: "CDB", label: "CDB" }, { id: "LCI", label: "LCI" },
  { id: "LCA", label: "LCA" }, { id: "CRI", label: "CRI" }, { id: "CRA", label: "CRA" }, { id: "DEBENTURE", label: "Debêntures" },
];

export function FixedIncomePage() {
  const [tab, setTab] = useState<"products" | "mine">("products");
  const [products, setProducts] = useState<FiProduct[] | null>(null);
  const [mine, setMine] = useState<FiInvestment[] | null>(null);
  const [indexes, setIndexes] = useState<FiIndexes | null>(null);
  const [pf, setPf] = useState<PortfolioSummary | null>(null);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<FiProduct | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadMine = useCallback(() => {
    api.fiInvestments().then(setMine).catch((e: Error) => setError(e.message));
    api.portfolio().then(setPf).catch(() => undefined);
  }, []);
  useEffect(() => {
    api.fiProducts().then(setProducts).catch((e: Error) => setError(e.message));
    api.fiIndexes().then(setIndexes).catch(() => undefined);
    loadMine();
    api.fiRefresh().then((r) => { if (r.refreshed) api.fiProducts().then(setProducts).catch(() => undefined); }).catch(() => undefined);
  }, [loadMine]);

  const shown = useMemo(() => (products ?? []).filter((p) =>
    !filter || (filter === "TESOURO" ? p.product_type.startsWith("TESOURO") : p.product_type === filter)), [products, filter]);
  const active = (mine ?? []).filter((m) => m.status === "ACTIVE");

  return (
    <div className="page">
      <header className="page-head"><div><h1>Renda Fixa</h1><p className="muted">Tesouro Direto, CDB, LCI, LCA, CRI, CRA e debêntures.</p></div></header>
      {error && <div className="alert">{error}</div>}

      <section className="stats-grid">
        <StatCard label="CDI (a.a.)" value={indexes ? `${indexes.cdi_annual.replace(".", ",")}%` : "…"} sub={indexes?.last_cdi_date ? `até ${fmtDay(indexes.last_cdi_date)}` : "dado de referência"} />
        <StatCard label="Selic (a.a.)" value={indexes ? `${indexes.selic_annual.replace(".", ",")}%` : "…"} />
        <StatCard label="IPCA (12 meses)" value={indexes ? `${indexes.ipca_12m.replace(".", ",")}%` : "…"} />
        <StatCard label="Aplicado em renda fixa" value={fmtBRL(pf?.fixed_income_invested_brl)} sub={`líquido estimado ${fmtBRL(pf?.fixed_income_value_brl)}`} emphasis />
      </section>

      <div className="seg compact tabs">
        <button className={tab === "products" ? "on" : ""} onClick={() => setTab("products")}>Produtos disponíveis</button>
        <button className={tab === "mine" ? "on" : ""} onClick={() => setTab("mine")}>Minhas aplicações{active.length ? ` (${active.length})` : ""}</button>
      </div>

      {tab === "products" && (
        <>
          <div className="chart-toolbar">
            {TYPE_FILTERS.map((f) => <button key={f.id} className={`tool${filter === f.id ? " on" : ""}`} onClick={() => setFilter(f.id)}>{f.label}</button>)}
          </div>
          <section className="card">
            {!products ? <div className="muted">Carregando…</div> : shown.length === 0 ? <div className="empty">Nenhum produto neste filtro.</div> : (
              <div className="table-wrap"><table>
                <thead><tr><th>Produto</th><th>Emissor</th><th className="r">Taxa</th><th>Vencimento</th><th>Liquidez</th><th>IR</th><th className="r">Mínimo</th><th /></tr></thead>
                <tbody>{shown.map((p) => (
                  <tr key={p.id}>
                    <td><b>{p.name}</b> {p.source === "SAMPLE" && <span className="tag sample" title="Oferta de exemplo: emissor fictício, taxa derivada do CDI/IPCA">exemplo</span>}
                      <div className="muted small">{FI_TYPE_LABEL[p.product_type] ?? p.product_type}</div></td>
                    <td className="muted">{p.issuer}</td>
                    <td className="r num tone-up">{p.rate_label}</td>
                    <td className="num">{fmtDay(p.maturity_date)}</td>
                    <td>{LIQUIDITY_LABEL[p.liquidity]}{p.grace_days ? ` (carência ${p.grace_days}d)` : ""}</td>
                    <td>{p.tax_regime === "EXEMPT" ? <span className="tag paid">isento</span> : "regressivo"}</td>
                    <td className="r num">{fmtBRL(p.min_investment_brl)}</td>
                    <td><button className="btn primary small" onClick={() => setSelected(p)}>Aplicar</button></td>
                  </tr>))}</tbody>
              </table></div>
            )}
          </section>
        </>
      )}

      {tab === "mine" && <MyInvestments rows={mine} onChanged={loadMine} />}
      {selected && <ProductModal product={selected} cash={pf?.cash_balance} onClose={() => setSelected(null)} onDone={() => { setSelected(null); loadMine(); setTab("mine"); }} />}
    </div>
  );
}

function ProductModal({ product: p, cash, onClose, onDone }: { product: FiProduct; cash?: string; onClose: () => void; onDone: () => void }) {
  const [amount, setAmount] = useState(String(Math.max(Number(p.min_investment_brl), 1000)));
  const [sim, setSim] = useState<FiSimulation | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const value = amount.replace(",", ".");

  useEffect(() => {
    if (!(Number(value) > 0)) { setSim(null); return; }
    const t = setTimeout(() => { api.fiSimulate(p.id, value).then(setSim).catch(() => setSim(null)); }, 350);
    return () => clearTimeout(t);
  }, [p.id, value]);

  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setMsg(null);
    try { await api.fiInvest(p.id, value); onDone(); }
    catch (err) { setMsg(err instanceof Error ? err.message : "Erro inesperado"); }
    finally { setBusy(false); }
  }

  return (
    <div className="modal-back" onMouseDown={onClose}>
      <form className="card modal" onMouseDown={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="row"><h2>{p.name}</h2><button type="button" className="link-btn" onClick={onClose}>fechar ✕</button></div>
        <p className="muted small" style={{ margin: 0 }}>{p.issuer} · {p.rate_label} · vence em {fmtDay(p.maturity_date)}</p>
        <dl className="facts">
          <div><dt>Liquidez</dt><dd>{LIQUIDITY_LABEL[p.liquidity]}{p.grace_days ? `, carência de ${p.grace_days} dias` : ""}{p.early_redemption ? "" : " (sem resgate antecipado)"}</dd></div>
          <div><dt>Pagamento de juros</dt><dd>{FREQ_LABEL[p.payment_frequency]}</dd></div>
          <div><dt>Tributação</dt><dd>{p.tax_regime === "EXEMPT" ? "Isento para pessoa física" : "IR regressivo (22,5% a 15%) e IOF até 30 dias"}</dd></div>
          <div><dt>Risco</dt><dd>{RISK_LABEL[p.risk_level]}{p.fgc_covered ? " · coberto pelo FGC (até R$ 250 mil)" : ""}</dd></div>
          {Number(p.secondary_discount_pct) > 0 && <div><dt>Venda antecipada</dt><dd>deságio de {p.secondary_discount_pct.replace(".", ",")}% no mercado secundário</dd></div>}
          {p.uses_mtm && <div><dt>Venda antecipada</dt><dd>a preço de mercado: pode render menos (ou mais) que o contratado</dd></div>}
        </dl>
        {p.description && <p className="muted small" style={{ margin: 0 }}>{p.description}</p>}
        <label>Valor a aplicar (R$) — mínimo {fmtBRL(p.min_investment_brl)}
          <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required />
        </label>
        <div className="muted small row"><span>Saldo disponível</span><span className="num">{fmtBRL(cash)}</span></div>
        {sim && (
          <div className="sim">
            <div className="row"><span>Líquido se mantido até o vencimento</span><b className="num tone-up">{fmtBRL(sim.total_net_brl)}</b></div>
            <div className="row muted small"><span>Rendimento líquido</span><span className={`num tone-${trend(sim.profit_net_brl)}`}>{fmtBRL(sim.profit_net_brl)}{sim.annualized_net_pct ? ` · ${fmtPct(sim.annualized_net_pct)} a.a.` : ""}</span></div>
            <div className="row muted small"><span>Imposto estimado</span><span className="num">{fmtBRL(sim.total_tax_brl)}</span></div>
            {sim.flows.length > 1 && <div className="muted small">Inclui {sim.flows.length - 1} pagamentos de juros. Próximo: {fmtDay(sim.flows[0].on)} ({fmtBRL(sim.flows[0].net)}).</div>}
            <p className="muted small" style={{ margin: "6px 0 0" }}>{sim.assumptions}</p>
          </div>
        )}
        {msg && <div className="alert">{msg}</div>}
        <button className="btn primary" disabled={busy}>{busy ? "Aplicando…" : "Confirmar aplicação"}</button>
      </form>
    </div>
  );
}

function MyInvestments({ rows, onChanged }: { rows: FiInvestment[] | null; onChanged: () => void }) {
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  async function redeem(r: FiInvestment) {
    if (!window.confirm(`Resgatar ${r.product.name}? Valor líquido estimado: ${fmtBRL(r.redeem_net_brl)}`)) return;
    setBusyId(r.id); setMsg(null);
    try { await api.fiRedeem(r.id); setMsg({ ok: true, text: "Resgate realizado." }); onChanged(); }
    catch (e) { setMsg({ ok: false, text: e instanceof Error ? e.message : "Erro" }); }
    finally { setBusyId(null); }
  }

  if (!rows) return <div className="muted">Carregando…</div>;
  if (rows.length === 0) return <div className="empty">Você ainda não tem aplicações em renda fixa.</div>;
  return (
    <section className="card">
      {msg && <div className={msg.ok ? "ok" : "alert"} style={{ marginBottom: 10 }}>{msg.text}</div>}
      <div className="table-wrap"><table>
        <thead><tr><th>Produto</th><th>Status</th><th>Aplicado em</th><th className="r">Aplicado</th><th className="r">Valor bruto</th><th className="r">IR est.</th><th className="r">Líquido</th><th className="r">Juros recebidos</th><th className="r">Resultado</th><th>Próximo</th><th /></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.id}>
            <td><b>{r.product.name}</b><div className="muted small">{r.product.rate_label} · vence {fmtDay(r.maturity_date)}{r.valuation_method === "MTM" ? " · a mercado" : ""}</div></td>
            <td><span className={`tag${r.status === "ACTIVE" ? " paid" : ""}`}>{FI_STATUS_LABEL[r.status]}</span></td>
            <td className="num">{fmtDay(r.applied_on)}</td>
            <td className="r num">{fmtBRL(r.principal_brl)}</td>
            <td className="r num">{fmtBRL(r.current_gross_brl)}</td>
            <td className="r num">{Number(r.estimated_tax_brl) > 0 ? fmtBRL(r.estimated_tax_brl) : "—"}</td>
            <td className="r num">{fmtBRL(r.estimated_net_brl)}</td>
            <td className="r num">{Number(r.interest_paid_net_brl) > 0 ? fmtBRL(r.interest_paid_net_brl) : "—"}</td>
            <td className={`r num tone-${trend(r.profit_net_brl)}`}>{fmtBRL(r.profit_net_brl)}</td>
            <td className="muted small">{r.next_event_date ? `${r.next_event_kind === "COUPON" ? "juros" : "vencimento"} ${fmtDay(r.next_event_date)}` : r.closed_on ? `encerrada ${fmtDay(r.closed_on)}` : "—"}</td>
            <td>{r.status === "ACTIVE" && (
              <button className="btn ghost small" disabled={!r.can_redeem || busyId === r.id} title={r.redeem_block_reason ?? "Resgatar"} onClick={() => redeem(r)}>
                {busyId === r.id ? "…" : "Resgatar"}
              </button>)}
            </td>
          </tr>))}</tbody>
      </table></div>
      <p className="muted small">O valor líquido é uma estimativa do resgate hoje, já com imposto. Passe o mouse em "Resgatar" quando estiver desabilitado para ver o motivo.</p>
    </section>
  );
}
