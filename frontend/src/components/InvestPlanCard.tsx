import { useCallback, useEffect, useMemo, useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { fmtBRL } from "../lib/format";
import { sim, type InvestPlan } from "../services/sim";

const COLORS: Record<string, string> = { FIXED: "#3ee59a", STOCKS: "#ffd23f", ETF: "#4cc9f0", FII: "#c13cff", CRYPTO: "#ff6482" };
const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");

/** Orçamento da carteira de investimentos: quanto investir (recomendado), em quê (gráfico de pizza) e quanto falta por tipo. */
export function InvestPlanCard({ onChange }: { onChange?: () => void }) {
  const [p, setP] = useState<InvestPlan | null>(null);
  const [view, setView] = useState<"month" | "target">("month");
  const [edit, setEdit] = useState<Record<string, string> | null>(null);
  const [goal, setGoal] = useState("");
  const [quiz, setQuiz] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => { sim.investPlan().then((x) => { setP(x); setGoal(x.goal_is_custom ? x.goal_total : ""); }).catch((e) => setErr(errMsg(e))); }, []);
  useEffect(() => { load(); }, [load]);
  const run = async (fn: () => Promise<InvestPlan>) => { setBusy(true); setErr(null); try { setP(await fn()); setEdit(null); onChange?.(); } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); } };
  const slices = useMemo(() => (p?.rows ?? []).map((r) => ({ name: r.label, key: r.key, value: view === "month" ? Number(r.month_amount) : r.target_pct })).filter((s) => s.value > 0), [p, view]);
  if (!p) return err ? <div className="alert">{err}</div> : null;
  const sum = edit ? Object.values(edit).reduce((a, v) => a + (Number(v) || 0), 0) : 100;
  const rec = p.recommended;
  return (
    <section className="card stack">
      <div className="row between"><h2>📊 Carteira de investimentos do mês</h2><span className="chip">Perfil: <b>{p.profile_label}</b></span></div>
      <div className="notice" style={{ margin: 0 }}>💡 <b>Recomendação:</b> investir <b>{fmtBRL(rec.amount)}</b> neste mês (sobra do orçamento: {fmtBRL(rec.surplus)}). <span className="muted">{rec.reason}</span>
        <div className="row" style={{ marginTop: 8 }}>
          <span>Você planejou: <b>{fmtBRL(p.planned_investment)}</b></span>
          <button className="btn primary small" disabled={busy || Number(p.planned_investment) === Number(rec.amount)} onClick={() => void run(sim.investApply)}>Usar o valor recomendado</button></div></div>
      {err && <div className="alert">{err}</div>}
      <div className="seg compact"><button className={view === "month" ? "on" : ""} onClick={() => setView("month")}>Divisão deste mês</button><button className={view === "target" ? "on" : ""} onClick={() => setView("target")}>Carteira-alvo</button></div>
      <div className="cols-2">
        <div style={{ height: 240 }}>
          <ResponsiveContainer><PieChart><Pie data={slices} dataKey="value" nameKey="name" innerRadius={55} outerRadius={95} paddingAngle={2} label={(d) => (view === "month" ? fmtBRL(String(d.value)) : `${d.value}%`)}>
            {slices.map((s) => <Cell key={s.key} fill={COLORS[s.key]} />)}</Pie><Tooltip formatter={(v: number) => (view === "month" ? fmtBRL(String(v)) : `${v}%`)} contentStyle={{ background: "#281e63", border: "2px solid #4d40a8", borderRadius: 12 }} /></PieChart></ResponsiveContainer>
          {slices.length === 0 && <p className="muted small center">Sem valor recomendado neste mês.</p>}</div>
        <ul className="list-plain">{p.rows.map((r) => (
          <li key={r.key}><span><i style={{ display: "inline-block", width: 10, height: 10, borderRadius: 99, background: COLORS[r.key], marginRight: 6 }} />{r.label}</span>
            <b className="num">{view === "month" ? fmtBRL(r.month_amount) : `${r.target_pct}%`}</b></li>))}</ul>
      </div>
      <h3 style={{ margin: "6px 0 0" }}>🎯 Quanto falta para o seu objetivo</h3>
      <div className="row"><label className="row small">Objetivo de dinheiro investido (R$)
        <input style={{ width: 140 }} inputMode="decimal" value={goal} placeholder={p.goal_total} onChange={(e) => setGoal(e.target.value)} /></label>
        <button className="btn ghost small" disabled={busy} onClick={() => void run(() => sim.investSettings({ goal_total: goal || "0" }))}>Salvar objetivo</button>
        <span className="muted small">Investido hoje: <b>{fmtBRL(p.invested_now)}</b> de {fmtBRL(p.goal_total)}</span></div>
      <div className="table-wrap"><table><thead><tr><th>Tipo</th><th className="r">Já tem</th><th className="r">Objetivo</th><th className="r">Falta</th><th>Progresso</th></tr></thead>
        <tbody>{p.rows.filter((r) => r.target_pct > 0).map((r) => (
          <tr key={r.key}><td>{r.label} <span className="muted small">({r.target_pct}%)</span></td><td className="r num">{fmtBRL(r.current)}</td><td className="r num">{fmtBRL(r.target_amount)}</td>
            <td className="r num">{fmtBRL(r.missing)}</td><td style={{ minWidth: 120 }}><div className="meter-bar"><i style={{ width: `${r.filled_pct}%`, background: COLORS[r.key] }} /></div></td></tr>))}</tbody></table></div>
      <div className="row">
        <button className="btn ghost small" onClick={() => setQuiz(true)}>🧪 Descobrir meu perfil de investidor</button>
        <button className="btn ghost small" onClick={() => setEdit(Object.fromEntries(p.rows.map((r) => [r.key, String(r.target_pct)])))}>✏️ Editar carteira</button></div>
      <p className="muted small" style={{ margin: 0 }}>{p.profile_text}</p>
      <details className="card"><summary><b>Em que eu quero investir</b></summary>
        <div className="row" style={{ marginTop: 8 }}>{p.classes.map((c) => (
          <label key={c.key} className="check"><input type="checkbox" checked={p.wanted.includes(c.key) || c.key === "FIXED"} disabled={c.key === "FIXED" || busy}
            onChange={(e) => void run(() => sim.investSettings({ wanted: e.target.checked ? [...p.wanted, c.key] : p.wanted.filter((w) => w !== c.key) }))} />{c.label}</label>))}</div>
        <div className="row" style={{ marginTop: 8 }}>{p.profiles.map((x) => <button key={x.key} className={`btn small ${p.profile === x.key ? "primary" : "ghost"}`} disabled={busy} title={x.text} onClick={() => void run(() => sim.investSettings({ profile: x.key }))}>{x.label}</button>)}</div>
      </details>
      {edit && (
        <div className="card stack"><b>Editar a carteira-alvo (precisa somar 100%)</b>
          <div className="row">{p.rows.map((r) => <label key={r.key} className="row small">{r.label}<input style={{ width: 70 }} inputMode="decimal" value={edit[r.key]} onChange={(e) => setEdit({ ...edit, [r.key]: e.target.value })} />%</label>)}</div>
          <div className="row"><span className={`small ${Math.abs(sum - 100) < 0.01 ? "tone-up" : "tone-down"}`}>Soma: {sum}%</span>
            <button className="btn primary small" disabled={busy || Math.abs(sum - 100) > 0.01} onClick={() => void run(() => sim.investSettings({ alloc: Object.fromEntries(Object.entries(edit).map(([k, v]) => [k, Number(v) || 0])) }))}>Salvar carteira</button>
            <button className="btn ghost small" onClick={() => setEdit(null)}>Cancelar</button></div></div>)}
      {quiz && <QuizModal onClose={() => setQuiz(false)} onDone={(x) => { setP(x); setQuiz(false); onChange?.(); }} />}
    </section>
  );
}

function QuizModal({ onClose, onDone }: { onClose: () => void; onDone: (p: InvestPlan) => void }) {
  const [qs, setQs] = useState<{ text: string; options: string[] }[]>([]);
  const [ans, setAns] = useState<number[]>([]);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { sim.investQuiz().then((r) => { setQs(r.questions); setAns(Array(r.questions.length).fill(-1)); }).catch((e) => setErr(errMsg(e))); }, []);
  const done = ans.length > 0 && ans.every((a) => a >= 0);
  return (
    <div className="modal-back" role="dialog" aria-modal="true" aria-label="Teste de perfil de investidor">
      <div className="card modal" style={{ maxWidth: 640 }}>
        <div className="row between"><h2>🧪 Qual é o seu perfil de investidor?</h2><button className="link-btn" onClick={onClose}>fechar ✕</button></div>
        <p className="muted small">Responda com sinceridade: não existe resposta certa. O resultado ajusta a sua carteira.</p>
        {err && <div className="alert">{err}</div>}
        {qs.map((q, i) => (
          <fieldset key={i} className="stack" style={{ border: 0, padding: 0 }}><legend><b>{i + 1}. {q.text}</b></legend>
            <div className="stack">{q.options.map((o, j) => <label key={j} className="check"><input type="radio" name={`q${i}`} checked={ans[i] === j} onChange={() => setAns(ans.map((a, k) => (k === i ? j : a)))} />{o}</label>)}</div></fieldset>))}
        <button className="btn primary" disabled={!done} onClick={() => void sim.investQuizSubmit(ans).then(onDone).catch((e) => setErr(errMsg(e)))}>Ver o meu perfil</button>
      </div>
    </div>
  );
}
