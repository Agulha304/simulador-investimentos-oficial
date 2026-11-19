import { useCallback, useEffect, useState } from "react";
import { StatCard } from "../components/StatCard";
import { fmtMonth } from "../lib/format";
import { sim, type EcoEvent, type Economy } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
const SCOPE: Record<string, string> = { WORLD: "todo o mundo", SECTOR: "um setor", USER: "você", COMPANY: "uma empresa sua" };
const CAT: Record<string, string> = { ECONOMIC: "Econômico", PERSONAL: "Pessoal", BUSINESS: "Empresarial" };

export function EconomyPage() {
  const [eco, setEco] = useState<Economy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const load = useCallback(() => sim.economy().then(setEco).catch((e) => setError(errMsg(e))), []);
  useEffect(() => { void load(); }, [load]);
  const decide = async (ev: EcoEvent, option: string) => {
    setError(null);
    try { const r = await sim.ecoDecide(ev.id, option); setNote(r.event.outcome); await load(); } catch (e) { setError(errMsg(e)); }
  };
  if (!eco) return error ? <div className="alert">{error}</div> : <div className="muted">Carregando economia…</div>;
  const st = eco.state;
  const last = eco.history.slice(-24);
  const maxInfl = Math.max(1, ...last.map((h) => Math.abs(Number(h.inflation))));
  return (
    <div className="page">
      <header className="page-head"><div><h1>Economia</h1><p className="muted">{eco.dynamic ? `Mundo dinâmico (semente ${eco.seed}). As mesmas condições valem para orçamento, família, empresas e bens.` : "Economia estável: preços e demanda não variam. Inicie uma partida para ativar a economia dinâmica."}</p></div></header>
      {error && <div className="alert">{error}</div>}
      {note && <div className="card small">Resultado: {note}</div>}
      {st && (
        <>
          <section className="stats-grid">
            <StatCard label="Inflação (a.a.)" value={`${Number(st.inflation).toFixed(2)}%`} />
            <StatCard label="Juros (a.a.)" value={`${Number(st.interest).toFixed(2)}%`} sub="afetam financiamentos novos" />
            <StatCard label="Desemprego" value={`${Number(st.unemployment).toFixed(1)}%`} />
            <StatCard label="Crescimento (a.a.)" value={`${Number(st.growth).toFixed(2)}%`} tone={Number(st.growth) >= 0 ? "up" : "down"} />
            <StatCard label="Demanda agregada" value={Number(st.demand).toFixed(1)} sub="100 = normal" />
            <StatCard label="Confiança do consumidor" value={Number(st.confidence).toFixed(0)} />
          </section>
          <section className="card stack"><h2>Inflação ao longo dos meses</h2>
            <div className="bars" aria-label="inflação mensal">{last.map((h) => <div key={h.month} title={`${fmtMonth(h.month)}: ${Number(h.inflation).toFixed(2)}%`} className={Number(h.inflation) < 0 ? "neg" : ""} style={{ height: `${(Math.abs(Number(h.inflation)) / maxInfl) * 100}%` }} />)}</div></section>
          <section className="card stack"><h2>Preços por categoria</h2>
            <div className="table-wrap"><table><thead><tr><th>Categoria</th><th className="r">Índice acumulado</th><th className="r">Variação no mês</th></tr></thead>
              <tbody>{eco.categories.map((c) => { const ch = st.monthly_changes[c.key] ?? 0; return (
                <tr key={c.key}><td>{c.label}</td><td className="r num">{(st.indices[c.key] ?? 1).toFixed(4)}</td><td className={`r num ${ch > 0.5 ? "tone-down" : ch < 0 ? "tone-up" : ""}`}>{ch.toFixed(2)}%</td></tr>); })}</tbody></table></div></section>
        </>
      )}
      <section className="card stack"><h2>Decisões pendentes ({eco.pending.length})</h2>
        {eco.pending.length === 0 && <p className="muted small">Nenhum acontecimento aguardando escolha.</p>}
        {eco.pending.map((ev) => (
          <div key={ev.id} className="card stack"><div className="row between"><b>{ev.name}</b><span className="chip warn">{CAT[ev.category]}</span></div>
            <p className="small">{ev.description}</p>
            <div className="row">{ev.options?.map((o) => <button key={o.key} className="btn ghost small" onClick={() => void decide(ev, o.key)} title={o.hint}>{o.label}{o.cost ? ` (custa ~R$ ${o.cost})` : ""}</button>)}</div>
            <ul className="list-plain small">{ev.options?.map((o) => <li key={o.key}><span><b>{o.label}:</b> {o.hint}</span></li>)}</ul>
            <p className="muted small">O resultado exato só aparece depois da decisão. Se o mês virar sem escolha, vale a opção padrão.</p></div>))}
      </section>
      <EventList title="Eventos em andamento" events={eco.active} />
      <EventList title="Eventos passados" events={eco.past.slice(0, 15)} />
    </div>
  );
}

function EventList({ title, events }: { title: string; events: EcoEvent[] }) {
  return (
    <section className="card stack"><h2>{title}</h2>
      {events.length === 0 ? <p className="muted small">Nenhum.</p> : <ul className="list-plain">{events.map((e) => (
        <li key={e.id}><span><b>{e.name}</b> <span className={`chip ${e.positive ? "up" : "down"}`}>{e.positive ? "favorável" : "adverso"}</span> <span className="chip">{CAT[e.category]} · afeta {SCOPE[e.scope]}</span><br /><span className="muted small">{e.outcome ?? e.description}</span></span>
          <span className="muted small">{fmtMonth(e.start_month)} → {fmtMonth(e.end_month)}</span></li>))}</ul>}
    </section>
  );
}
