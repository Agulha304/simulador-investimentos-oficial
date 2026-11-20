import { useCallback, useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { StatCard } from "../components/StatCard";
import { fmtMonth } from "../lib/format";
import { sim, type Crisis, type EcoEvent, type Economy, type SimParams } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
const SCOPE: Record<string, string> = { WORLD: "todo o mundo", SECTOR: "um setor", USER: "você", COMPANY: "uma empresa sua" };
const CAT: Record<string, string> = { ECONOMIC: "Econômico", PERSONAL: "Pessoal", BUSINESS: "Empresarial" };
const REGIME: Record<string, [string, string]> = {
  BULL: ["🐂 Mercado otimista", "Os preços tendem a subir e os investidores estão confiantes."], BEAR: ["🐻 Mercado pessimista", "Os preços tendem a cair e há medo no ar."],
  SIDEWAYS: ["↔️ Mercado lateral", "Os preços andam de lado, sem direção clara."], HIGH_VOL: ["🎢 Muita oscilação", "Os preços sobem e descem com força."],
  LOW_VOL: ["😴 Calmaria", "Os preços variam pouco."], RECOVERY: ["🌱 Recuperação", "O mercado se levanta depois de uma queda."], CRISIS: ["🚨 Crise", "Quedas fortes e simultâneas nos mercados."],
};
const PHASE: Record<string, string> = { ONSET: "começando", PEAK: "no pior momento", RECOVERY: "se recuperando" };
const CRISIS_HELP: Record<string, string> = {
  FINANCIAL: "O crédito some e o mercado cai de uma vez.", BANKING: "Bancos em apuros: empréstimos ficam raros.", INFLATION: "Tudo fica mais caro por muito tempo.",
  DEBT: "Muita gente e empresas sem conseguir pagar suas dívidas.", HOUSING: "Imóveis caem de preço e ficam vagos.", SUPPLY: "Falta de produtos: preços sobem.",
  CURRENCY: "O real perde valor e o que vem de fora fica caro.", RECESSION: "A economia encolhe: menos vendas e mais desemprego.", GLOBAL: "Uma crise mundial que atinge todo mundo.",
};
const COLORS = ["#ffd23f", "#3ee59a", "#ff6482", "#4cc9f0", "#c13cff", "#ff9f1c"];
type Tab = "now" | "charts" | "crises" | "prices" | "config";

export function EconomyPage() {
  const [eco, setEco] = useState<Economy | null>(null);
  const [tab, setTab] = useState<Tab>("now");
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
  return (
    <div className="page">
      <header className="page-head"><div><h1>🌍 Economia</h1><p className="muted">{eco.dynamic ? `Mundo dinâmico (semente ${eco.seed}). Os preços do mercado abaixo são SIMULADOS pelo jogo — não são previsões do mundo real.` : "Economia estável: os preços não variam. Comece uma partida de vida completa para ativar a economia dinâmica."}</p></div></header>
      {error && <div className="alert">{error}</div>}
      {note && <div className="card small">Resultado: {note}</div>}
      <div className="seg compact tabs">
        {([["now", "Hoje"], ["charts", "Gráficos"], ["crises", `Crises e eventos (${eco.crises.length})`], ["prices", "Preços"], ["config", "Ajustes"]] as [Tab, string][]).map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {tab === "now" && st && <Now eco={eco} decide={decide} />}
      {tab === "now" && !st && <div className="card muted">Sem dados ainda.</div>}
      {tab === "charts" && <Charts eco={eco} />}
      {tab === "crises" && <Crises eco={eco} />}
      {tab === "prices" && st && <Prices eco={eco} />}
      {tab === "config" && <Config eco={eco} reload={load} />}
    </div>
  );
}

function Now({ eco, decide }: { eco: Economy; decide: (e: EcoEvent, o: string) => void }) {
  const st = eco.state!;
  const active = eco.crises.filter((c) => c.status === "ACTIVE");
  const reg = st.regime ? REGIME[st.regime] : null;
  return (
    <>
      {active.map((c) => (
        <div key={c.id} className="notice">🚨 <b>{c.label}</b> — {CRISIS_HELP[c.type]} Está <b>{PHASE[c.phase]}</b> (intensidade {Math.round(c.intensity * 100)}%).</div>))}
      {reg && <section className="card"><b>{reg[0]}</b><p className="muted small" style={{ margin: "4px 0 0" }}>{reg[1]}</p></section>}
      <section className="stats-grid">
        <StatCard label="🛒 Inflação (12 meses)" value={`${Number(st.inflation).toFixed(2)}%`} sub="quanto os preços subiram no último ano" />
        <StatCard label="🏦 Juros (Selic)" value={`${Number(st.interest).toFixed(2)}%`} sub="afeta financiamentos e a renda fixa" />
        <StatCard label="👷 Desemprego" value={`${Number(st.unemployment).toFixed(1)}%`} />
        <StatCard label="📈 Crescimento (PIB)" value={`${Number(st.growth).toFixed(2)}%`} tone={Number(st.growth) >= 0 ? "up" : "down"} />
        <StatCard label="💵 Dólar" value={st.fx ? `R$ ${st.fx.toFixed(2)}` : "—"} />
        <StatCard label="😊 Confiança do consumidor" value={Number(st.confidence).toFixed(0)} sub="0 a 100" />
        <StatCard label="💳 Crédito disponível" value={st.credit != null ? st.credit.toFixed(0) : "—"} sub="quanto mais alto, mais fácil conseguir empréstimo" />
        <StatCard label="🧾 Dívida das famílias" value={st.household_debt != null ? `${st.household_debt.toFixed(0)}% da renda` : "—"} />
      </section>
      <section className="card stack"><h2>📌 Decisões pendentes ({eco.pending.length})</h2>
        {eco.pending.length === 0 && <p className="muted small">Nenhum acontecimento aguardando escolha.</p>}
        {eco.pending.map((ev) => (
          <div key={ev.id} className="card stack"><div className="row between"><b>{ev.name}</b><span className="chip warn">{CAT[ev.category]}</span></div>
            <p className="small">{ev.description}</p>
            <div className="row">{ev.options?.map((o) => <button key={o.key} className="btn ghost small" onClick={() => void decide(ev, o.key)} title={o.hint}>{o.label}{o.cost ? ` (custa ~R$ ${o.cost})` : ""}</button>)}</div>
            <ul className="list-plain small">{ev.options?.map((o) => <li key={o.key}><span><b>{o.label}:</b> {o.hint}</span></li>)}</ul>
            <p className="muted small">O resultado exato só aparece depois da decisão. Se o mês virar sem escolha, vale a opção padrão.</p></div>))}
      </section>
    </>
  );
}

function Charts({ eco }: { eco: Economy }) {
  const data = useMemo(() => eco.history.map((h) => ({
    m: fmtMonth(h.month).replace(" de ", "/"), inflacao: Number(h.inflation), juros: Number(h.interest), desemprego: Number(h.unemployment),
    pib: Number(h.growth), dolar: h.fx ?? undefined, confianca: Number(h.confidence), acoes: h.class_index?.equity, fiis: h.class_index?.fii,
    cripto: h.class_index?.crypto, imoveis: h.class_index?.house, rendafixa: h.class_index?.bond, iprice: h.indices.geral,
    mensal: h.general_inflation_month ?? undefined,
  })), [eco.history]);
  const areas = eco.crises.map((c) => ({ from: fmtMonth(c.start_month).replace(" de ", "/"), to: fmtMonth(c.end_month ?? eco.month).replace(" de ", "/") }));
  const Chart = ({ title, keys, hint }: { title: string; keys: [string, string][]; hint: string }) => (
    <section className="card stack"><h2>{title}</h2><p className="muted small" style={{ margin: 0 }}>{hint}</p>
      <div style={{ height: 220 }}><ResponsiveContainer><LineChart data={data}><CartesianGrid stroke="#4d40a855" strokeDasharray="3 3" />
        <XAxis dataKey="m" tick={{ fill: "#c3bcf0", fontSize: 11 }} minTickGap={30} /><YAxis tick={{ fill: "#c3bcf0", fontSize: 11 }} domain={["auto", "auto"]} />
        <Tooltip contentStyle={{ background: "#281e63", border: "2px solid #4d40a8", borderRadius: 12 }} /><Legend />
        {areas.map((a, i) => <ReferenceArea key={i} x1={a.from} x2={a.to} fill="#ff6482" fillOpacity={0.12} />)}
        {keys.map(([k, name], i) => <Line key={k} type="monotone" dataKey={k} name={name} stroke={COLORS[i % COLORS.length]} dot={false} strokeWidth={2.5} />)}
      </LineChart></ResponsiveContainer></div></section>
  );
  if (data.length < 2) return <div className="card muted">Avance alguns meses para ver os gráficos ganharem forma. 📈</div>;
  return (
    <>
      <p className="muted small">As faixas vermelhas mostram períodos de crise.</p>
      <div className="cols-2">
        <Chart title="🛒 Inflação (12 meses)" hint="Quanto os preços subiram em um ano." keys={[["inflacao", "Inflação %"]]} />
        <Chart title="🏦 Juros e crescimento" hint="Juros altos esfriam a economia." keys={[["juros", "Juros %"], ["pib", "PIB %"]]} />
        <Chart title="👷 Desemprego e confiança" hint="Quando o emprego cai, o consumo cai junto." keys={[["desemprego", "Desemprego %"], ["confianca", "Confiança"]]} />
        <Chart title="💵 Dólar (R$)" hint="Dólar mais caro encarece o que vem de fora." keys={[["dolar", "Dólar"]]} />
        <Chart title="📊 Mercados (base 100)" hint="Índices simulados das classes de ativos." keys={[["acoes", "Ações"], ["fiis", "FIIs"], ["cripto", "Cripto"], ["imoveis", "Imóveis"]]} />
        <Chart title="🧺 Custo de vida (índice)" hint="Índice geral de preços acumulado desde o início." keys={[["iprice", "Preços"]]} />
      </div>
    </>
  );
}

function Crises({ eco }: { eco: Economy }) {
  const [open, setOpen] = useState<number | null>(null);
  const cat = (c: Crisis) => Object.entries(c.sectors).sort((a, b) => a[1] - b[1]).slice(0, 4).map(([k, v]) => `${k.toLowerCase().replace("_", " ")} ${Math.round(v * c.peak)}%`).join(" · ");
  return (
    <>
      <section className="card stack"><h2>🚨 Histórico de crises</h2>
        {eco.crises.length === 0 && <p className="muted small">Nenhuma crise até agora. Elas são raras: podem passar muitos anos sem nenhuma.</p>}
        {eco.crises.map((c) => (
          <div key={c.id} className="card stack"><div className="row between"><b>{c.label}</b><span className={`chip ${c.status === "ACTIVE" ? "down" : "up"}`}>{c.status === "ACTIVE" ? `em andamento (${PHASE[c.phase]})` : "terminou"}</span></div>
            <p className="small">{CRISIS_HELP[c.type]} · {fmtMonth(c.start_month)} → {c.end_month ? fmtMonth(c.end_month) : "…"} · pico {Math.round(c.peak * 100)}%</p>
            <p className="muted small">Setores mais atingidos: {cat(c)}</p>
            <button className="btn ghost small" onClick={() => setOpen(open === c.id ? null : c.id)}>{open === c.id ? "Esconder" : "Ver como evoluiu"}</button>
            {open === c.id && <div className="bars" aria-label="intensidade">{c.path.map((p) => <div key={p.m} title={`${p.m}: ${Math.round(p.i * 100)}% (${PHASE[p.phase]})`} style={{ height: `${Math.max(3, p.i * 100)}%` }} />)}</div>}
            {open === c.id && Object.keys(c.triggers).length > 0 && <p className="muted small">O que contribuiu: {Object.entries(c.triggers).map(([k, v]) => `${k} (${v})`).join(", ")}</p>}</div>))}
      </section>
      <EventList title="Acontecimentos em andamento" events={eco.active} />
      <EventList title="Acontecimentos passados" events={eco.past.slice(0, 20)} />
    </>
  );
}

function Prices({ eco }: { eco: Economy }) {
  const st = eco.state!;
  return (
    <section className="card stack"><h2>🧺 Preços por categoria</h2>
      <p className="muted small">Cada categoria tem o seu índice. 1,0000 = preço do início da partida.</p>
      <div className="table-wrap"><table><thead><tr><th>Categoria</th><th className="r">Índice acumulado</th><th className="r">Variação no mês</th></tr></thead>
        <tbody>{[{ key: "geral", label: "Geral (custo de vida)" }, ...eco.categories].map((c) => { const ch = st.monthly_changes[c.key] ?? 0; return (
          <tr key={c.key}><td>{c.label}</td><td className="r num">{(st.indices[c.key] ?? 1).toFixed(4)}</td><td className={`r num ${ch > 0.6 ? "tone-down" : ch < 0 ? "tone-up" : ""}`}>{ch.toFixed(2)}%</td></tr>); })}</tbody></table></div></section>
  );
}

function Config({ eco, reload }: { eco: Economy; reload: () => void }) {
  const [p, setP] = useState<SimParams>(eco.params);
  const [msg, setMsg] = useState<string | null>(null);
  const save = async () => { try { await sim.ecoParams(p); setMsg("Salvo! Vale a partir do próximo mês."); reload(); } catch (e) { setMsg(errMsg(e)); } };
  const F = (k: keyof SimParams, label: string, hint: string) => (
    <label className="stack"><span>{label}: <b>{p[k].toFixed(1)}×</b></span><input type="range" min={0} max={3} step={0.1} value={p[k]} onChange={(e) => setP({ ...p, [k]: Number(e.target.value) })} /><span className="muted small">{hint}</span></label>);
  return (
    <section className="card stack"><h2>⚙️ Ajustes da simulação</h2>
      <p className="muted small">Controles de dificuldade. 1,0× é o normal. Valem do próximo mês em diante.</p>
      {F("volatility", "Oscilação dos preços", "Quanto os ativos sobem e descem")}{F("event_frequency", "Frequência de acontecimentos", "Eventos aleatórios")}
      {F("crisis_frequency", "Frequência de crises", "0 = sem crises")}{F("crisis_severity", "Gravidade das crises", "Quão fortes elas são")}{F("shock_scale", "Imprevistos da economia", "Ruído dos indicadores")}
      <div className="row"><button className="btn primary" onClick={() => void save()}>Salvar</button>{msg && <span className="small">{msg}</span>}</div>
      <p className="muted small">⚠️ Os preços e as crises daqui são resultado de uma economia simulada, calibrada com ordens de grandeza históricas — não são previsões reais.</p></section>
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
