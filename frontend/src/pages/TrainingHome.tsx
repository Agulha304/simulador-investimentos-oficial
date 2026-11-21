import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { StatCard } from "../components/StatCard";
import { fmtBRL, fmtMonth, trend } from "../lib/format";
import { type PortfolioSummary } from "../services/api";
import { useApi } from "../services/dataCache";
import { useActiveGame } from "../services/gameStore";
import { sim, type GameSummary } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");

export function TrainingHome() {
  const game = useActiveGame()!;
  // mesmos GET /games/{id} e /portfolio do restante do app: vêm do cache e são refeitos sozinhos após cada ação
  const { data: g, error: loadErr } = useApi<GameSummary>(`/games/${game.id}`);
  const { data: pf } = useApi<PortfolioSummary>("/portfolio");
  const [date, setDate] = useState("");
  const [money, setMoney] = useState("10000");
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const marketMonth = g?.market_date?.slice(0, 7) ?? "";
  useEffect(() => { setDate(marketMonth); }, [marketMonth]);
  const act = async (fn: () => Promise<unknown>, msg: string) => {
    setErr(null);
    try { await fn(); setNote(msg); } catch (e) { setErr(errMsg(e)); }
  };
  if (!g) return err || loadErr ? <div className="alert">{err ?? loadErr}</div> : <div className="muted">Carregando…</div>;
  return (
    <div className="page">
      <header className="page-head"><div><h1>🧪 {g.name}</h1><p className="muted">Hoje, no seu treino, é <b>{fmtMonth(g.market_date!)}</b>. Os preços são os reais daquela época.</p></div></header>
      {err && <div className="alert">{err}</div>}
      {note && <div className="card small">✅ {note}</div>}
      {pf && <section className="stats-grid">
        <StatCard label="💰 Dinheiro de treino" value={fmtBRL(pf.cash_balance)} emphasis />
        <StatCard label="📦 Patrimônio total" value={fmtBRL(pf.total_equity_brl)} sub={`${pf.pnl_pct ?? "0"}% desde o início`} tone={trend(pf.pnl_brl)} />
        <StatCard label="📈 Investido" value={fmtBRL(pf.invested_brl)} />
      </section>}
      <div className="cols-2">
        <section className="card stack"><h2>⏭ Avançar no tempo</h2>
          <p className="muted small">Pule meses e veja como seus investimentos reagiram ao que realmente aconteceu.</p>
          <div className="row">{[1, 3, 6, 12].map((m) => <button key={m} className="btn primary small" disabled={g.at_present} onClick={() => void act(() => sim.trainAdvance(g.id, m), `Avançamos ${m} mês(es)!`)}>+{m} {m === 1 ? "mês" : "meses"}</button>)}</div>
          {g.at_present && <p className="muted small">Você chegou ao presente: não existem preços reais do futuro. Para simular o futuro, jogue uma partida de vida completa.</p>}</section>
        <section className="card stack"><h2>⏪ Voltar no tempo</h2>
          <p className="muted small">Escolha qualquer mês desde 2015. O que você comprou continua com você, valendo o preço daquela data.</p>
          <div className="row"><input type="month" value={date} min="2015-01" max={new Date().toISOString().slice(0, 7)} onChange={(e) => setDate(e.target.value)} />
            <button className="btn ghost small" onClick={() => void act(() => sim.trainDate(g.id, `${date}-01`), "Viajamos no tempo!")}>Ir para essa data</button></div></section>
        <section className="card stack"><h2>💰 Adicionar dinheiro de treino</h2>
          <p className="muted small">É dinheiro fictício, só para praticar. Não conta no ranking.</p>
          <div className="row"><input value={money} onChange={(e) => setMoney(e.target.value)} inputMode="decimal" style={{ maxWidth: 160 }} />
            <button className="btn ghost small" onClick={() => void act(() => sim.trainMoney(g.id, money), "Dinheiro de treino adicionado!")}>Adicionar</button></div></section>
        <section className="card stack"><h2>🚀 Por onde começar?</h2>
          <ul className="clean"><li>📈 <Link to="/mercado">Mercado</Link>: compre ações, fundos e cripto</li><li>🏦 <Link to="/renda-fixa">Renda fixa</Link>: Tesouro, CDB e mais</li>
            <li>🏅 <Link to="/desempenho">Desempenho</Link>: veja como você está indo e quais aulas ajudam</li></ul></section>
      </div>
    </div>
  );
}
