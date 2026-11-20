import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { fmtMonth } from "../lib/format";
import { gameStore, useActiveGame } from "../services/gameStore";
import { sim, type GameSummary } from "../services/sim";
import { SearchBar } from "./SearchBar";

const INVEST = ["/mercado", "/renda-fixa", "/carteira", "/historico", "/ativo"];
const LIFE_NAV = [
  { to: "/painel", icon: "🏠", label: "Início" },
  { to: "/orcamento", icon: "📒", label: "Orçamento do mês", star: true },
  { to: "/mercado", icon: "📈", label: "Investir", group: INVEST },
  { to: "/empresas", icon: "🏪", label: "Empresas" },
  { to: "/patrimonio", icon: "🏡", label: "Bens" },
  { to: "/vida", icon: "💖", label: "Vida pessoal" },
  { to: "/economia", icon: "🌍", label: "Economia" },
  { to: "/desempenho", icon: "🏅", label: "Desempenho" },
  { to: "/resumos", icon: "📊", label: "Resumos" },
];
const TRAIN_NAV = [
  { to: "/painel", icon: "🏠", label: "Início" },
  { to: "/mercado", icon: "📈", label: "Investir", group: INVEST },
  { to: "/desempenho", icon: "🏅", label: "Desempenho" },
];
const INVEST_TABS = [
  { to: "/mercado", label: "Mercado" }, { to: "/renda-fixa", label: "Renda fixa" },
  { to: "/carteira", label: "Minha carteira" }, { to: "/historico", label: "Histórico de operações" },
];

/** Dentro da partida: barra superior (sair, data, avançar) + menu enxuto + sub-abas de investimento. */
export function GameLayout() {
  const active = useActiveGame();
  const nav = useNavigate();
  const loc = useLocation();
  const [g, setG] = useState<GameSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!active) return;
    sim.game_(active.id).then(setG).catch(() => { gameStore.set(null); nav("/"); });
  }, [active, nav]);
  useEffect(() => { load(); }, [load, loc.pathname === "/painel"]);   // eslint-disable-line react-hooks/exhaustive-deps

  if (!active) return <Navigate to="/" replace />;
  const training = active.kind === "TRAINING";
  const items = training ? TRAIN_NAV : LIFE_NAV;
  const inInvest = INVEST.some((p) => loc.pathname.startsWith(p));

  const advance = async () => {
    setBusy(true); setErr(null);
    try { await sim.trainAdvance(active.id, 1); window.location.reload(); } catch (e) { setErr(e instanceof Error ? e.message : "Erro"); setBusy(false); }
  };
  return (
    <div className="game-shell">
      <header className="game-top">
        <button className="btn ghost small exit" onClick={() => { gameStore.set(null); nav("/"); }}>⬅ Sair da partida</button>
        <div className="game-title"><span className={`tag ${training ? "train" : "life"}`}>{training ? "🧪 Treino" : "🎮 Vida"}</span><b>{active.name}</b></div>
        <div className="game-date">
          {training && g?.market_date && <><span className="chip">📅 {fmtMonth(g.market_date)} · dados reais</span>
            <button className="btn primary small" disabled={busy || g.at_present} onClick={() => void advance()}>⏭ Avançar 1 mês</button></>}
          {!training && g?.month && <><span className="chip">📅 {fmtMonth(g.month)}</span>
            <Link className="btn primary small" to="/orcamento">⏭ Passar o mês</Link></>}
        </div>
      </header>
      {training && <div className="training-banner">🎓 <b>Modo treino:</b> tudo aqui é simulado e o dinheiro é de mentirinha. Os preços são os <b>reais do passado</b>; você pode avançar meses ou voltar no tempo.</div>}
      {!training && g?.started && inInvest && <div className="sim-banner-game">🎲 <b>Mercado simulado:</b> o preço de partida de cada ativo é a cotação real de quando você começou; daqui para a frente os preços são <b>gerados pelo jogo</b> (economia, juros, crises). Não são previsões do mundo real.</div>}
      {err && <div className="alert" style={{ margin: "8px 16px" }}>{err}</div>}
      <div className="game-body">
        <nav className="game-nav" aria-label="Menu da partida">
          {items.map((n) => {
            const on = "group" in n && n.group ? inInvest : loc.pathname === n.to || loc.pathname.startsWith(`${n.to}/`);
            return <NavLink key={n.to} to={n.to} className={`gnav${on ? " on" : ""}`}><span className="gnav-icon" aria-hidden>{n.icon}</span><span className="gnav-label">{n.label}</span>{"star" in n && n.star ? <span className="gnav-dot" title="Faça todo mês">!</span> : null}</NavLink>;
          })}
        </nav>
        <main className="game-main">
          {inInvest && (
            <div className="invest-tabs">
              {INVEST_TABS.map((t) => <NavLink key={t.to} to={t.to} className={({ isActive }) => `itab${isActive ? " on" : ""}`}>{t.label}</NavLink>)}
              <div className="grow" /><SearchBar />
            </div>)}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
