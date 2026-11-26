import { useCallback, useEffect, useState } from "react";
import { Toast } from "../components/Toast";
import { fmtBRL, fmtMonth } from "../lib/format";
import { sim, type Education, type University } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
const ST: Record<string, string> = { ACTIVE: "Cursando", DONE: "Concluído", DROPPED: "Abandonado" };

export function EducationPage() {
  const [e, setE] = useState<Education | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pickField, setPickField] = useState<string | null>(null);
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
      {pickField && <UniversityPicker field={pickField} busy={busy} onClose={() => setPickField(null)}
        onPick={(uni) => { const f = pickField; setPickField(null); setBusy(true); setErr(null); setNote(null);
          sim.lifeDegree(f, uni).then((r) => setNote(r.admission && !r.admission.admitted ? `Você não passou no vestibular desta faculdade (chance era ${Math.round(r.admission.chance * 100)}%). Tente outra ou espere 12 meses.` : "Você passou e começou a faculdade!"))
            .catch((x) => setErr(errMsg(x))).finally(() => { setBusy(false); load(); }); }} />}
      <header className="page-head"><div><h1>🎓 Educação</h1><p className="muted">Cursos e faculdades custam dinheiro (mensalidade no orçamento) e tempo livre ({e.free_hours}h sobrando no mês). Depois de concluir, você escolhe se entra no currículo.</p></div></header>
      {err && <div className="alert">{err}</div>}
      {note && <Toast text={note} onClose={() => setNote(null)} />}
      <h2>Faculdades</h2>
      {e.studying && <div className="notice">Cursando agora: {e.degrees.find((d) => d.key === e.studying!.field)?.degree} — {e.studying.progress} de {e.studying.total} meses.</div>}
      <div className="cols-2">{e.degrees.map((d) => (
        <div key={d.key} className="card stack"><b>{d.emoji} {d.degree}</b><span className="muted small">{d.months} meses · ~{fmtBRL(String(d.cost_month))}/mês · {d.hours}h/mês · salário +{d.premium_pct}% ao mudar para a área</span>
          <div>{d.status === "DONE" ? <span className="chip up">🎓 Formado</span> : d.status === "ACTIVE" ? <button className="btn danger small" disabled={busy} onClick={() => window.confirm("Trancar a faculdade? O que já estudou fica perdido.") && void act(sim.lifeDegreeDrop, "Faculdade trancada.")}>Cursando — trancar</button>
            : <button className="btn primary small" disabled={busy || !!e.studying} onClick={() => setPickField(d.key)}>{e.studying ? "Termine a atual primeiro" : "Fazer faculdade"}</button>}</div></div>))}</div>
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

/** Escolha da faculdade: ranking real (RUF/QS), concorrência, mensalidade, carga e peso no currículo; só aparecem os cursos que a instituição oferece. */
function UniversityPicker({ field, busy, onClose, onPick }: { field: string; busy: boolean; onClose: () => void; onPick: (uni: string) => void }) {
  const [list, setList] = useState<University[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { sim.lifeUniversities(field).then((r) => setList(r.universities)).catch((e) => setErr(errMsg(e))); }, [field]);
  return (
    <div className="modal-back" role="dialog" aria-modal="true" aria-label="Escolher faculdade">
      <div className="card modal" style={{ maxWidth: 760, maxHeight: "86vh", overflow: "auto" }}>
        <div className="row between"><h2>Escolha a faculdade</h2><button className="link-btn" onClick={onClose}>fechar ✕</button></div>
        <p className="muted small">Faculdades mais fortes valem mais pontos no currículo e elevam o prêmio salarial, mas passar é mais difícil (vestibular anual). As públicas quase não cobram mensalidade.</p>
        {err && <div className="alert">{err}</div>}
        {!list ? <div className="muted">Carregando…</div> : list.map((u) => { const f = u.fields[0]; return (
          <div key={u.key} className="card stack" style={{ marginBottom: 8 }}>
            <div className="row between"><b>{u.ranking < 99 ? `#${u.ranking} ` : ""}{u.name}</b><span className="chip">{u.kind === "PUBLICA" ? "Pública" : "Particular"}{u.state !== "—" ? ` · ${u.state}` : ""}</span></div>
            <span className="muted small">{f.degree} · {f.months} meses · {f.monthly_cost ? `${fmtBRL(String(f.monthly_cost))}/mês` : "sem mensalidade"} · {f.hours}h livres/mês · diploma vale <b>+{f.points} pontos</b> no currículo (salário ×{u.salary_premium_factor})</span>
            <span className="small">Chance de passar: <b>{Math.round(f.chance * 100)}%</b>{f.wait_months > 0 ? ` — reprovado(a): nova tentativa em ${f.wait_months} mês(es)` : ""}</span>
            <div><button className="btn primary small" disabled={busy || f.wait_months > 0} onClick={() => onPick(u.key)}>{u.key === "aberta" ? "Matricular" : "Prestar vestibular"}</button></div>
          </div>); })}
      </div>
    </div>
  );
}
