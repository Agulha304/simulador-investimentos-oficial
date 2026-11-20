import { useEffect, useState } from "react";
import { fmtBRL } from "../lib/format";
import { sim, type BudgetImpact } from "../services/sim";

const ICON: Record<string, string> = { health: "❤️ Saúde", wellbeing: "😊 Bem-estar", satisfaction: "🌟 Satisfação", quality: "🏅 Qualidade de vida" };
const arrow = (n: number) => (n > 0 ? `▲ +${n}` : n < 0 ? `▼ ${n}` : "—");

/** Prévia ao vivo: cada mudança no orçamento do mês mexe com a sua saúde, o seu bem-estar e a sua satisfação. */
export function BudgetImpactCard({ version }: { version: string }) {
  const [d, setD] = useState<BudgetImpact | null>(null);
  useEffect(() => { sim.budgetImpact().then(setD).catch(() => setD(null)); }, [version]);
  if (!d) return null;
  const keys = ["health", "wellbeing", "satisfaction", "quality"] as const;
  return (
    <section className="card stack">
      <h2>🧬 Como este orçamento afeta você</h2>
      <p className="muted small" style={{ margin: 0 }}>O que você decide gastar (ou não) muda a sua vida no fim do mês. Mexa nos valores e veja a prévia aqui.</p>
      <div className="row">{keys.map((k) => <span key={k} className={`chip ${d.totals[k] > 0 ? "up" : d.totals[k] < 0 ? "down" : ""}`}>{ICON[k]} {arrow(d.totals[k])}</span>)}</div>
      {d.effects.length === 0 ? <p className="muted small">Nenhum efeito especial neste mês: seu orçamento está num nível neutro (ou ainda vazio).</p> : (
        <ul className="list-plain">{d.effects.map((e, i) => (
          <li key={i}><span>{e.text}{e.spend && <span className="muted small"> ({fmtBRL(e.spend)})</span>}</span>
            <span className="row small">{keys.filter((k) => e[k] !== 0).map((k) => <span key={k} className={e[k] > 0 ? "tone-up" : "tone-down"}>{ICON[k].split(" ")[0]} {arrow(e[k])}</span>)}</span></li>))}</ul>)}
    </section>
  );
}
