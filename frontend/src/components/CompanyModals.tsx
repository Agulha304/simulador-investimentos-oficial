import { useState, type FormEvent, type ReactNode } from "react";
import { api, type CompanyDetail, type Good } from "../services/api";
import { LEVEL_LABEL, fmtBRL, parseMoneyInput } from "../lib/format";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");

function Modal({ title, onClose, onSubmit, children }: { title: string; onClose: () => void; onSubmit: (e: FormEvent) => void; children: ReactNode }) {
  return (
    <div className="modal-back" onMouseDown={onClose}>
      <form className="card modal" onMouseDown={(e) => e.stopPropagation()} onSubmit={onSubmit}>
        <div className="row"><h2>{title}</h2><button type="button" className="link-btn" onClick={onClose}>fechar ✕</button></div>
        {children}
      </form>
    </div>
  );
}

/** Formulário genérico de valor (aporte, distribuição de lucros). */
export function MoneyModal({ title, hint, label, cta, run, onClose, onDone }: {
  title: string; hint: string; label: string; cta: string; run: (amount: string) => Promise<CompanyDetail>;
  onClose: () => void; onDone: (d: CompanyDetail) => void;
}) {
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try { onDone(await run(parseMoneyInput(amount))); } catch (err) { setMsg(errMsg(err)); setBusy(false); }
  }
  return (
    <Modal title={title} onClose={onClose} onSubmit={submit}>
      <p className="muted small" style={{ margin: 0 }}>{hint}</p>
      <label>{label}<input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required /></label>
      {msg && <div className="alert">{msg}</div>}
      <button className="btn primary" disabled={busy}>{busy ? "Enviando…" : cta}</button>
    </Modal>
  );
}

export function HireModal({ d, onClose, onDone }: { d: CompanyDetail; onClose: () => void; onDone: (d: CompanyDetail) => void }) {
  const [role, setRole] = useState(d.roles[0]?.key ?? "");
  const [level, setLevel] = useState("MID");
  const [risk, setRisk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const r = d.roles.find((x) => x.key === role);
  const mult = level === "JUNIOR" ? 0.8 : level === "SENIOR" ? 1.5 : 1;
  async function submit(e: FormEvent, confirm = false) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try { onDone(await api.coHire(d.company.id, role, level, confirm)); }
    catch (err) {
      const m = errMsg(err);
      if (m.startsWith("RISCO")) setRisk(m); else setMsg(m);
      setBusy(false);
    }
  }
  return (
    <Modal title="Contratar funcionário" onClose={onClose} onSubmit={(e) => submit(e, risk != null)}>
      <label>Cargo<select value={role} onChange={(e) => setRole(e.target.value)}>{d.roles.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}</select></label>
      <label>Nível<select value={level} onChange={(e) => setLevel(e.target.value)}>{Object.entries(LEVEL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      {r && <p className="muted small" style={{ margin: 0 }}>Salário {fmtBRL((Number(r.salary) * mult).toFixed(2))} + 35% de encargos. Custo de contratação: meio salário. Níveis mais altos produzem mais.</p>}
      {risk && <div className="alert">{risk}</div>}
      {msg && <div className="alert">{msg}</div>}
      <button className="btn primary" disabled={busy}>{busy ? "Contratando…" : risk ? "Contratar assim mesmo" : "Contratar"}</button>
    </Modal>
  );
}

export function LoanModal({ d, onClose, onDone }: { d: CompanyDetail; onClose: () => void; onDone: (d: CompanyDetail) => void }) {
  const [amount, setAmount] = useState("");
  const [term, setTerm] = useState("12");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try { onDone(await api.coLoan(d.company.id, parseMoneyInput(amount), Number(term))); } catch (err) { setMsg(errMsg(err)); setBusy(false); }
  }
  return (
    <Modal title="Empréstimo para a empresa" onClose={onClose} onSubmit={submit}>
      <p className="muted small" style={{ margin: 0 }}>Limite de crédito: {fmtBRL(d.loan_limit)}. Juros de 18% ao ano, parcelas Price a partir do mês seguinte. O dinheiro entra no caixa da empresa e vira dívida.</p>
      <label>Valor (R$)<input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required /></label>
      <label>Prazo (meses, até 60)<input inputMode="numeric" value={term} onChange={(e) => setTerm(e.target.value.replace(/\D/g, ""))} required /></label>
      {msg && <div className="alert">{msg}</div>}
      <button className="btn primary" disabled={busy}>{busy ? "Contratando…" : "Contratar empréstimo"}</button>
    </Modal>
  );
}

export function LeaseModal({ d, goods, onClose, onDone }: { d: CompanyDetail; goods: Good[]; onClose: () => void; onDone: (d: CompanyDetail) => void }) {
  const usable = goods.filter((g) => g.status === "ACTIVE" && g.occupancy && ["VACANT", "LISTED_FOR_RENT"].includes(g.occupancy) && g.category !== "LAND");
  const [mode, setMode] = useState<"EXTERNAL" | "OWN_GOOD">("EXTERNAL");
  const [goodId, setGoodId] = useState<number | "">(usable[0]?.id ?? "");
  const [rent, setRent] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try {
      onDone(await api.coLease(d.company.id, { kind: mode, ...(mode === "OWN_GOOD" && goodId !== "" ? { good_id: goodId } : {}), ...(rent ? { monthly_rent: parseMoneyInput(rent) } : {}) }));
    } catch (err) { setMsg(errMsg(err)); setBusy(false); }
  }
  return (
    <Modal title="Instalações da empresa" onClose={onClose} onSubmit={submit}>
      <div className="seg" role="group" aria-label="Tipo de instalação">
        <button type="button" className={mode === "EXTERNAL" ? "on" : ""} onClick={() => setMode("EXTERNAL")}>Alugar de terceiros</button>
        <button type="button" className={mode === "OWN_GOOD" ? "on" : ""} onClick={() => setMode("OWN_GOOD")} disabled={usable.length === 0}>Usar meu imóvel</button>
      </div>
      {mode === "OWN_GOOD" && (
        <>
          <label>Imóvel pessoal<select value={goodId} onChange={(e) => setGoodId(Number(e.target.value))}>{usable.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
          <p className="muted small" style={{ margin: 0 }}>A empresa paga o aluguel ao proprietário (você): sai do caixa empresarial e entra no seu orçamento pessoal como receita, todo mês no fechamento. O imóvel não pode ser vendido, alugado a terceiros nem usado por outra empresa enquanto o contrato durar.</p>
        </>
      )}
      <label>Aluguel mensal (R$) {mode === "EXTERNAL" ? "— vazio = valor de mercado da região" : ""}<input inputMode="decimal" value={rent} onChange={(e) => setRent(e.target.value)} /></label>
      {msg && <div className="alert">{msg}</div>}
      <button className="btn primary" disabled={busy}>{busy ? "Salvando…" : "Confirmar"}</button>
    </Modal>
  );
}
