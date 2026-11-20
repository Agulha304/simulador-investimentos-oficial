import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { sim, type AccountCategory, type GameSummary, type SimParams } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");

/** Configurações da conta: valem para todas as partidas (atuais e futuras). */
export function SettingsPage() {
  const [cats, setCats] = useState<AccountCategory[] | null>(null);
  const [kind, setKind] = useState<"EXPENSE" | "INCOME">("EXPENSE");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const load = () => sim.accountCategories().then(setCats).catch((e) => setErr(errMsg(e)));
  useEffect(() => { void load(); }, []);
  const run = async (fn: () => Promise<unknown>) => { setErr(null); try { await fn(); await load(); } catch (e) { setErr(errMsg(e)); } };
  if (!cats) return err ? <div className="alert">{err}</div> : <div className="muted">Carregando…</div>;
  const Block = ({ k, title, hint }: { k: "EXPENSE" | "INCOME"; title: string; hint: string }) => (
    <section className="panel stack"><h2>{title}</h2><p className="muted small" style={{ margin: 0 }}>{hint}</p>
      <ul className="list-plain">{cats.filter((c) => c.kind === k).map((c) => (
        <li key={c.id}>
          <input defaultValue={c.name} aria-label={`Nome da categoria ${c.name}`} maxLength={60} style={{ maxWidth: 260 }}
            onBlur={(e) => { const v = e.target.value.trim(); if (v && v !== c.name) void run(() => sim.patchAccountCategory(c.id, { name: v })); }} />
          <button className={`btn small ${c.active ? "primary" : "ghost"}`} onClick={() => void run(() => sim.patchAccountCategory(c.id, { active: !c.active }))}>{c.active ? "✅ Ativada" : "⏸ Desativada"}</button>
        </li>))}</ul></section>
  );
  return (
    <div className="hub">
      <Link to="/" className="back">⬅ Voltar</Link>
      <section className="hero"><div><h1>⚙ Configurações da conta</h1><p>As escolhas daqui valem para todas as suas partidas — as que você já tem e as próximas.</p></div></section>
      {err && <div className="alert">{err}</div>}
      <Block k="EXPENSE" title="🛒 Categorias de despesas" hint="Desative as que você não quer usar: elas deixam de aparecer ao lançar despesas. Dá para renomear também." />
      <Block k="INCOME" title="💼 Categorias de receitas" hint="Mesma ideia, para o dinheiro que entra." />
      <SimSettings />
      <section className="panel stack"><h2>➕ Nova categoria</h2>
        <form className="row" onSubmit={(e) => { e.preventDefault(); if (name.trim()) void run(async () => { await sim.addAccountCategory(name.trim(), kind); setName(""); }); }}>
          <input placeholder="Nome (ex.: Pets)" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
          <select value={kind} onChange={(e) => setKind(e.target.value as "EXPENSE" | "INCOME")}><option value="EXPENSE">Despesa</option><option value="INCOME">Receita</option></select>
          <button className="btn primary" type="submit">Criar</button></form></section>
    </div>
  );
}


const PARAM_LABELS: [keyof SimParams, string, string][] = [
  ["volatility", "Oscilação dos preços", "Quanto os ativos sobem e descem"], ["event_frequency", "Frequência de acontecimentos", "Eventos aleatórios"],
  ["crisis_frequency", "Frequência de crises", "0 = sem crises"], ["crisis_severity", "Gravidade das crises", "Quão fortes elas são"],
  ["shock_scale", "Imprevistos da economia", "Ruído dos indicadores"],
];

/** Ajustes da economia simulada de cada partida de vida completa (antes ficavam na tela de Economia). */
function SimSettings() {
  const [games, setGames] = useState<GameSummary[]>([]);
  const [gid, setGid] = useState<number | null>(null);
  const [p, setP] = useState<SimParams | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { sim.hub().then((h) => { const life = h.games.filter((g) => g.kind === "LIFE"); setGames(life); if (life[0]) setGid(life[0].id); }).catch(() => undefined); }, []);
  useEffect(() => { if (gid != null) sim.gameSimParams(gid).then((r) => setP(r.params)).catch((e) => setMsg(errMsg(e))); }, [gid]);
  const save = async () => { if (gid == null || !p) return; try { const r = await sim.putGameSimParams(gid, p); setP(r.params); setMsg("Salvo! Vale a partir do próximo mês."); } catch (e) { setMsg(errMsg(e)); } };
  return (
    <section className="panel stack"><h2>🎚️ Ajustes da economia simulada</h2>
      <p className="muted small" style={{ margin: 0 }}>Controles de dificuldade das partidas de vida completa. 1,0× é o normal; valem do próximo mês em diante.</p>
      {games.length === 0 ? <p className="muted small">Você ainda não tem partidas de vida completa.</p> : (<>
        <label className="stack"><span>Partida</span><select value={gid ?? ""} onChange={(e) => setGid(Number(e.target.value))}>{games.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
        {p && PARAM_LABELS.map(([k, label, hint]) => (
          <label key={k} className="stack"><span>{label}: <b>{p[k].toFixed(1)}×</b></span>
            <input type="range" min={0} max={3} step={0.1} value={p[k]} onChange={(e) => setP({ ...p, [k]: Number(e.target.value) })} /><span className="muted small">{hint}</span></label>))}
        <div className="row"><button className="btn primary" onClick={() => void save()}>Salvar</button>{msg && <span className="small">{msg}</span>}</div>
        <p className="muted small">⚠️ Preços e crises são de uma economia simulada, não previsões reais.</p></>)}
    </section>
  );
}
