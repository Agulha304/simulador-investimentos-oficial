import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PurchaseModal } from "../components/GoodsModals";
import { StatCard } from "../components/StatCard";
import { api, type Good, type GoodCategory, type Listing, type WealthOverview } from "../services/api";
import { CATEGORY_LABEL, GOOD_STATUS_LABEL, OCCUPANCY_LABEL, fmtBRL, fmtDay, trend } from "../lib/format";

const WealthSeriesChart = lazy(() => import("../components/charts/WealthCharts").then((m) => ({ default: m.WealthSeriesChart })));
const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
type Tab = "overview" | "mine" | "market";
const CATS = Object.keys(CATEGORY_LABEL) as GoodCategory[];

export function WealthPage() {
  const nav = useNavigate();
  const [tab, setTab] = useState<Tab>("overview");
  const [ov, setOv] = useState<WealthOverview | null>(null);
  const [goods, setGoods] = useState<Good[]>([]);
  const [cash, setCash] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [o, g, p] = await Promise.all([api.wealth(), api.myGoods(), api.portfolio()]);
      setOv(o); setGoods(g); setCash(p.cash_balance); setError(null);
    } catch (e) { setError(errMsg(e)); }
  }, []);
  useEffect(() => { void reload(); }, [reload]);

  if (error && !ov) return <div className="alert">Não foi possível carregar o patrimônio: {error}</div>;
  if (!ov) return <div className="muted">Carregando patrimônio…</div>;

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Patrimônio</h1><p className="muted">Imóveis, veículos e outros bens. Patrimônio não é saldo: um imóvel não vira dinheiro até ser vendido.</p></div>
      </header>
      {error && <div className="alert">{error}</div>}
      {notice && <div className="ok">{notice}</div>}
      <div className="seg compact tabs">
        <button className={tab === "overview" ? "on" : ""} onClick={() => setTab("overview")}>Visão geral</button>
        <button className={tab === "mine" ? "on" : ""} onClick={() => setTab("mine")}>Meus bens ({ov.count})</button>
        <button className={tab === "market" ? "on" : ""} onClick={() => setTab("market")}>Mercado de bens</button>
      </div>

      {tab === "overview" && (
        <>
          <section className="stats-grid">
            <StatCard label="Patrimônio em bens (líquido)" value={fmtBRL(ov.net_worth)} sub={`${ov.count} ${ov.count === 1 ? "bem" : "bens"}`} emphasis />
            <StatCard label="Valor de mercado atual" value={fmtBRL(ov.total_value)} sub={`custo de aquisição ${fmtBRL(ov.total_acquisition_cost)}`} />
            <StatCard label="Dívidas dos bens" value={fmtBRL(ov.debts)} sub={`parcelas do mês ${fmtBRL(ov.monthly_debt_service)}`} />
            <StatCard label="Receitas mensais dos bens" value={fmtBRL(ov.monthly_income)} sub={`recebido até hoje ${fmtBRL(ov.income_received_total)}`} tone="up" />
            <StatCard label="Despesas mensais dos bens" value={fmtBRL(ov.monthly_expense)} sub={`pago até hoje ${fmtBRL(ov.expense_paid_total)}`} />
            <StatCard label="Valorização não realizada" value={fmtBRL(ov.unrealized_result)} tone={trend(ov.unrealized_result)} sub="valor atual − custo de aquisição" />
          </section>
          <Suspense fallback={<div className="card muted">Carregando gráfico…</div>}><WealthSeriesChart series={ov.series} /></Suspense>
          <section className="card">
            <h2>Composição por categoria</h2>
            {ov.by_category.length === 0 ? <div className="empty">Você ainda não possui bens. Veja o Mercado de bens.</div> : (
              <div className="table-wrap"><table>
                <thead><tr><th>Categoria</th><th className="r">Quantidade</th><th className="r">Valor atual</th></tr></thead>
                <tbody>{ov.by_category.map((c) => <tr key={c.category}><td>{CATEGORY_LABEL[c.category]}</td><td className="r num">{c.count}</td><td className="r num">{fmtBRL(c.value)}</td></tr>)}</tbody>
              </table></div>
            )}
          </section>
        </>
      )}

      {tab === "mine" && <MyGoods goods={goods} onOpen={(id) => nav(`/patrimonio/${id}`)} />}
      {tab === "market" && <Market cash={cash} onBought={(g) => { setNotice(`${g.good.name} comprado.`); void reload(); nav(`/patrimonio/${g.good.id}`); }} />}
    </div>
  );
}

function MyGoods({ goods, onOpen }: { goods: Good[]; onOpen: (id: number) => void }) {
  const [cat, setCat] = useState<GoodCategory | "ALL">("ALL");
  const [showSold, setShowSold] = useState(false);
  const rows = goods.filter((g) => (cat === "ALL" || g.category === cat) && (showSold || g.status === "ACTIVE"));
  return (
    <section className="card">
      <div className="row">
        <h2>Meus bens</h2>
        <div className="row-gap">
          <select value={cat} onChange={(e) => setCat(e.target.value as GoodCategory | "ALL")} aria-label="Filtrar por categoria">
            <option value="ALL">Todas as categorias</option>
            {CATS.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>)}
          </select>
          <label className="check"><input type="checkbox" checked={showSold} onChange={(e) => setShowSold(e.target.checked)} />vendidos/baixados</label>
        </div>
      </div>
      {rows.length === 0 ? <div className="empty">Nenhum bem encontrado.</div> : (
        <div className="goods-grid">{rows.map((g) => (
          <button key={g.id} className="card good-card" onClick={() => onOpen(g.id)}>
            <div className="row"><b>{g.name}</b><span className="tag">{GOOD_STATUS_LABEL[g.status]}</span></div>
            <span className="muted small">{CATEGORY_LABEL[g.category]}{g.location ? ` · ${g.location}` : ""}</span>
            <span className="num good-value">{g.status === "ACTIVE" ? fmtBRL(g.current_value) : fmtBRL(g.sale_result ?? "0")}</span>
            <span className="muted small">{g.status === "ACTIVE"
              ? <>Adquirido em {fmtDay(g.acquired_on)} por {fmtBRL(g.acquisition_cost)}</>
              : <>Resultado da venda {g.sold_on ? `em ${fmtDay(g.sold_on)}` : ""}</>}</span>
            {g.occupancy && g.status === "ACTIVE" && <span className="tag">{OCCUPANCY_LABEL[g.occupancy]}{g.occupancy === "RENTED" ? ` · ${fmtBRL(g.monthly_rent)}/mês` : ""}</span>}
            {g.loan_balance && Number(g.loan_balance) > 0 && g.status === "ACTIVE" && <span className="muted small">Saldo devedor {fmtBRL(g.loan_balance)}</span>}
          </button>
        ))}</div>
      )}
    </section>
  );
}

function Market({ cash, onBought }: { cash: string; onBought: (g: import("../services/api").GoodDetail) => void }) {
  const [cat, setCat] = useState<GoodCategory | "ALL">("ALL");
  const [q, setQ] = useState("");
  const [max, setMax] = useState("");
  const [list, setList] = useState<Listing[] | null>(null);
  const [buying, setBuying] = useState<Listing | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const p: Record<string, string> = {};
    if (cat !== "ALL") p.category = cat;
    if (q.trim()) p.q = q.trim();
    if (max.trim()) p.max_price = max.trim().replace(/\./g, "").replace(",", ".");
    const t = window.setTimeout(() => { api.market(p).then((l) => { setList(l); setError(null); }).catch((e) => setError(errMsg(e))); }, 250);
    return () => window.clearTimeout(t);
  }, [cat, q, max]);

  return (
    <section className="card">
      <h2>Mercado de bens</h2>
      <p className="muted small">Anúncios simulados, com preços que acompanham o mês do simulador. Nenhum dado externo é usado.</p>
      <div className="row-gap" style={{ maxWidth: "none", flexWrap: "wrap", marginBottom: 14 }}>
        <select value={cat} onChange={(e) => setCat(e.target.value as GoodCategory | "ALL")} aria-label="Categoria">
          <option value="ALL">Todas as categorias</option>{CATS.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>)}
        </select>
        <input placeholder="Buscar (nome ou cidade)" value={q} onChange={(e) => setQ(e.target.value)} />
        <input placeholder="Preço máximo (R$)" inputMode="decimal" value={max} onChange={(e) => setMax(e.target.value)} />
      </div>
      {error && <div className="alert">{error}</div>}
      {!list ? <div className="muted">Carregando…</div> : list.length === 0 ? <div className="empty">Nenhum anúncio com esses filtros.</div> : (
        <div className="goods-grid">{list.map((l) => (
          <div key={l.key} className="card good-card">
            <div className="row"><b>{l.name}</b>{l.owned && <span className="tag">você já possui</span>}</div>
            <span className="muted small">{CATEGORY_LABEL[l.category]} · {l.location}</span>
            <span className="num good-value">{fmtBRL(l.price)}</span>
            <span className="muted small">{l.description}</span>
            {l.area_m2 && <span className="muted small">{l.area_m2} m²{l.bedrooms ? ` · ${l.bedrooms} quarto(s)` : ""}{l.suggested_rent ? ` · aluguel de referência ${fmtBRL(l.suggested_rent)}` : ""}</span>}
            {l.financing && <span className="muted small">Financia até {l.financing.max_term_months} meses</span>}
            <button className="btn small primary" disabled={l.owned} onClick={() => setBuying(l)}>{l.owned ? "Já adquirido" : "Ver e comprar"}</button>
          </div>
        ))}</div>
      )}
      {buying && <PurchaseModal listing={buying} cash={cash} onClose={() => setBuying(null)} onBought={(g) => { setBuying(null); onBought(g); }} />}
    </section>
  );
}

export function BackLink() { return <Link to="/patrimonio" className="link-btn" style={{ marginLeft: 0 }}>← Patrimônio</Link>; }
