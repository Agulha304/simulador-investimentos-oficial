import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fmtMonth } from "../lib/format";
import { sim, type Hub } from "../services/sim";

export function AchievementsPage() {
  const [hub, setHub] = useState<Hub | null>(null);
  useEffect(() => { sim.hub().then(setHub).catch(() => undefined); }, []);
  if (!hub) return <div className="muted">Carregando…</div>;
  const got = hub.achievements.filter((a) => a.unlocked).length;
  return (
    <div className="hub">
      <Link to="/" className="back">⬅ Voltar</Link>
      <section className="hero"><div><h1>🏅 Conquistas</h1><p>{got} de {hub.achievements.length} desbloqueadas. Elas valem para todas as suas partidas.</p></div></section>
      <div className="xp wide"><i style={{ width: `${(got / hub.achievements.length) * 100}%` }} /></div>
      <div className="trophy-grid">{hub.achievements.map((a) => (
        <div key={a.key} className={`trophy${a.unlocked ? " on" : ""}`}>
          <span className="trophy-emoji">{a.unlocked ? "🏆" : "🔒"}</span><b>{a.name}</b><p className="small">{a.description}</p>
          {a.unlocked_month && <span className="chip up">{fmtMonth(a.unlocked_month)}</span>}
        </div>))}</div>
    </div>
  );
}
