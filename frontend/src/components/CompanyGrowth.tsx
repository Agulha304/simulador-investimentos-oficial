import { useState } from "react";
import { api, type CoAide, type CoAideKind, type CoAideLevel, type CoTier, type CompanyDetail } from "../services/api";
import { fmtBRL, fmtMonth } from "../lib/format";

type Act = (fn: () => Promise<CompanyDetail>, msg: string) => Promise<void>;
const TIER_LABEL: Record<CoTier, string> = { BARATO: "Barata", MEDIO: "Média", CARO: "Cara" };

/** Marketeiro e gerente: baixo/médio/alto nível, cada um com briefing (orçamento mensal; rigidez). */
export function AidesCard({ d, act }: { d: CompanyDetail; act: Act }) {
  const id = d.company.id;
  return (
    <section className="card stack" aria-label="Marketeiro e gerente">
      <h2>Marketeiro e gerente</h2>
      <p className="muted small" style={{ margin: 0 }}>
        <b>Opcionais.</b> O marketeiro gasta todo mês o orçamento que você definir em campanhas: quanto melhor o nível e o orçamento, maior a chance de a campanha dar certo (nunca é garantido).
        O gerente eleva a produtividade da empresa; quanto mais <b>rígido</b>, mais ela rende, mas os funcionários podem pedir demissão.
      </p>
      <div className="goods-grid">
        <AideBox d={d} kind="MARKETER" title="📣 Marketeiro" act={act} id={id} />
        <AideBox d={d} kind="MANAGER" title="🧑‍💼 Gerente" act={act} id={id} />
      </div>
    </section>
  );
}

function AideBox({ d, kind, title, act, id }: { d: CompanyDetail; kind: CoAideKind; title: string; act: Act; id: number }) {
  const cur: CoAide | null = (kind === "MARKETER" ? d.aides?.marketer : d.aides?.manager) ?? null;
  const opts = (kind === "MARKETER" ? d.aide_options?.marketer : d.aide_options?.manager) ?? [];
  const [budget, setBudget] = useState(cur?.settings.monthly_budget ?? "0");
  const [rigor, setRigor] = useState(cur?.settings.rigor ?? 40);
  return (
    <div className="card good-card stack">
      <div className="row"><b>{title}</b>{cur && <span className="tag">{cur.label}</span>}</div>
      {!cur && opts.map((o) => (
        <div key={o.level} className="row">
          <span>{o.label} <span className="muted small">· {fmtBRL(o.fee)}/mês</span></span>
          <button type="button" className="btn small primary" onClick={() => void act(() => api.coAideHire(id, kind, o.level as CoAideLevel), `${title.slice(3)} contratado.`)}>Contratar</button>
        </div>
      ))}
      {cur && (
        <>
          <span className="muted small">Taxa mensal {fmtBRL(cur.fee)} · cobrada no fechamento.</span>
          <label className="muted small">Trocar nível
            <select value={cur.level} onChange={(e) => void act(() => api.coAideHire(id, kind, e.target.value as CoAideLevel), "Nível alterado.")}>
              {opts.map((o) => <option key={o.level} value={o.level}>{o.label} — {fmtBRL(o.fee)}/mês</option>)}</select></label>
          {kind === "MARKETER" ? (
            <>
              <label>Orçamento mensal de marketing (R$)
                <input inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} /></label>
              <button type="button" className="btn small" onClick={() => void act(() => api.coAideBriefing(id, kind, { monthly_budget: budget.replace(/\./g, "").replace(",", ".") }), "Briefing do marketeiro salvo.")}>Salvar briefing</button>
            </>
          ) : (
            <>
              <label>Rigidez: {rigor}/100 {rigor >= 70 ? "(alta: risco de demissões)" : rigor <= 30 ? "(branda)" : ""}
                <input type="range" min={0} max={100} value={rigor} onChange={(e) => setRigor(Number(e.target.value))} /></label>
              <span className="muted small">Produtividade +{cur.productivity_pct ?? 0}% · chance mensal de cada funcionário pedir demissão {cur.quit_chance_pct ?? 0}%.</span>
              <button type="button" className="btn small" onClick={() => void act(() => api.coAideBriefing(id, kind, { rigor }), "Briefing do gerente salvo.")}>Salvar briefing</button>
            </>
          )}
          <button type="button" className="btn small ghost" onClick={() => window.confirm("Dispensar? Sem multa.") && void act(() => api.coAideDismiss(id, kind), "Dispensado.")}>Dispensar</button>
        </>
      )}
    </div>
  );
}

/** Franquias: publicidade da franquia, franqueados e royalties. Difícil: exige marca relevante. */
export function FranchiseCard({ d, act }: { d: CompanyDetail; act: Act }) {
  const f = d.franchise;
  if (!f) return null;
  const id = d.company.id;
  return (
    <section className="card stack" aria-label="Franquias">
      <h2>Franquias</h2>
      <p className="muted small" style={{ margin: 0 }}>
        Você pode franquear a marca a qualquer momento (e é o único jeito de crescer depois de {f.units_cap - 1} filiais próprias). Mas é <b>difícil</b>: ninguém abre franquia de marca desconhecida
        (relevância mínima {f.min_relevance_ad}). A publicidade da franquia aumenta a atratividade e a relevância da marca cresce com cada franquia, mas você ganha só taxa inicial e {f.royalty_pct}% de royalties, bem menos que numa filial própria.
      </p>
      <div className="stats-grid">
        <div className="card"><span className="muted small">Atratividade</span><b className="num">{f.appeal.toFixed(1)}/100</b></div>
        <div className="card"><span className="muted small">Chance mensal de novo franqueado</span><b className="num">{f.monthly_interest_pct}%</b></div>
        <div className="card"><span className="muted small">Franquias abertas / em obra</span><b className="num">{f.open - f.building} / {f.building}</b></div>
        <div className="card"><span className="muted small">Royalties recebidos</span><b className="num">{fmtBRL(f.total_royalties)}</b></div>
      </div>
      <div className="row-gap" style={{ flexWrap: "wrap" }}>
        {(Object.keys(f.ad_costs) as CoTier[]).map((t) => (
          <button key={t} type="button" className="btn small primary" onClick={() => void act(() => api.coFranchiseAd(id, t), "Publicidade da franquia paga.")}>Publicidade {TIER_LABEL[t]} — {fmtBRL(f.ad_costs[t])}</button>
        ))}
      </div>
      {f.franchises.length > 0 && (
        <ul className="list-plain">{f.franchises.map((x) => (
          <li key={x.id}><span>{x.name} · {x.status === "OPEN" ? `abre em ${fmtMonth(x.opens_month)}` : `fechada: ${x.closed_reason ?? ""}`}</span><b className="num">{fmtBRL(x.total_royalties)}</b></li>))}</ul>
      )}
    </section>
  );
}

/** Abertura de capital (IPO): pré-requisitos, pedido, ação negociada e venda/recompra da sua participação. */
export function IpoCard({ d, act }: { d: CompanyDetail; act: Act }) {
  const ipo = d.ipo;
  const [pct, setPct] = useState("25");
  const [stake, setStake] = useState("5");
  if (!ipo) return null;
  const id = d.company.id;
  const l = ipo.listing;
  return (
    <section className="card stack" aria-label="Abertura de capital">
      <h2>📈 Abertura de capital (bolsa)</h2>
      {!l && (
        <>
          <p className="muted small" style={{ margin: 0 }}>
            Vender parte da empresa ao público traz dinheiro para o caixa, mas dilui a sua participação e os dividendos passam a ser divididos. Exige empresa madura e lucrativa; o processo leva {ipo.eligibility.process_months} meses.
          </p>
          <ul className="list-plain">
            <li><span>Avaliação atual</span><b className="num">{fmtBRL(ipo.eligibility.valuation)}</b></li>
            <li><span>Lucro líquido médio (6 meses)</span><b className="num">{fmtBRL(ipo.eligibility.avg_net_6m)}</b></li>
            <li><span>Preparação (auditoria e taxas)</span><b className="num">{fmtBRL(ipo.eligibility.prep_fee)}</b></li>
          </ul>
          {!ipo.eligibility.ok && <div className="alert">Ainda não pode abrir capital: {ipo.eligibility.missing.join("; ")}.</div>}
          <label>% do capital oferecido ({ipo.min_float}–{ipo.max_float})
            <input inputMode="decimal" value={pct} onChange={(e) => setPct(e.target.value)} /></label>
          <button type="button" className="btn primary" disabled={!ipo.eligibility.ok}
            onClick={() => window.confirm(`Pedir o IPO com ${pct}% do capital? A preparação custa ${fmtBRL(ipo.eligibility.prep_fee)}.`) && void act(() => api.coIpoApply(id, pct.replace(",", ".")), "IPO solicitado.")}>Pedir abertura de capital</button>
        </>
      )}
      {l && l.status === "PENDING" && <p className="muted">IPO <b>{l.ticker}</b> em andamento: {l.float_pct}% do capital; estreia no pregão em {fmtMonth(l.lists_month)}.</p>}
      {l && l.status === "LISTED" && (
        <>
          <div className="stats-grid">
            <div className="card"><span className="muted small">{l.ticker}</span><b className="num">R$ {Number(l.price).toFixed(2)}</b><span className="muted small">IPO a R$ {Number(l.ipo_price).toFixed(2)}</span></div>
            <div className="card"><span className="muted small">Valor de mercado</span><b className="num">{fmtBRL(l.market_cap)}</b></div>
            <div className="card"><span className="muted small">Sua participação</span><b className="num">{l.owner_share_pct}%</b><span className="muted small">vale {fmtBRL(l.my_stake_value)}</span></div>
            <div className="card"><span className="muted small">Captação líquida do IPO</span><b className="num">{fmtBRL(l.proceeds)}</b></div>
          </div>
          <PriceSpark history={l.history} />
          <div className="row-gap" style={{ flexWrap: "wrap" }}>
            <input aria-label="Pontos percentuais" inputMode="decimal" value={stake} onChange={(e) => setStake(e.target.value)} style={{ width: 90 }} />
            <button type="button" className="btn small" onClick={() => void act(() => api.coIpoSell(id, stake.replace(",", ".")), "Participação vendida no pregão.")}>Vender % da minha parte</button>
            <button type="button" className="btn small ghost" onClick={() => void act(() => api.coIpoBuyback(id, stake.replace(",", ".")), "Participação recomprada.")}>Recomprar % do mercado</button>
          </div>
          <p className="muted small" style={{ margin: 0 }}>Você precisa manter pelo menos 30% do capital; a recompra paga 3% de prêmio e vai até a participação que você tinha antes do IPO ({l.prev_owner_share}%).</p>
        </>
      )}
    </section>
  );
}

function PriceSpark({ history }: { history: { month: string; price: string }[] }) {
  if (history.length < 2) return <p className="muted small">O histórico de preços aparece nos próximos meses.</p>;
  const v = history.map((h) => Number(h.price));
  const lo = Math.min(...v), hi = Math.max(...v), w = 300, h = 60;
  const pts = v.map((x, i) => `${(i / (v.length - 1)) * w},${h - ((x - lo) / (hi - lo || 1)) * (h - 6) - 3}`).join(" ");
  return <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Histórico do preço da ação" style={{ width: "100%", maxWidth: 420, height: 64 }}>
    <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="2" /></svg>;
}
