import { useState } from "react";
import { fmtBRL } from "../lib/format";
import { sim, type EcoEvent } from "../services/sim";

const KIND: Record<string, [string, string]> = { FINANCIAL: ["💰", "Decisão financeira"], PERSONAL: ["💖", "Decisão pessoal"], ECONOMIC: ["🌍", "Acontecimento"], BUSINESS: ["🏪", "Decisão da empresa"] };

/** Decisão do mês: aparece ANTES do resumo do fechamento. Uma de cada vez; o resultado só é mostrado depois da escolha. */
export function DecisionModal({ events, onDone }: { events: EcoEvent[]; onDone: () => void }) {
  const [i, setI] = useState(0);
  const [outcome, setOutcome] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const ev = events[i];
  const choose = async (key: string) => {
    setBusy(true); setErr(null);
    try { const r = await sim.ecoDecide(ev.id, key); setOutcome(r.event.outcome ?? "Feito!"); }
    catch (e) { setErr(e instanceof Error ? e.message : "Erro"); }
    finally { setBusy(false); }
  };
  const next = () => { setOutcome(null); if (i + 1 >= events.length) onDone(); else setI(i + 1); };
  const [emoji, label] = KIND[ev.category] ?? ["🎲", "Decisão"];
  return (
    <div className="modal-back" role="dialog" aria-modal="true" aria-label="Decisão do mês">
      <div className="card modal">
        <div className="row between"><span className="tag life">{emoji} {label}</span><span className="muted small">{i + 1} de {events.length}</span></div>
        <h2>{ev.name}</h2>
        <p>{ev.description}</p>
        {err && <div className="alert">{err}</div>}
        {outcome === null ? (
          <>
            <div className="stack">{ev.options?.map((o) => (
              <button key={o.key} className="btn ghost decision-opt" disabled={busy} onClick={() => void choose(o.key)}>
                <b>{o.label}</b>{o.cost ? <span className="chip warn">custa ~{fmtBRL(String(o.cost))}</span> : null}<span className="muted small">{o.hint}</span></button>))}</div>
            <p className="muted small">O resultado nem sempre é o esperado. Se você não escolher, vale a opção mais prudente.</p>
          </>
        ) : (
          <>
            <div className="notice">🎲 {outcome}</div>
            <button className="btn primary" onClick={next}>{i + 1 >= events.length ? "Ver o resumo do mês ▸" : "Próxima decisão ▸"}</button>
          </>)}
      </div>
    </div>
  );
}
