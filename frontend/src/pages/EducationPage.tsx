import { useCallback, useEffect, useState } from "react";
import { Toast } from "../components/Toast";
import { fmtBRL, fmtMonth } from "../lib/format";
import { sim, type Education } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
const ST: Record<string, string> = { ACTIVE: "Cursando", DONE: "Concluído", DROPPED: "Abandonado" };

export function EducationPage() {
  const [e, setE] = useState<Education | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => { sim.education().then(setE).catch((x) => setErr(errMsg(x))); }, []);
  useEffect(() => { load(); }, [load]);
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true); setErr(null); setNote(null);
    try { await fn(); setNote(ok); } catch (x) { setErr(errMsg(x)); } finally { setBusy(false); load(); }
  };
  if (!e) return err ? <div className="alert">{err}</div> : <div className="muted">Carregando educação…</div>;
  const general = e.courses.filter((c) => c.field === "geral");
  const byField = e.courses.filter((c) => c.field !== "geral");
  const Course = ({ c }: { c: Education["courses"][number] }) => (
    <div className="card stack">
      <b>{c.name}</b><span className="muted small">{c.field_label} · {c.months} meses · {fmtBRL(String(c.cost_month))}/mês · {c.hours}h/mês · +{c.points} pontos no currículo</span>
      <div>{c.status === "DONE" ? <span className="chip up">✅ Concluído</span> : c.status === "ACTIVE" ? <button className="btn danger small" disabled={busy} onClick={() => c.id && window.confirm("Desistir deste curso?") && void act(() => sim.dropCourse(c.id!), "Você desistiu do curso.")}>Cursando — desistir</button>
        : <button className="btn primary small" disabled={busy || c.hours > e.free_hours} onClick={() => void act(() => sim.enrollCourse(c.key), "Matrícula feita! A mensalidade entra no orçamento.")}>{c.hours > e.free_hours ? "Sem tempo livre" : "Fazer curso"}</button>}</div>
    </div>);
  return (
    <div className="page">
      <header className="page-head"><div><h1>🎓 Educação</h1><p className="muted">Cursos e faculdades custam dinheiro (mensalidade no orçamento) e tempo livre ({e.free_hours}h sobrando no mês). Depois de concluir, você escolhe se entra no currículo.</p></div></header>
      {err && <div className="alert">{err}</div>}
      {note && <Toast text={note} onClose={() => setNote(null)} />}
      <h2>Faculdades</h2>
      {e.studying && <div className="notice">Cursando agora: {e.degrees.find((d) => d.key === e.studying!.field)?.degree} — {e.studying.progress} de {e.studying.total} meses.</div>}
      <div className="cols-2">{e.degrees.map((d) => (
        <div key={d.key} className="card stack"><b>{d.emoji} {d.degree}</b><span className="muted small">{d.months} meses · ~{fmtBRL(String(d.cost_month))}/mês · {d.hours}h/mês · salário +{d.premium_pct}% ao mudar para a área</span>
          <div>{d.status === "DONE" ? <span className="chip up">🎓 Formado</span> : d.status === "ACTIVE" ? <button className="btn danger small" disabled={busy} onClick={() => window.confirm("Trancar a faculdade? O que já estudou fica perdido.") && void act(sim.lifeDegreeDrop, "Faculdade trancada.")}>Cursando — trancar</button>
            : <button className="btn primary small" disabled={busy || !!e.studying} onClick={() => void act(() => sim.lifeDegree(d.key), "Você começou a faculdade!")}>{e.studying ? "Termine a atual primeiro" : "Fazer faculdade"}</button>}</div></div>))}</div>
      <h2>Cursos gerais (valem em qualquer área)</h2>
      <div className="cols-2">{general.map((c) => <Course key={c.key} c={c} />)}</div>
      <h2>Cursos por área</h2>
      <div className="cols-2">{byField.map((c) => <Course key={c.key} c={c} />)}</div>
      <h2>📚 Meu histórico de educação</h2>
      {e.history.length === 0 ? <p className="muted">Você ainda não fez nenhum curso.</p> : (
        <div className="table-wrap"><table><thead><tr><th>Curso</th><th>Área</th><th>Período</th><th>Situação</th><th>No currículo</th></tr></thead>
          <tbody>{e.history.map((h) => (
            <tr key={h.id}><td>{h.kind === "DEGREE" ? "🎓 " : ""}{h.name}</td><td>{h.field_label}</td><td>{fmtMonth(h.start)}{h.end ? ` → ${fmtMonth(h.end)}` : ""}</td>
              <td>{ST[h.status]}{h.status === "ACTIVE" ? ` (${h.progress}/${h.months_total})` : ""}</td>
              <td><input type="checkbox" checked={h.in_resume} disabled={busy || h.status !== "DONE"} onChange={(ev) => void act(() => sim.careerResume("education", h.id, ev.target.checked), "Currículo atualizado.")} /></td></tr>))}</tbody></table></div>)}
    </div>
  );
}
