import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { gameStore } from "../services/gameStore";
import { sim } from "../services/sim";

const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

export function NewTrainingPage() {
  const nav = useNavigate();
  const now = new Date();
  const [name, setName] = useState("Meu treino");
  const [month, setMonth] = useState(now.getMonth());
  const [year, setYear] = useState(now.getFullYear() - 2);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const years = Array.from({ length: now.getFullYear() - 2015 + 1 }, (_, i) => 2015 + i);
  const go = async () => {
    setBusy(true); setErr(null);
    try {
      const g = await sim.createGame("TRAINING", name.trim() || "Meu treino", `${year}-${String(month + 1).padStart(2, "0")}-01`);
      gameStore.set({ id: g.id, kind: "TRAINING", name: g.name });
      nav("/painel");
    } catch (e) { setErr(e instanceof Error ? e.message : "Erro"); setBusy(false); }
  };
  return (
    <div className="hub">
      <Link to="/" className="back">⬅ Voltar</Link>
      <section className="hero"><div><h1>🧪 Treinar investimentos</h1><p>Aqui você erra sem medo: o dinheiro é de mentirinha.</p></div></section>
      {err && <div className="alert">{err}</div>}
      <section className="panel stack">
        <div className="notice">⚠️ <b>Tudo aqui é simulado.</b> Nenhum dinheiro de verdade é usado e nada do que você fizer aqui vale como recomendação de investimento.</div>
        <label className="stack"><span>Nome do treino</span><input className="xl" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} /></label>
        <h2>⏪ Para quando você quer voltar no tempo?</h2>
        <div className="row">
          <select className="xl" value={month} onChange={(e) => setMonth(Number(e.target.value))}>{MONTHS.map((m, i) => <option key={m} value={i}>{m}</option>)}</select>
          <select className="xl" value={year} onChange={(e) => setYear(Number(e.target.value))}>{years.map((y) => <option key={y} value={y}>{y}</option>)}</select>
        </div>
        <p className="muted">Os preços serão os que existiam de verdade naquele mês. Depois é só avançar mês a mês e ver o que aconteceu — e você pode voltar no tempo de novo quando quiser.</p>
        <div><button className="btn primary big" disabled={busy} onClick={() => void go()}>{busy ? "Criando…" : "🚀 Começar o treino"}</button></div>
      </section>
    </div>
  );
}
