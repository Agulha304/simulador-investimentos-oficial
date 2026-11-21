import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fmtBRL, fmtDay } from "../lib/format";
import { type Ranking } from "../services/api";
import { useApi } from "../services/dataCache";
import { gameStore } from "../services/gameStore";
import { sim, type GameSummary, type Hub } from "../services/sim";
import { useAuth } from "../services/auth";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
const MEDAL = ["🥇", "🥈", "🥉"];

export function HubPage() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [board, setBoard] = useState<"wealth" | "return">("wealth");
  const [actionError, setActionError] = useState<string | null>(null);
  useEffect(() => { gameStore.set(null); }, []);          // estar no menu inicial = fora de qualquer partida
  // /games e ranking em paralelo, com cache (compartilhado com Conquistas/Configurações)
  const { data: hub, error: hubError } = useApi<Hub>("/games");
  const { data: rank } = useApi<Ranking>(`/ranking?board=${board}&period=all`);
  const error = actionError ?? hubError;

  const open = async (g: GameSummary) => { gameStore.set({ id: g.id, kind: g.kind, name: g.name }); nav("/painel"); };
  const archive = async (g: GameSummary) => {
    if (!window.confirm(`Arquivar a partida “${g.name}”? Ela some da lista (seus dados ficam guardados).`)) return;
    try { await sim.archiveGame(g.id); } catch (e) { setActionError(errMsg(e)); }
  };
  const unlocked = hub?.achievements.filter((a) => a.unlocked).length ?? 0;
  const pct = hub ? Math.round((hub.lessons.done / Math.max(1, hub.lessons.total)) * 100) : 0;

  return (
    <div className="hub">
      <section className="hero">
        <div>
          <h1>Olá, {user?.name.split(" ")[0]}! 👋</h1>
          <p>O que vamos fazer hoje? Escolha uma aventura:</p>
        </div>
      </section>
      {error && <div className="alert">{error}</div>}

      <section className="big-cards">
        <Link to="/partida/nova" className="big-card life">
          <span className="big-emoji">🎮</span><h2>Iniciar partida</h2>
          <p>Viva uma vida financeira completa: salário, contas do mês, empresas, família e investimentos. O mundo muda mês a mês!</p>
          <span className="go">Jogar →</span>
        </Link>
        <Link to="/treino/novo" className="big-card train">
          <span className="big-emoji">🧪</span><h2>Treinar investimentos</h2>
          <p>Pratique com dinheiro de mentirinha e preços <b>reais do passado</b>. Dá até para voltar no tempo e ver o que teria acontecido.</p>
          <span className="go">Treinar →</span>
        </Link>
        <Link to="/aulas" className="big-card learn">
          <span className="big-emoji">📚</span><h2>Fazer aulas</h2>
          <p>Aprenda do zero, em aulas curtas com vídeo e quiz. Ganhe pontos a cada aula!</p>
          <div className="xp"><i style={{ width: `${pct}%` }} /></div>
          <span className="go">{hub ? `${hub.lessons.done} de ${hub.lessons.total} aulas` : "Estudar →"}</span>
        </Link>
      </section>

      <section className="panel">
        <div className="panel-head"><h2>🎒 Minhas partidas</h2><span className="muted small">continue de onde parou</span></div>
        {!hub ? <p className="muted">Carregando…</p> : hub.games.length === 0 ? (
          <p className="muted">Você ainda não tem partidas salvas. Que tal começar uma agora? 👆</p>
        ) : (
          <div className="save-grid">{hub.games.map((g) => (
            <div key={g.id} className="save-card">
              <div className="row between"><span className={`tag ${g.kind === "TRAINING" ? "train" : "life"}`}>{g.kind === "TRAINING" ? "🧪 Treino" : "🎮 Vida"}</span>
                <button className="icon-btn" title="Arquivar" onClick={() => void archive(g)}>🗑</button></div>
              <h3>{g.name}</h3>
              {g.ended && <span className="chip down">{g.ended === "DEAD" ? "🕊️ personagem faleceu" : "📉 falência"}</span>}
              <p className="muted small">{g.kind === "TRAINING" ? `Mercado em ${g.market_date?.slice(0, 7).split("-").reverse().join("/")}` : g.started ? `${g.mode === "CAREER" ? "Carreira" : "Livre"} · mês ${g.month?.slice(0, 7).split("-").reverse().join("/")}` : "Ainda não começou"}</p>
              <p className="num save-money">{g.equity_brl ? fmtBRL(g.equity_brl) : "—"}</p>
              <p className="muted small">Jogou em {fmtDay(g.last_played_at.slice(0, 10))}</p>
              <button className="btn primary" onClick={() => void open(g)}>{g.ended ? "👁 Ver" : "▶ Continuar"}</button>
            </div>))}</div>)}
      </section>

      <div className="two-panels">
        <section className="panel">
          <div className="panel-head"><h2>🏆 Ranking</h2><Link to="/ranking" className="small">ver tudo →</Link></div>
          <div className="seg compact"><button className={board === "wealth" ? "on" : ""} onClick={() => setBoard("wealth")}>Vida completa</button><button className={board === "return" ? "on" : ""} onClick={() => setBoard("return")}>Treino</button></div>
          {!rank || rank.entries.length === 0 ? <p className="muted small" style={{ marginTop: 12 }}>Ninguém no ranking ainda. Seja o primeiro!</p> : (
            <ol className="podium">{rank.entries.slice(0, 5).map((e) => (
              <li key={e.rank} className={e.is_me ? "me" : ""}><span className="pos">{MEDAL[e.rank - 1] ?? e.rank}</span><span className="grow">{e.nickname}{e.is_me && " (você)"}</span>
                <b className="num">{board === "wealth" ? fmtBRL(e.wealth_brl) : `${e.return_pct}%`}</b></li>))}</ol>)}
        </section>
        <section className="panel">
          <div className="panel-head"><h2>🏅 Conquistas</h2><Link to="/conquistas" className="small">ver todas ({unlocked}/{hub?.achievements.length ?? 0}) →</Link></div>
          <div className="medals">{(hub?.achievements ?? []).slice(0, 12).map((a) => (
            <span key={a.key} className={`medal${a.unlocked ? " on" : ""}`} title={`${a.name} — ${a.description}`}>{a.unlocked ? "🏅" : "🔒"}</span>))}</div>
          <p className="muted small" style={{ marginTop: 10 }}>As conquistas valem para todas as suas partidas e nunca se perdem.</p>
        </section>
      </div>
    </div>
  );
}
