import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fmtBRL } from "../lib/format";
import { sim, type GameInfo } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");

export function GamePage() {
  const nav = useNavigate();
  const [g, setG] = useState<GameInfo | null>(null);
  const [mode, setMode] = useState<"FREE" | "CAREER">("CAREER");
  const [scenario, setScenario] = useState("young_pro");
  const [name, setName] = useState("Você");
  const [seed, setSeed] = useState("");
  const [cfg, setCfg] = useState({ cash: "20000", monthly_income: "4000", monthly_expenses: "2000", rent: "1000", age: "28" });
  const [infl, setInfl] = useState("4.5");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { sim.game().then(setG).catch((e) => setErr(errMsg(e))); }, []);
  if (!g) return err ? <div className="alert">{err}</div> : <div className="muted">Carregando…</div>;

  const start = async () => {
    setBusy(true); setErr(null);
    try {
      const body: Record<string, unknown> = { mode, name, seed: seed ? Number(seed) : undefined, economy: { inflation: Number(infl) } };
      if (mode === "CAREER") body.scenario = scenario;
      else body.free = { cash: cfg.cash, monthly_income: cfg.monthly_income, monthly_expenses: cfg.monthly_expenses, rent: cfg.rent, age: Number(cfg.age) };
      await sim.gameStart(body);
      nav("/visao-geral");
    } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  };

  if (g.started) return (
    <div className="page"><header className="page-head"><div><h1>Partida</h1><p className="muted">{g.mode === "CAREER" ? `Modo carreira — ${g.scenarios.find((s) => s.key === g.scenario)?.name}` : "Modo livre"} · semente {g.seed}</p></div></header>
      <div className="card muted">A partida já foi iniciada. A configuração inicial só pode ser escolhida em uma conta nova, para nunca apagar seu histórico.</div></div>);

  const sc = g.scenarios.find((s) => s.key === scenario);
  return (
    <div className="page">
      <header className="page-head"><div><h1>Nova partida</h1><p className="muted">Escolha como começar. Os mesmos sistemas valem nos dois modos: investimentos, patrimônio, empresas e vida pessoal.</p></div></header>
      {err && <div className="alert">{err}</div>}
      <div className="seg compact tabs"><button className={mode === "CAREER" ? "on" : ""} onClick={() => setMode("CAREER")}>Modo carreira</button><button className={mode === "FREE" ? "on" : ""} onClick={() => setMode("FREE")}>Modo livre</button></div>
      {mode === "CAREER" ? (
        <>
          <div className="cols-2">{g.scenarios.map((s) => (
            <button key={s.key} className={`card scenario stack${scenario === s.key ? " on" : ""}`} onClick={() => setScenario(s.key)}>
              <b>{s.name}</b><span className="muted small">{s.description}</span>
              <span className="small">Caixa {fmtBRL(String(s.cash))} · renda {fmtBRL(String(s.salary))}/mês</span></button>))}</div>
          {sc && <section className="card stack"><h2>{sc.name}</h2>
            <p className="small"><b>Objetivos:</b> {sc.goals.map((x) => x.title).join(" · ")}</p>
            <p className="small"><b>Desafios:</b> {sc.challenges.join(" ")}</p>
            <p className="muted small">Os objetivos orientam, mas você decide: nada obriga um caminho único.</p></section>}
        </>
      ) : (
        <section className="card stack"><h2>Situação inicial</h2>
          <div className="cols-2">
            <label className="stack"><span className="muted small">Dinheiro inicial (R$)</span><input value={cfg.cash} onChange={(e) => setCfg({ ...cfg, cash: e.target.value })} inputMode="decimal" /></label>
            <label className="stack"><span className="muted small">Renda mensal (R$)</span><input value={cfg.monthly_income} onChange={(e) => setCfg({ ...cfg, monthly_income: e.target.value })} inputMode="decimal" /></label>
            <label className="stack"><span className="muted small">Despesas mensais (R$)</span><input value={cfg.monthly_expenses} onChange={(e) => setCfg({ ...cfg, monthly_expenses: e.target.value })} inputMode="decimal" /></label>
            <label className="stack"><span className="muted small">Aluguel (R$, 0 = moradia própria)</span><input value={cfg.rent} onChange={(e) => setCfg({ ...cfg, rent: e.target.value })} inputMode="decimal" /></label>
            <label className="stack"><span className="muted small">Idade</span><input value={cfg.age} onChange={(e) => setCfg({ ...cfg, age: e.target.value })} inputMode="numeric" /></label>
          </div>
          <p className="muted small">Combinações que quebrariam a simulação (por exemplo, despesas que o caixa não sustenta) são recusadas.</p></section>
      )}
      <section className="card stack"><h2>Personagem e mundo</h2>
        <div className="cols-2">
          <label className="stack"><span className="muted small">Seu nome</span><input value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label className="stack"><span className="muted small">Inflação inicial (% a.a.)</span><input value={infl} onChange={(e) => setInfl(e.target.value)} inputMode="decimal" /></label>
          <label className="stack"><span className="muted small">Semente do mundo (opcional — repete o mesmo cenário)</span><input value={seed} onChange={(e) => setSeed(e.target.value)} inputMode="numeric" /></label></div></section>
      <div><button className="btn primary" disabled={busy} onClick={() => void start()}>Começar partida</button></div>
    </div>
  );
}
