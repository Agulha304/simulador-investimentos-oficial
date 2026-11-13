import { Fragment, useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Block, type Lesson, type QuizResult } from "../services/api";

function inline(text: string): ReactNode {
  return text.split("**").map((part, i) => (i % 2 ? <b key={i}>{part}</b> : <Fragment key={i}>{part}</Fragment>));
}

function BlockView({ b }: { b: Block }) {
  const [kind] = b;
  if (kind === "h") return <h3>{b[1] as string}</h3>;
  if (kind === "p") return <p>{inline(b[1] as string)}</p>;
  if (kind === "ul") return <ul>{(b[1] as string[]).map((t, i) => <li key={i}>{inline(t)}</li>)}</ul>;
  if (kind === "tip") return <div className="callout tip"><b>Dica</b> {inline(b[1] as string)}</div>;
  if (kind === "warn") return <div className="callout warn"><b>Atenção</b> {inline(b[1] as string)}</div>;
  if (kind === "formula") return <pre className="formula">{b[1] as string}</pre>;
  if (kind === "table") {
    const headers = b[1] as string[]; const rows = b[2] as string[][];
    return <div className="table-wrap"><table><thead><tr>{headers.map((h) => <th key={h}>{h}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} style={{ whiteSpace: "normal" }}>{c}</td>)}</tr>)}</tbody></table></div>;
  }
  if (kind === "sim") return <p><Link className="btn ghost small" to={b[1] as string}>{b[2] as string} →</Link></p>;
  return null;
}

export function LessonPage() {
  const id = useParams().id ?? "";
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [answers, setAnswers] = useState<(number | null)[]>([]);
  const [result, setResult] = useState<QuizResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setLesson(null); setResult(null); setError(null);
    api.lesson(id).then((l) => { setLesson(l); setAnswers(l.quiz.map(() => null)); window.scrollTo({ top: 0 }); })
      .catch((e: Error) => setError(e.message));
  }, [id]);

  if (!lesson) return error ? <div className="alert">{error}</div> : <div className="muted">Carregando a aula…</div>;
  const ready = answers.every((a) => a !== null);

  async function submit() {
    setBusy(true); setError(null);
    try { setResult(await api.submitQuiz(id, answers as number[])); }
    catch (e) { setError(e instanceof Error ? e.message : "Erro"); }
    finally { setBusy(false); }
  }
  const retry = () => { setResult(null); setAnswers(lesson.quiz.map(() => null)); };
  const nextId = result?.next_lesson_id ?? lesson.next_id;

  return (
    <div className="page lesson">
      <nav className="muted small"><Link to="/aulas">Aulas</Link> › {lesson.module_title}</nav>
      <header><h1>{lesson.title}</h1><p className="muted small">{lesson.minutes} min de leitura{lesson.completed ? " · aula concluída ✓" : ""}</p></header>

      <article className="card prose">{lesson.blocks.map((b, i) => <BlockView key={i} b={b} />)}</article>

      <section className="card quiz">
        <h2>Quiz da aula</h2>
        <p className="muted small">Acerte pelo menos 2 de 3 para concluir a aula. Você pode tentar quantas vezes quiser.</p>
        {lesson.quiz.map((q, qi) => (
          <fieldset key={qi} disabled={!!result}>
            <legend>{qi + 1}. {q.text}</legend>
            {q.options.map((o, oi) => {
              const r = result?.results[qi];
              const cls = !r ? "" : oi === r.correct_index ? " right" : answers[qi] === oi ? " wrong" : "";
              return (
                <label key={oi} className={`opt${cls}`}>
                  <input type="radio" name={`q${qi}`} checked={answers[qi] === oi} onChange={() => setAnswers(answers.map((a, k) => (k === qi ? oi : a)))} />
                  <span>{o}{r && oi === r.correct_index && <b> ✓ correta</b>}{r && answers[qi] === oi && oi !== r.correct_index && <b> ✗ sua resposta</b>}</span>
                </label>);
            })}
            {result && <p className="muted small expl">{result.results[qi].explanation}</p>}
          </fieldset>))}

        {error && <div className="alert">{error}</div>}
        {!result ? <button className="btn primary" disabled={!ready || busy} onClick={submit}>{busy ? "Corrigindo…" : "Enviar respostas"}</button> : (
          <div className={result.passed ? "ok" : "alert"}>
            <b>{result.score}% de acerto.</b> {result.passed ? "Aula concluída!" : "Ainda não foi desta vez: releia a aula e tente de novo."}
            <div className="actions">
              {!result.passed && <button className="btn ghost small" onClick={retry}>Tentar de novo</button>}
              {nextId && result.passed && <Link className="btn primary small" to={`/aulas/${nextId}`}>Próxima aula →</Link>}
              <Link className="btn ghost small" to="/aulas">Voltar às aulas</Link>
            </div>
          </div>)}
      </section>

      <div className="lesson-nav">
        {lesson.prev_id ? <Link to={`/aulas/${lesson.prev_id}`}>← Aula anterior</Link> : <span />}
        {lesson.next_id ? <Link to={`/aulas/${lesson.next_id}`}>Próxima aula →</Link> : <span />}
      </div>
    </div>
  );
}
