import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fmtBRL } from "../lib/format";
import { gameStore } from "../services/gameStore";
import { sim, type GameInfo, type Scenario } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
const FIELDS = [
  { key: "tecnologia", label: "Tecnologia", emoji: "💻", text: "Reajustes altos e muita procura." },
  { key: "saude", label: "Saúde", emoji: "🩺", text: "Estável; paga muito bem a quem se forma." },
  { key: "engenharia", label: "Engenharia", emoji: "🏗️", text: "Bons reajustes e grandes projetos." },
  { key: "financas", label: "Finanças e negócios", emoji: "📊", text: "Cresce com promoções e gestão." },
  { key: "direito", label: "Direito", emoji: "⚖️", text: "Começo igual, ótimo depois de formado." },
  { key: "educacao", label: "Educação", emoji: "📚", text: "Reajustes menores, muito significado." },
  { key: "comercio", label: "Comércio e vendas", emoji: "🛍️", text: "Comissões e crescimento moderado." },
  { key: "artes", label: "Artes e comunicação", emoji: "🎨", text: "Criativo, com ganho irregular." },
];
const EMOJI: Record<string, string> = { independent: "🌱", young_pro: "💼", entrepreneur: "🚀", investor: "💎", family: "👨‍👩‍👧" };

/** Assistente em passos: nome → modo → cenário/valores → começar. Cria a partida e já a configura. */
export function NewGamePage() {
  const nav = useNavigate();
  const [info, setInfo] = useState<GameInfo | null>(null);
  const [step, setStep] = useState(1);
  const [name, setName] = useState("Minha vida financeira");
  const [charName, setCharName] = useState("");
  const [gender, setGender] = useState<"M" | "F" | "N">("N");
  const [field, setField] = useState("comercio");
  const [age, setAge] = useState("");
  const [mode, setMode] = useState<"CAREER" | "FREE" | "RANKED">("CAREER");
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
      const body: Record<string, unknown> = { mode, name: charName.trim() || "Você", seed: seed ? Number(seed) : undefined, gender, interested_in: "ANY", career_field: field, age: age ? Number(age) : undefined };
      if (mode === "CAREER") body.scenario = scenario;
      else if (mode === "FREE") body.free = { cash: cfg.cash, monthly_income: cfg.monthly_income, monthly_expenses: cfg.monthly_expenses, rent: cfg.rent, age: Number(cfg.age) };
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
      <section className="hero"><div><h1>🎮 Nova partida</h1><p>Passo {step} de 4</p></div></section>
      <div className="steps"><i className={step >= 1 ? "on" : ""} /><i className={step >= 2 ? "on" : ""} /><i className={step >= 3 ? "on" : ""} /><i className={step >= 4 ? "on" : ""} /></div>
      {err && <div className="alert">{err}</div>}

      {step === 1 && (
        <section className="stack">
          <h2>Como você quer jogar?</h2>
          <p className="muted">Escolha primeiro o modo: ele define o que você poderá personalizar a seguir.</p>
          <div className="big-cards three">
            <button className={`big-card pick${mode === "CAREER" ? " on" : ""}`} onClick={() => setMode("CAREER")}>
              <span className="big-emoji">🧭</span><h2>Modo carreira</h2><p>Você começa numa situação pronta (cenário) e recebe objetivos para te guiar. Ótimo para aprender!</p></button>
            <button className={`big-card pick${mode === "FREE" ? " on" : ""}`} onClick={() => setMode("FREE")}>
              <span className="big-emoji">🎨</span><h2>Modo livre</h2><p>Você monta o começo do seu jeito e define as suas próprias metas. Sem regras de caminho.</p></button>
            <button className={`big-card pick${mode === "RANKED" ? " on" : ""}`} onClick={() => setMode("RANKED")}>
              <span className="big-emoji">🏆</span><h2>Modo ranqueado</h2><p>Todo mundo começa igual: 18 anos, R$ 1.800/mês num subemprego (caixa, repositor, atendente...). Só este modo entra no ranking!</p></button>
          </div>
          <div><button className="btn primary big" onClick={() => setStep(2)}>Próximo →</button></div>
        </section>)}

      {step === 2 && (
        <section className="panel stack">
          <h2>Como vai se chamar a sua partida?</h2>
          <input className="xl" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
          <p className="muted">Você pode ter várias partidas salvas e voltar nelas quando quiser.</p>
          <h2>Quem é o seu personagem?</h2>
          {mode !== "RANKED" && <label className="stack"><span>🎂 Idade inicial (18 a 80) — vazio = a do cenário</span><input className="xl" value={age} onChange={(e) => setAge(e.target.value.replace(/\D/g, ""))} inputMode="numeric" maxLength={2} placeholder="ex.: 18" style={{ maxWidth: 160 }} /></label>}
          <label className="stack"><span>Nome do personagem</span><input className="xl" value={charName} onChange={(e) => setCharName(e.target.value)} maxLength={60} placeholder="Como você quer ser chamado" /></label>
          <div><span className="muted small">Sexo</span>
            <div className="seg compact" style={{ marginTop: 6 }}>
              {([["M", "👨 Masculino"], ["F", "👩 Feminino"], ["N", "🙂 Prefiro não dizer"]] as const).map(([k, l]) => <button key={k} className={gender === k ? "on" : ""} onClick={() => setGender(k)}>{l}</button>)}</div></div>
          <p className="muted small">Você vai conhecer homens e mulheres ao longo da vida.</p>
          {mode === "RANKED" && <p className="muted small">🏆 No modo ranqueado só nome e sexo são escolhidos: a largada é igual para todos.</p>}
          <div className="row"><button className="btn ghost" onClick={() => setStep(1)}>← Voltar</button><button className="btn primary big" onClick={() => setStep(3)}>Próximo →</button></div>
        </section>)}

      {step === 3 && info && (
        <section className="stack">
          {mode === "RANKED" ? (
            <div className="card stack"><h2>🏆 Largada igual para todos</h2>
              <p>Você começa com <b>18 anos</b>, <b>R$ 1.800 por mês</b> num subemprego da área que escolher no passo anterior e <b>R$ 1.500</b> no bolso. A partir daí, evolua: estude, faça cursos, procure empregos melhores, invista e abra empresas. O seu patrimônio aparece no ranking.</p></div>
          ) : mode === "CAREER" ? (
            <>
              <h2>Escolha o seu cenário</h2>
              <div className="big-cards five">{info.scenarios.map((s) => (
                <button key={s.key} className={`big-card pick small${scenario === s.key ? " on" : ""}`} onClick={() => setScenario(s.key)}>
                  <span className="big-emoji">{EMOJI[s.key] ?? "⭐"}</span><h3>{s.name}</h3><p>{s.description}</p>
                  <span className="small">🎂 {s.age ?? 28} anos · Caixa {fmtBRL(String(s.cash))} · renda {fmtBRL(String(s.salary))}/mês</span></button>))}</div>
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
              <p className="muted small">Sua família já começa com pai e mãe e, por sorteio, irmãos. A idade do personagem aparece no topo da partida.</p>
              <p className="muted small">Se os números não fecharem (gastos que o dinheiro não aguenta), o jogo avisa para você ajustar.</p></div>)}
          <details className="panel"><summary>Opções avançadas</summary>
            <label className="stack" style={{ marginTop: 10 }}><span className="muted small">Semente do mundo (repete o mesmo cenário econômico)</span><input value={seed} onChange={(e) => setSeed(e.target.value)} inputMode="numeric" style={{ maxWidth: 200 }} /></label></details>
          <div className="row"><button className="btn ghost" onClick={() => setStep(2)}>← Voltar</button><button className="btn primary big" disabled={busy} onClick={() => (mode === "RANKED" ? void start() : setStep(4))}>{mode === "RANKED" ? (busy ? "Criando…" : "Começar a partida 🏆") : "Próximo →"}</button></div>
        </section>)}

      {step === 4 && (
        <section className="stack">
          <h2>Em que área você quer atuar?</h2>
          <p className="muted">Todas começam pagando mais ou menos o mesmo. O que muda é a <b>perspectiva de crescimento</b>. Mais tarde você pode fazer faculdade e mudar para uma área que paga mais.</p>
          <div className="big-cards five">{FIELDS.map((f) => (
            <button key={f.key} className={`big-card pick small${field === f.key ? " on" : ""}`} onClick={() => setField(f.key)}>
              <span className="big-emoji">{f.emoji}</span><h3>{f.label}</h3><p>{f.text}</p></button>))}</div>
          <div className="row"><button className="btn ghost" onClick={() => setStep(3)}>← Voltar</button><button className="btn primary big" disabled={busy} onClick={() => void start()}>{busy ? "Criando…" : "🚀 Começar a partida!"}</button></div>
        </section>)}
    </div>
  );
}
