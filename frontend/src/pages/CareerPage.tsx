import { useCallback, useEffect, useState } from "react";
import { StatCard } from "../components/StatCard";
import { Toast } from "../components/Toast";
import { fmtBRL, fmtMonth } from "../lib/format";
import { sim, type CareerHub, type Gig, type HubApplication, type HubJob, type JobOffer } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
const WORK: Record<string, string> = { REDUCED: "Trabalhar menos (menos renda, mais tempo livre)", NORMAL: "Jornada normal", INTENSE: "Trabalhar mais (mais renda, menos tempo livre)" };
type Tab = "now" | "search" | "freela" | "resume";

export function CareerPage() {
  const [c, setC] = useState<CareerHub | null>(null);
  const [tab, setTab] = useState<Tab>("now");
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { sim.career().then(setC).catch((e) => setErr(errMsg(e))); }, []);
  const act = useCallback(async (fn: () => Promise<CareerHub>, ok?: (r: CareerHub) => string | null) => {
    setBusy(true); setErr(null); setNote(null);
    try { const r = await fn(); setC(r); setNote(ok ? ok(r) : null); } catch (e) { setErr(errMsg(e)); sim.career().then(setC).catch(() => undefined); } finally { setBusy(false); }
  }, []);
  if (!c) return err ? <div className="alert">{err}</div> : <div className="muted">Carregando carreira…</div>;
  return (
    <div className="page">
      <header className="page-head"><div><h1>💼 Carreira</h1><p className="muted">Seu trabalho, quanto você ganha, vagas para se candidatar, freelas e o seu currículo. Cursos e faculdades ficam em <b>Educação</b>.</p></div></header>
      {err && <div className="alert">{err}</div>}
      {note && <Toast text={note} onClose={() => setNote(null)} />}
      <div className="seg compact tabs">
        {([["now", "Minha carreira"], ["search", "Procurar emprego"], ["freela", "Freelas"], ["resume", "Currículo"]] as [Tab, string][]).map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {tab === "now" && <Now c={c} busy={busy} act={act} />}
      {tab === "search" && <Search c={c} busy={busy} act={act} />}
      {tab === "freela" && <Freela c={c} busy={busy} act={act} />}
      {tab === "resume" && <Resume c={c} busy={busy} act={act} />}
    </div>
  );
}
type Act = (fn: () => Promise<CareerHub>, ok?: (r: CareerHub) => string | null) => Promise<void>;
type P = { c: CareerHub; busy: boolean; act: Act };

function JobCard({ j, busy, act }: { j: HubJob; busy: boolean; act: Act }) {
  return (
    <div className="card stack">
      <div className="row between"><b>{j.title}</b><span className={`chip ${j.kind === "CLT" ? "up" : ""}`}>{j.kind}{j.status === "PENDING" ? " · começa " + fmtMonth(j.since) : ""}</span></div>
      <span className="muted small">{j.employer} · {j.field_label} · nível {j.level_name.toLowerCase()} · desde {fmtMonth(j.since)}{j.until ? ` até ${fmtMonth(j.until)}` : ""}</span>
      <span>Salário líquido: <b className="num">{fmtBRL(j.net)}</b>/mês</span>
      <ul className="list-plain small">{j.perks.map((p) => <li key={p}><span>✔ {p}</span></li>)}</ul>
      {j.hours > 0 && <span className="muted small">⏱ Consome {j.hours}h livres por mês.</span>}
      {j.status === "ACTIVE" && !j.can_raise && j.raise_note && <span className="muted small">📈 Aumento: {j.raise_note}{j.raise_ready_in ? ` (faltam ${j.raise_ready_in} mês(es))` : ""}.</span>}
      <div className="row">
        <label className="check"><input type="checkbox" checked={j.in_resume} disabled={busy} onChange={(e) => void act(() => sim.careerResume("job", j.id, e.target.checked))} />Mostrar no currículo</label>
        {j.status === "ACTIVE" && (
          <button className="btn primary small" disabled={busy || !j.can_raise} title={j.can_raise ? "Pedir aumento neste emprego" : (j.raise_note ?? "")}
            onClick={() => void act(() => sim.careerAskRaise(j.id), (r) => r.raise_result ? (r.raise_result.granted ? "🎉 " : "😕 ") + r.raise_result.text : null)}>Pedir aumento</button>)}
        {j.status !== "ENDED" && <button className="btn danger small" disabled={busy} onClick={() => window.confirm(`Pedir demissão de ${j.title}? Você perde esse salário.`) && void act(() => sim.careerQuit(j.id), () => "Você pediu demissão.")}>Pedir demissão</button>}
      </div>
    </div>
  );
}

function Now({ c, busy, act }: P) {
  const cur = c.jobs.filter((j) => j.status !== "ENDED");
  const old = c.jobs.filter((j) => j.status === "ENDED");
  return (
    <>
      <div className="stat-grid">
        <StatCard label="Profissão (área)" value={c.field.label ? `${c.field.emoji} ${c.field.label}` : "—"} sub={c.field.outlook ?? ""} />
        <StatCard label="Salário atual (todos os empregos)" value={fmtBRL(c.salary)} sub={cur.length === 0 ? "você está sem emprego" : `${cur.length} emprego(s)`} />
        <StatCard label="Perspectiva de aumento" value={c.field.growth_pct != null ? `~${c.field.growth_pct}% ao ano` : "—"} sub={c.field.next_raise ? `próximo reajuste em ${fmtMonth(c.field.next_raise)}` : ""} />
        <StatCard label="FGTS acumulado" value={fmtBRL(c.fgts_balance)} sub="só no emprego CLT" />
      </div>
      <section className="card stack">
        <h2>⏳ Trabalhar mais ou menos</h2>
        <p className="muted small">Mais horas rendem mais, mas cansam e tiram tempo da vida pessoal. Tempo livre neste mês: <b>{c.free_hours}h</b>.</p>
        <div className="seg compact">{c.work_options.map((o) => <button key={o} className={c.work_level === o ? "on" : ""} disabled={busy} onClick={() => void act(() => sim.careerWork(o))}>{WORK[o]}</button>)}</div>
      </section>
      <section className="card stack">
        <h2>📈 Reconhecimento e aumento</h2>
        <div className="row"><span style={{ width: 150 }}>Mérito no trabalho</span><div className="meter-bar" style={{ flex: 1 }}><i style={{ width: `${c.merit}%` }} /></div><b className="num">{c.merit}/{c.merit_needed}+</b></div>
        <p className="muted small" style={{ margin: 0 }}>Trabalhar bastante (jornada intensa) e tomar boas decisões no trabalho acumula mérito. Com {c.merit_needed} ou mais, a empresa pode dar um aumento por conta própria. Você também pode pedir: a chance hoje é de <b>{c.raise_chance}%</b> e depende do seu mérito. O pedido é feito em cada emprego CLT, no botão <b>Pedir aumento</b> do cartão dele (a cada 6 meses por emprego; no PJ você renegocia ao trocar de cliente).</p>
      </section>
      <h2>Empregos atuais</h2>
      {cur.length === 0 && <p className="muted">Nenhum emprego no momento. Use a aba <b>Procurar emprego</b>.</p>}
      <div className="cols-2">{cur.map((j) => <JobCard key={j.id} j={j} busy={busy} act={act} />)}</div>
      {Number(c.fgts_balance) > 0 && (
        <section className="card row between"><span>💰 FGTS: <b>{fmtBRL(c.fgts_balance)}</b> — o saque só é liberado quando você não tem emprego CLT ativo.</span>
          <button className="btn ghost small" disabled={busy || !c.fgts_can_withdraw} onClick={() => void act(sim.careerFgts, () => "FGTS sacado: o valor entra no orçamento do mês.")}>Sacar FGTS</button></section>)}
      <h2>Histórico de empregos</h2>
      {old.length === 0 ? <p className="muted">Você ainda não saiu de nenhum emprego.</p> : <div className="cols-2">{old.map((j) => <JobCard key={j.id} j={j} busy={busy} act={act} />)}</div>}
    </>
  );
}

function Search({ c, busy, act }: P) {
  const [field, setField] = useState(c.field.key ?? "comercio");
  const [data, setData] = useState<{ score: number; offers: JobOffer[] } | null>(null);
  const [pick, setPick] = useState<HubApplication | null>(null);
  const [kind, setKind] = useState<"CLT" | "PJ">("CLT");
  const load = useCallback(() => { sim.careerOffers(field).then(setData).catch(() => setData(null)); }, [field]);
  useEffect(() => { load(); }, [load, c.applications.length]);
  const apply = (o: JobOffer) => act(() => sim.careerApply(field, o.key), (r) => r.result?.status === "APPROVED" ? `🎉 Aprovado(a) para ${r.result.title}! Aceite a vaga abaixo.` : `Não foi dessa vez: ${r.result?.title} escolheu outro candidato.`);
  return (
    <>
      <section className="card stack">
        <div className="row"><label className="row">Área em que quero trabalhar
          <select value={field} onChange={(e) => setField(e.target.value)}>{c.fields.map((f) => <option key={f.key} value={f.key}>{f.emoji} {f.label}</option>)}</select></label>
          <span className="chip">Seu currículo nessa área: <b>{data?.score ?? 0}</b> pontos</span><span className="muted small">Candidaturas restantes no mês: {c.applications_left} (cada uma usa {c.rules.apply_hours}h)</span></div>
        <p className="muted small" style={{ margin: 0 }}>Vagas são raras (poucas por mês em cada área) e mudam todo mês. Quanto mais cursos, faculdade e experiência <b>na área</b> estiverem no seu currículo, maior a chance de ser aprovado.</p>
      </section>
      <div className="cols-2">{(data?.offers ?? []).map((o) => (
        <div key={o.key} className="card stack">
          <div className="row between"><b>{o.title}</b><span className="chip">{o.level_name}</span></div>
          <span className="muted small">{o.employer} · {o.field_label} · pede ~{o.need} pontos de currículo</span>
          <span className="small">CLT: <b>{fmtBRL(String(o.clt.net))}</b> líquido (+13º, férias, FGTS{o.clt.vr ? `, VR ${fmtBRL(String(o.clt.vr))}` : ""}{o.clt.health_plan ? ", plano de saúde" : ""})<br />PJ: <b>{fmtBRL(String(o.pj.net))}</b> no bolso, sem benefícios</span>
          <div className="meter-bar"><i style={{ width: `${o.chance}%`, background: o.chance >= 60 ? "#3ee59a" : o.chance >= 30 ? "#ffd23f" : "#ff6482" }} /></div>
          <span className="small">Chance de aprovação: <b>{o.chance}%</b></span>
          <div><button className="btn primary small" disabled={busy || !!o.applied || c.applications_left <= 0} onClick={() => void apply(o)}>{o.applied ? (o.applied === "REJECTED" ? "Reprovado(a)" : "Candidatura feita") : "Candidatar-me"}</button></div>
        </div>))}
        {data && data.offers.length === 0 && <p className="muted">Nenhuma vaga aberta nessa área neste mês. Tente outra área ou volte no mês que vem.</p>}
      </div>
      <h2>Minhas candidaturas do mês</h2>
      {c.applications.length === 0 ? <p className="muted">Nenhuma candidatura ainda.</p> : (
        <ul className="list-plain">{c.applications.map((a) => (
          <li key={a.id}><span>{a.title} — {a.employer} <span className="muted small">({a.chance}% de chance)</span></span>
            {a.status === "APPROVED" ? <button className="btn primary small" onClick={() => setPick(a)}>✅ Aprovado — aceitar</button> : <span className={`chip ${a.status === "ACCEPTED" ? "up" : "down"}`}>{a.status === "ACCEPTED" ? "Aceita" : "Reprovado(a)"}</span>}</li>))}</ul>)}
      {pick && (
        <div className="modal-back" role="dialog" aria-modal="true" aria-label="Aceitar vaga">
          <div className="card modal">
            <div className="row between"><h2>Aceitar: {pick.title}</h2><button className="link-btn" onClick={() => setPick(null)}>fechar ✕</button></div>
            <p className="muted">{pick.offer.employer}. Escolha como você será contratado(a):</p>
            <div className="seg"><button className={kind === "CLT" ? "on" : ""} onClick={() => setKind("CLT")}>CLT — {fmtBRL(String(pick.offer.clt.net))}</button><button className={kind === "PJ" ? "on" : ""} onClick={() => setKind("PJ")}>PJ — {fmtBRL(String(pick.offer.pj.net))}</button></div>
            <p className="small">{kind === "CLT" ? "CLT: 13º salário, férias + 1/3, FGTS e benefícios. Só um emprego CLT por vez: este substitui o atual." : `PJ: ganha cerca de ${c.rules.pj_premium_pct}% a mais no bolso, sem 13º, férias, FGTS ou benefícios. Você pode manter outro emprego (um PJ extra consome ${c.rules.pj_extra_hours}h livres por mês).`}</p>
            <button className="btn primary" disabled={busy} onClick={() => { const id = pick.id; setPick(null); void act(() => sim.careerAccept(id, kind), () => "Contratado(a)! O novo salário começa no mês que vem."); }}>Aceitar a vaga</button>
          </div>
        </div>)}
    </>
  );
}

function Freela({ c, busy, act }: P) {
  const [field, setField] = useState(c.field.key ?? "comercio");
  const [data, setData] = useState<{ free_hours: number; gigs: Gig[]; score: number } | null>(null);
  useEffect(() => { sim.freelance(field).then(setData).catch(() => setData(null)); }, [field, c.free_hours]);
  return (
    <>
      <section className="card stack">
        <div className="row"><label className="row">Área do freela
          <select value={field} onChange={(e) => setField(e.target.value)}>{c.fields.map((f) => <option key={f.key} value={f.key}>{f.emoji} {f.label}</option>)}</select></label>
          <span className="chip">Tempo livre: <b>{data?.free_hours ?? c.free_hours}h</b></span></div>
        <p className="muted small" style={{ margin: 0 }}>Freelas pagam por trabalho feito, em qualquer área, mas precisam de tempo livre e de alguém querer contratar você: com pouco currículo na área, aparecem menos pedidos.</p>
      </section>
      {data && data.gigs.length === 0 && <p className="muted">Ninguém quis contratar você para freelas nessa área neste mês. Melhore o currículo ou tente outra área.</p>}
      <div className="cols-2">{(data?.gigs ?? []).map((g) => (
        <div key={g.key} className="card stack"><b>{g.title}</b><span className="muted small">{g.field_label} · {g.hours}h</span><span>Pagamento: <b className="num">{fmtBRL(g.pay)}</b></span>
          <div><button className="btn primary small" disabled={busy || g.taken || g.hours > (data?.free_hours ?? 0)} onClick={() => void act(() => sim.freelanceAccept(field, g.key), () => "Freela aceito: o pagamento entra neste mês.")}>{g.taken ? "Já aceito" : g.hours > (data?.free_hours ?? 0) ? "Sem tempo livre" : "Aceitar freela"}</button></div></div>))}</div>
    </>
  );
}

function Resume({ c }: P) {
  const rows = Object.entries(c.resume_scores).sort((a, b) => b[1].score - a[1].score);
  return (
    <>
      <section className="card stack"><h2>📄 Seu currículo por área</h2>
        <p className="muted small">A pontuação vem de cursos, faculdades e empregos que você deixou <b>marcados para aparecer no currículo</b> (marque em Educação e nos empregos). Experiência e estudo na área da vaga valem mais.</p>
        {rows.map(([k, v]) => <div key={k} className="row"><span style={{ width: 200 }}>{v.emoji} {v.label}</span><div className="meter-bar" style={{ flex: 1 }}><i style={{ width: `${v.score}%` }} /></div><b className="num">{v.score}</b></div>)}</section>
      <section className="card stack"><h2>O que conta na sua área atual</h2>
        {c.resume_items.length === 0 ? <p className="muted">Nada ainda. Faça cursos e ganhe experiência!</p> : <ul className="list-plain">{c.resume_items.map((i, n) => <li key={n}><span>{i.kind === "job" ? "💼" : "🎓"} {i.name}</span><b>+{i.points}</b></li>)}</ul>}</section>
    </>
  );
}
