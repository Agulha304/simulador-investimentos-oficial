import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fmtBRL } from "../lib/format";
import { gameStore } from "../services/gameStore";
import { sim, type GameInfo, type Scenario } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
const EMOJI: Record<string, string> = { independent: "🌱", young_pro: "💼", entrepreneur: "🚀", investor: "💎", family: "👨‍👩‍👧" };

/** Assistente em passos: nome → modo → cenário/valores → começar. Cria a partida e já a configura. */
export function NewGamePage() {
  const nav = useNavigate();
  const [info, setInfo] = useState<GameInfo | null>(null);
  const [step, setStep] = useState(1);
  const [name, setName] = useState("Minha vida financeira");
  const [mode, setMode] = useState<"CAREER" | "FREE">("CAREER");
  const [scenario, setScenario] = useState("young_pro");
  const [cfg, setCfg] = useState({ cash: "20000", monthly_income: "4000", monthly_expenses: "2000", rent: "1000", age: "28" });
  const [seed, setSeed] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { gameStore.set(null); sim.game().then(setInfo).catch((e) => setErr(errMsg(e))); }, []);

  const start = async () => {
    setBusy(true); setErr(null);
    let created: { id: number; name: string } | null = null;
    try {
      const g = await sim.createGame("LIFE", name.trim() || "Minha partida");
      created = g;
      gameStore.set({ id: g.id, kind: "LIFE", name: g.name });
      const body: Record<string, unknown> = { mode, name: "Você", seed: seed ? Number(seed) : undefined };
      if (mode === "CAREER") body.scenario = scenario;
      else body.free = { cash: cfg.cash, monthly_income: cfg.monthly_income, monthly_expenses: cfg.monthly_expenses, rent: cfg.rent, age: Number(cfg.age) };
      await sim.gameStart(body);
      nav("/painel");
    } catch (e) {
      setErr(errMsg(e));
      gameStore.set(null);
      if (created) { try { await sim.archiveGame(created.id); } catch { /* ignore */ } }   // não deixa partida pela metade
      setBusy(false);
    }
  };
  const sc: Scenario | undefined = info?.scenarios.find((s) => s.key === scenario);
  return (
    <div className="hub">
      <Link to="/" className="back">⬅ Voltar</Link>
      <section className="hero"><div><h1>🎮 Nova partida</h1><p>Passo {step} de 3</p></div></section>
      <div className="steps"><i className={step >= 1 ? "on" : ""} /><i className={step >= 2 ? "on" : ""} /><i className={step >= 3 ? "on" : ""} /></div>
      {err && <div className="alert">{err}</div>}

      {step === 1 && (
        <section className="panel stack">
          <h2>Como vai se chamar a sua partida?</h2>
          <input className="xl" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
          <p className="muted">Você pode ter várias partidas salvas e voltar nelas quando quiser.</p>
          <div><button className="btn primary big" onClick={() => setStep(2)}>Próximo →</button></div>
        </section>)}

      {step === 2 && (
        <section className="stack">
          <h2>Como você quer jogar?</h2>
          <div className="big-cards two">
            <button className={`big-card pick${mode === "CAREER" ? " on" : ""}`} onClick={() => setMode("CAREER")}>
              <span className="big-emoji">🧭</span><h2>Modo carreira</h2><p>Você começa numa situação pronta (cenário) e recebe objetivos para te guiar. Ótimo para aprender!</p></button>
            <button className={`big-card pick${mode === "FREE" ? " on" : ""}`} onClick={() => setMode("FREE")}>
              <span className="big-emoji">🎨</span><h2>Modo livre</h2><p>Você monta o começo do seu jeito e define as suas próprias metas. Sem regras de caminho.</p></button>
          </div>
          <div className="row"><button className="btn ghost" onClick={() => setStep(1)}>← Voltar</button><button className="btn primary big" onClick={() => setStep(3)}>Próximo →</button></div>
        </section>)}

      {step === 3 && info && (
        <section className="stack">
          {mode === "CAREER" ? (
            <>
              <h2>Escolha o seu cenário</h2>
              <div className="big-cards five">{info.scenarios.map((s) => (
                <button key={s.key} className={`big-card pick small${scenario === s.key ? " on" : ""}`} onClick={() => setScenario(s.key)}>
                  <span className="big-emoji">{EMOJI[s.key] ?? "⭐"}</span><h3>{s.name}</h3><p>{s.description}</p>
                  <span className="small">Caixa {fmtBRL(String(s.cash))} · renda {fmtBRL(String(s.salary))}/mês</span></button>))}</div>
              {sc && <div className="panel"><h3>🎯 Objetivos</h3><ul className="clean">{sc.goals.map((g) => <li key={g.key}>{g.title}</li>)}</ul>
                <h3>⚠️ Desafios</h3><ul className="clean">{sc.challenges.map((c) => <li key={c}>{c}</li>)}</ul></div>}
            </>
          ) : (
            <div className="panel stack"><h2>Como é o seu começo?</h2>
              <div className="cols-2">
                <label className="stack"><span>💰 Dinheiro inicial (R$)</span><input value={cfg.cash} onChange={(e) => setCfg({ ...cfg, cash: e.target.value })} inputMode="decimal" /></label>
                <label className="stack"><span>💼 Renda por mês (R$)</span><input value={cfg.monthly_income} onChange={(e) => setCfg({ ...cfg, monthly_income: e.target.value })} inputMode="decimal" /></label>
                <label className="stack"><span>🛒 Gastos por mês (R$)</span><input value={cfg.monthly_expenses} onChange={(e) => setCfg({ ...cfg, monthly_expenses: e.target.value })} inputMode="decimal" /></label>
                <label className="stack"><span>🏠 Aluguel (R$, 0 = casa própria)</span><input value={cfg.rent} onChange={(e) => setCfg({ ...cfg, rent: e.target.value })} inputMode="decimal" /></label>
                <label className="stack"><span>🎂 Idade</span><input value={cfg.age} onChange={(e) => setCfg({ ...cfg, age: e.target.value })} inputMode="numeric" /></label>
              </div>
              <p className="muted small">Se os números não fecharem (gastos que o dinheiro não aguenta), o jogo avisa para você ajustar.</p></div>)}
          <details className="panel"><summary>Opções avançadas</summary>
            <label className="stack" style={{ marginTop: 10 }}><span className="muted small">Semente do mundo (repete o mesmo cenário econômico)</span><input value={seed} onChange={(e) => setSeed(e.target.value)} inputMode="numeric" style={{ maxWidth: 200 }} /></label></details>
          <div className="row"><button className="btn ghost" onClick={() => setStep(2)}>← Voltar</button><button className="btn primary big" disabled={busy} onClick={() => void start()}>{busy ? "Criando…" : "🚀 Começar a partida!"}</button></div>
        </section>)}
    </div>
  );
}
