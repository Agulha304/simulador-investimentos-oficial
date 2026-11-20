import { useCallback, useEffect, useState } from "react";
import { fmtBRL } from "../lib/format";
import { sim, type Debt } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");

/** Empréstimos (com juros pela taxa da economia) e saldo negativo (cheque especial, com limite de R$ 100 mil). */
export function DebtCard({ onChange }: { onChange?: () => void }) {
  const [d, setD] = useState<Debt | null>(null);
  const [amount, setAmount] = useState("5000");
  const [term, setTerm] = useState(12);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => { sim.debt().then(setD).catch(() => setD(null)); }, []);
  useEffect(() => { load(); }, [load]);
  if (!d) return null;
  const run = async (fn: () => Promise<Debt>) => { setBusy(true); setErr(null); try { setD(await fn()); onChange?.(); } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); } };
  const od = Number(d.overdraft);
  const pct = Math.min(100, (od / Number(d.overdraft_limit)) * 100);
  return (
    <section className="card stack">
      <h2>💳 Empréstimos e saldo negativo</h2>
      <p className="muted small" style={{ margin: 0 }}>Se faltar dinheiro no fechamento do mês, o <b>saldo negativo</b> (cheque especial) cobre — mas os juros são altos ({d.overdraft_rate}% ao ano) e, se passar de {fmtBRL(d.overdraft_limit)} negativo, você vai à <b>falência</b>. Um empréstimo é mais barato ({d.loan_rate}% ao ano, a taxa depende da economia).</p>
      <div className={`meter ${pct > 70 ? "low" : pct > 30 ? "mid" : "high"}`}><div className="meter-top"><span>Saldo negativo usado</span><span className="num">{fmtBRL(d.overdraft)} / {fmtBRL(d.overdraft_limit)}</span></div><div className="meter-bar"><i style={{ width: `${pct}%` }} /></div></div>
      {err && <div className="alert">{err}</div>}
      {d.ended ? <p className="muted">Esta partida terminou.</p> : (
        <form className="row" onSubmit={(e) => { e.preventDefault(); void run(() => sim.takeLoan(amount, term)); }}>
          <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} aria-label="Valor do empréstimo" style={{ maxWidth: 140 }} />
          <select value={term} onChange={(e) => setTerm(Number(e.target.value))} aria-label="Prazo">{[6, 12, 24, 36, 48, 60].map((m) => <option key={m} value={m}>{m} meses</option>)}</select>
          <button className="btn primary small" disabled={busy}>Pedir empréstimo</button>
          <span className="muted small">limite disponível: {fmtBRL(d.credit_limit)}</span>
        </form>)}
      {d.loans.length > 0 && (
        <div className="table-wrap"><table><thead><tr><th>Empréstimo</th><th className="r">Saldo devedor</th><th className="r">Taxa</th><th className="r">Próxima parcela</th><th /></tr></thead>
          <tbody>{d.loans.map((l) => (
            <tr key={l.id}><td>{fmtBRL(l.principal)} em {l.term}x {l.status === "PAID" && <span className="chip up">quitado</span>}</td><td className="r num">{fmtBRL(l.balance)}</td><td className="r num">{l.rate}%</td>
              <td className="r num">{l.next_payment ? fmtBRL(l.next_payment) : "—"}</td>
              <td className="r">{l.status === "ACTIVE" && !d.ended && <button className="btn ghost small" disabled={busy} onClick={() => void run(() => sim.prepayLoan(l.id))}>Quitar</button>}</td></tr>))}</tbody></table></div>)}
    </section>
  );
}
