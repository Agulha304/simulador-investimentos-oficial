import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { StatCard } from "../components/StatCard";
import { fmtMonth } from "../lib/format";
import { sim, type CountryRow, type Crisis, type WorldEvent, type EcoEvent, type Economy } from "../services/sim";

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
type Tab = "now" | "charts" | "crises" | "prices" | "countries";

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
        {([["now", "Hoje"], ["charts", "Gráficos"], ["crises", `Crises e eventos (${eco.crises.length})`], ["prices", "Preços"], ["countries", "🌐 Países e câmbio"]] as [Tab, string][]).map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {tab === "now" && st && <Now eco={eco} decide={decide} />}
      {tab === "now" && !st && <div className="card muted">Sem dados ainda.</div>}
      {tab === "charts" && <Charts eco={eco} />}
      {tab === "crises" && <Crises eco={eco} />}
      {tab === "prices" && st && <Prices eco={eco} />}
      {tab === "countries" && <Countries />}
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

function EventList({ title, events }: { title: string; events: EcoEvent[] }) {
  return (
    <section className="card stack"><h2>{title}</h2>
      {events.length === 0 ? <p className="muted small">Nenhum.</p> : <ul className="list-plain">{events.map((e) => (
        <li key={e.id}><span><b>{e.name}</b> <span className={`chip ${e.positive ? "up" : "down"}`}>{e.positive ? "favorável" : "adverso"}</span> <span className="chip">{CAT[e.category]} · afeta {SCOPE[e.scope]}</span><br /><span className="muted small">{e.outcome ?? e.description}</span></span>
          <span className="muted small">{fmtMonth(e.start_month)} → {fmtMonth(e.end_month)}</span></li>))}</ul>}
    </section>
  );
}

function Spark({ rows }: { rows: { rate: string }[] }) {
  if (rows.length < 2) return null;
  const v = rows.map((r) => Number(r.rate)), lo = Math.min(...v), hi = Math.max(...v), w = 120, h = 28;
  const pts = v.map((x, i) => `${(i / (v.length - 1)) * w},${h - ((x - lo) / (hi - lo || 1)) * (h - 4) - 2}`).join(" ");
  return <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} role="img" aria-label="Câmbio dos últimos 24 meses"><polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>;
}

/** Economia de todos os países do jogo: quanto vale a moeda em reais, inflação, impostos e custo de vida. */
function Countries() {
  const [rows, setRows] = useState<CountryRow[] | null>(null);
  const [events, setEvents] = useState<WorldEvent[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { sim.economyCountries().then((r) => { setRows(r.countries); setEvents(r.events); }).catch((e) => setErr(errMsg(e))); }, []);
  if (err) return <div className="alert">{err}</div>;
  if (!rows) return <div className="muted">Carregando países…</div>;
  const money = (v: string, d = 4) => `R$ ${Number(v).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: d })}`;
  return (
    <section className="card stack">
      <h2>🌐 Economia dos países</h2>
      <p className="muted small" style={{ margin: 0 }}>Economias <b>simuladas</b> (nada vem da vida real): cada partida sorteia inflação, juros, crescimento, câmbio e crises de cada país. O câmbio responde à inflação, aos juros e às crises; moedas de países emergentes sofrem mais nas crises mundiais, e as de "porto seguro" sobem. Clique numa linha para ver impostos e custo de vida.</p>
      <div className="table-wrap"><table>
        <thead><tr><th>País</th><th>Situação</th><th>Moeda</th><th className="r">Cotação (R$)</th><th className="r">12 meses</th><th>Histórico</th><th className="r">Inflação a.a.</th><th className="r">Custo de vida/mês</th></tr></thead>
        <tbody>{rows.map((c) => (
          <Fragment key={c.code}>
            <tr onClick={() => setOpen(open === c.code ? null : c.code)} style={{ cursor: "pointer" }}>
              <td>{c.flag} {c.name}</td><td>{c.crisis ? <span className="chip down" title={c.crisis}>⚠ {c.crisis.split(":")[0]}</span> : <span className="muted small">estável</span>}</td><td>{c.currency}</td><td className="r num">{c.code === "BR" ? "—" : money(c.rate)}</td>
              <td className={`r num ${c.change_12m_pct > 0 ? "tone-down" : c.change_12m_pct < 0 ? "tone-up" : ""}`}>{c.code === "BR" ? "—" : `${c.change_12m_pct > 0 ? "+" : ""}${c.change_12m_pct.toFixed(1)}%`}</td>
              <td><Spark rows={c.history} /></td><td className="r num">{c.inflation.toFixed(1)}%</td><td className="r num">{money(c.living_brl, 0)}</td>
            </tr>
            {open === c.code && <tr key={`${c.code}-d`}><td colSpan={8}>
              <div className="stats-grid">
                <div className="card"><span className="muted small">Crescimento / juros</span><b className="num">{c.growth?.toFixed(1)}% / {c.interest?.toFixed(1)}%</b></div>
                <div className="card"><span className="muted small">Confiança · demanda · preços</span><b className="num">{c.confidence} · {c.demand?.toFixed(2)} · ×{c.price_level?.toFixed(2)}</b></div>
                <div className="card"><span className="muted small">Imposto de renda (efetivo)</span><b className="num">{c.income_tax}%</b></div>
                <div className="card"><span className="muted small">Imposto sobre lucro de empresas</span><b className="num">{c.corp_tax}%</b></div>
                <div className="card"><span className="muted small">IVA / imposto sobre vendas</span><b className="num">{c.vat}%</b></div>
                <div className="card"><span className="muted small">Encargos patronais</span><b className="num">{((c.burden - 1) * 100).toFixed(0)}%</b></div>
                <div className="card"><span className="muted small">Preços vs. Brasil</span><b className="num">{c.cost_index.toFixed(1)}x</b></div>
                <div className="card"><span className="muted small">Salários vs. Brasil</span><b className="num">{c.wage_index.toFixed(1)}x</b></div>
              </div>
              <p className="small muted" style={{ margin: "8px 0 0" }}>Vida em {c.name} (moeda local, por mês): aluguel {c.living_local.rent?.toLocaleString("pt-BR")}, comida {c.living_local.food?.toLocaleString("pt-BR")}, contas {c.living_local.utilities?.toLocaleString("pt-BR")}, transporte {c.living_local.transport?.toLocaleString("pt-BR")}, saúde {c.living_local.health?.toLocaleString("pt-BR")} · idioma: {c.language}.</p>
            </td></tr>}
          </Fragment>))}</tbody>
      </table></div>
      <h3>⚠ Crises no mundo</h3>
      {events.length === 0 ? <p className="muted small">Nenhuma crise até agora. Elas surgem ao longo do jogo, em países isolados ou no mundo todo.</p> : (
        <ul className="list-plain">{events.slice(0, 14).map((e, i) => (
          <li key={i}><span>{e.flag} {e.label} · {e.start.slice(0, 7)} → {e.end.slice(0, 7)}</span><span className={`chip ${e.active ? "down" : ""}`}>{e.active ? "em andamento" : "encerrada"}</span></li>))}</ul>)}
    </section>
  );
}
