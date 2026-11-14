import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fmtDuration } from "../lib/format";
import { api, type LearnOverview } from "../services/api";

export function LearnPage() {
  const [data, setData] = useState<LearnOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.learn().then(setData).catch((e: Error) => setError(e.message)); }, []);
  const startVideo = data
    ? (data.modules.flatMap((m) => m.lessons).find((l) => l.video_seconds && !l.completed)
      ?? data.modules.flatMap((m) => m.lessons).find((l) => l.video_seconds))?.id ?? null
    : null;
  if (!data) return error ? <div className="alert">{error}</div> : <div className="muted">Carregando as aulas…</div>;

  return (
    <div className="page">
      <header className="page-head"><div><h1>Aulas</h1><p className="muted">Aprenda a investir do zero, com exemplos e quiz em cada aula.</p></div></header>

      <section className="card learn-hero">
        <div className="grow">
          <div className="muted small">Seu nível</div>
          <div className="big">{data.level}</div>
          <div className="bar tall" role="progressbar" aria-valuenow={data.percent} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${data.percent}%` }} /></div>
          <div className="muted small">{data.completed} de {data.total} aulas concluídas · {data.points} pontos</div>
          {data.videos > 0 && <div className="muted small">{data.videos} videoaulas · {fmtDuration(data.video_seconds)} de vídeo</div>}
        </div>
        <div className="hero-actions">
          {data.next_lesson_id
            ? <Link className="btn primary" to={`/aulas/${data.next_lesson_id}`}>{data.completed ? "Continuar" : "Começar"}</Link>
            : <span className="tag paid">curso completo ✓</span>}
          {startVideo && <Link className="btn ghost" to={`/aulas/${startVideo}?auto=1`}>▶ Assistir em sequência</Link>}
        </div>
      </section>

      <div className="modules">
        {data.modules.map((m) => (
          <section key={m.id} className="card module">
            <header>
              <div className="row"><h2>{m.title}</h2><span className="tag">{m.level}</span></div>
              <p className="muted small">{m.description}</p>
              <div className="bar" role="progressbar" aria-valuenow={m.completed} aria-valuemin={0} aria-valuemax={m.total}><span style={{ width: `${(100 * m.completed) / m.total}%` }} /></div>
              <span className="muted small">{m.completed}/{m.total} aulas</span>
            </header>
            <ol className="lessons">
              {m.lessons.map((l) => (
                <li key={l.id}>
                  <Link to={`/aulas/${l.id}`} className={l.completed ? "done" : ""}>
                    <span className="check-ico" aria-label={l.completed ? "concluída" : "pendente"}>{l.completed ? "✓" : "○"}</span>
                    <span className="grow"><b>{l.title}</b><span className="muted small"> {l.summary}</span></span>
                    <span className="muted small">{l.video_seconds ? `▶ ${fmtDuration(l.video_seconds)}` : `${l.minutes} min`}{l.best_score != null ? ` · ${l.best_score}%` : ""}</span>
                  </Link>
                </li>))}
            </ol>
          </section>))}
      </div>
    </div>
  );
}
