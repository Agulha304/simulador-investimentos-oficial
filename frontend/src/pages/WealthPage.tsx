import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PurchaseModal } from "../components/GoodsModals";
import { BuildPanel } from "../components/BuildPanel";
import { StatCard } from "../components/StatCard";
import { type Good, type GoodCategory, type Listing, type PortfolioSummary, type WealthOverview } from "../services/api";
import { cachedGet, useApi } from "../services/dataCache";
import { CATEGORY_LABEL, GOOD_STATUS_LABEL, OCCUPANCY_LABEL, fmtBRL, fmtDay, trend } from "../lib/format";

const WealthSeriesChart = lazy(() => import("../components/charts/WealthCharts").then((m) => ({ default: m.WealthSeriesChart })));
const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
type Tab = "overview" | "mine" | "market" | "build";
export type Group = "goods" | "realty" | "vehicles";
const GROUPS: Record<Group, { cats: GoodCategory[]; title: string; emoji: string; intro: string; path: string }> = {
  goods: { cats: ["INSTRUMENT", "EQUIPMENT", "ANTIQUE", "COLLECTIBLE", "OTHER"], title: "Bens", emoji: "🎻", path: "/patrimonio",
    intro: "Instrumentos, equipamentos, antiguidades, joias e coleções. Alguns valorizam com o tempo; outros perdem valor." },
  realty: { cats: ["RESIDENTIAL", "COMMERCIAL", "LAND"], title: "Imóveis", emoji: "🏡", path: "/imoveis",
    intro: "Casas, apartamentos, lojas e terrenos. Você pode morar (e parar de pagar aluguel), alugar por um valor fixo ou hospedar por temporada, que rende mais mas dá trabalho." },
  vehicles: { cats: ["CAR", "MOTORCYCLE"], title: "Automóveis", emoji: "🚗", path: "/automoveis",
    intro: "Carros e motos. Cada um traz IPVA, seguro, combustível e manutenção — e perde valor com o tempo." },
};

export function WealthPage({ group = "goods" }: { group?: Group }) {
  const nav = useNavigate();
  const G = GROUPS[group];
  const [tab, setTab] = useState<Tab>("overview");
  // quatro leituras em paralelo (todas com cache; carteira e mercado são compartilhados com outras telas)
  const { data: ov, error: ovErr, reload: reloadOv } = useApi<WealthOverview>("/goods/overview");
  const { data: allGoods, error: goodsErr, reload: reloadGoods } = useApi<Good[]>("/goods?");
  const { data: pf, error: pfErr, reload: reloadPf } = useApi<PortfolioSummary>("/portfolio");
  const { data: taxes } = useApi<{ total: string; items: { tax: string; amount: string }[] }>("/goods/taxes/summary");
  const goods = useMemo(() => (allGoods ?? []).filter((x) => G.cats.includes(x.category)), [allGoods, G]);
  const cash = pf?.cash_balance ?? "0";
  const mine = goods.filter((g) => g.status === "ACTIVE");
  const value = mine.reduce((a, g) => a + Number(g.current_value), 0);
  const cost = mine.reduce((a, g) => a + Number(g.acquisition_cost), 0);
  const debt = mine.reduce((a, g) => a + Number(g.loan_balance ?? 0), 0);
  const error = ovErr ?? goodsErr ?? pfErr;
  const [notice, setNotice] = useState<string | null>(null);
  const reload = () => Promise.all([reloadOv(), reloadGoods(), reloadPf()]);

  if (error && !ov) return <div className="alert">Não foi possível carregar o patrimônio: {error}</div>;
  if (!ov) return <div className="muted">Carregando patrimônio…</div>;

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>{G.emoji} {G.title}</h1><p className="muted">{G.intro}</p></div>
      </header>
      {error && <div className="alert">{error}</div>}
      {notice && <div className="ok">{notice}</div>}
      <div className="seg compact tabs">
        <button className={tab === "overview" ? "on" : ""} onClick={() => setTab("overview")}>Visão geral</button>
        <button className={tab === "mine" ? "on" : ""} onClick={() => setTab("mine")}>Meus {G.title.toLowerCase()} ({mine.length})</button>
        <button className={tab === "market" ? "on" : ""} onClick={() => setTab("market")}>Mercado de bens</button>
        {G.cats.includes("RESIDENTIAL") && <button className={tab === "build" ? "on" : ""} onClick={() => setTab("build")}>Construir</button>}
      </div>

      {tab === "overview" && (
        <>
          <section className="stats-grid">
            <StatCard label={`Valor dos seus ${G.title.toLowerCase()}`} value={fmtBRL(String(value))} sub={`${mine.length} ${mine.length === 1 ? "item" : "itens"}`} emphasis />
            <StatCard label="Custo de aquisição" value={fmtBRL(String(cost))} sub="o que você pagou, com impostos e taxas" />
            <StatCard label="Dívidas (financiamentos)" value={fmtBRL(String(debt))} tone={debt > 0 ? "down" : "neutral"} />
            <StatCard label="Valorização não realizada" value={fmtBRL(String(value - cost))} tone={trend(String(value - cost))} sub="valor atual − custo de aquisição" />
          </section>
          <section className="card stack">
            <h2>🧾 Impostos que você paga sobre os seus bens</h2>
            <p className="muted small" style={{ margin: 0 }}>ITBI e registro na compra, IPTU e IPVA todo ano, imposto de renda sobre aluguéis e hospedagens, ISS da temporada e imposto sobre o lucro quando você vende.</p>
            {!taxes || taxes.items.length === 0 ? <p className="muted small">Nenhum imposto pago ainda.</p> : (
              <ul className="list-plain">{taxes.items.map((t) => <li key={t.tax}><span>{t.tax}</span><b className="num">{fmtBRL(t.amount)}</b></li>)}
                <li><span><b>Total pago</b></span><b className="num">{fmtBRL(taxes.total)}</b></li></ul>)}
          </section>
          <Suspense fallback={<div className="card muted">Carregando gráfico…</div>}><WealthSeriesChart series={ov.series} /></Suspense>
          <section className="card">
            <h2>Composição por categoria</h2>
            {ov.by_category.filter((c) => G.cats.includes(c.category)).length === 0 ? <div className="empty">Você ainda não possui bens. Veja o Mercado de bens.</div> : (
              <div className="table-wrap"><table>
                <thead><tr><th>Categoria</th><th className="r">Quantidade</th><th className="r">Valor atual</th></tr></thead>
                <tbody>{ov.by_category.filter((c) => G.cats.includes(c.category)).map((c) => <tr key={c.category}><td>{CATEGORY_LABEL[c.category]}</td><td className="r num">{c.count}</td><td className="r num">{fmtBRL(c.value)}</td></tr>)}</tbody>
              </table></div>
            )}
          </section>
        </>
      )}

      {tab === "mine" && <MyGoods goods={goods} cats={G.cats} onOpen={(id) => nav(`/patrimonio/${id}`)} />}
      {tab === "build" && <BuildPanel onBuilt={(g) => { setNotice(`Obra contratada: ${g.good.name}.`); void reload(); nav(`/patrimonio/${g.good.id}`); }} />}
      {tab === "market" && <Market cash={cash} cats={G.cats} onBought={(g) => { setNotice(`${g.good.name} comprado.`); void reload(); nav(`/patrimonio/${g.good.id}`); }} />}
    </div>
  );
}

function MyGoods({ goods, cats: CATS, onOpen }: { goods: Good[]; cats: GoodCategory[]; onOpen: (id: number) => void }) {
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
            {g.available_month && g.status === "ACTIVE" && <span className="tag">{g.construction_plan ? "Em obra" : "Em escritura"} até {g.available_month.slice(0, 7)}</span>}
            {g.occupancy && g.status === "ACTIVE" && <span className="tag">{OCCUPANCY_LABEL[g.occupancy]}{g.occupancy === "RENTED" ? ` · ${fmtBRL(g.monthly_rent)}/mês` : ""}</span>}
            {g.loan_balance && Number(g.loan_balance) > 0 && g.status === "ACTIVE" && <span className="muted small">Saldo devedor {fmtBRL(g.loan_balance)}</span>}
          </button>
        ))}</div>
      )}
    </section>
  );
}

function Market({ cash, cats: CATS, onBought }: { cash: string; cats: GoodCategory[]; onBought: (g: import("../services/api").GoodDetail) => void }) {
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
    const t = window.setTimeout(() => { cachedGet<Listing[]>(`/goods/market?${new URLSearchParams(p)}`).then((l) => { setList(l.filter((x) => CATS.includes(x.category))); setError(null); }).catch((e) => setError(errMsg(e))); }, 250);
    return () => window.clearTimeout(t);
  }, [cat, q, max, CATS]);

  return (
    <section className="card">
      <h2>Mercado</h2>
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

export function BackLink() { const nav = useNavigate(); return <button onClick={() => nav(-1)} className="link-btn" style={{ marginLeft: 0 }}>← Voltar</button>; }
