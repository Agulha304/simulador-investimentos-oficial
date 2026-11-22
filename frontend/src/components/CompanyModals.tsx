import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api, type CoCandidate, type CoCatalog, type CoHeadhunterResult, type CoRegime, type CoRelocateQuote, type CoSchedule, type CoSiteMode, type CompanyDetail, type Good } from "../services/api";
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

const SCHEDULES: { key: CoSchedule; label: string; hint: string }[] = [
  { key: "5x2", label: "5x2 (segunda a sexta)", hint: "padrão" },
  { key: "6x1", label: "6x1 (seis dias, uma folga)", hint: "pede um pequeno prêmio" },
  { key: "12x36", label: "12x36 (12 h trabalha, 36 h folga)", hint: "aceita desconto" },
  { key: "4x3", label: "4x3 (quatro dias, três de folga)", hint: "aceita desconto" },
];
const costMult = (regime: CoRegime) => (regime === "CLT" ? 2 : 1);
const fmtNum = (v: number) => fmtBRL(v.toFixed(2));

function Panel({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <div className="modal-back" onMouseDown={onClose}>
      <div className="card modal" style={wide ? { maxWidth: 820, width: "96vw" } : undefined} role="dialog" aria-label={title} onMouseDown={(e) => e.stopPropagation()}>
        <div className="row"><h2>{title}</h2><button type="button" className="link-btn" onClick={onClose}>fechar ✕</button></div>
        {children}
      </div>
    </div>
  );
}

function CandidateTable({ list, onPick }: { list: CoCandidate[]; onPick: (c: CoCandidate) => void }) {
  if (list.length === 0) return <div className="empty">Nenhum candidato disponível agora. Volte no próximo mês ou use o headhunter.</div>;
  return (
    <div className="table-wrap"><table>
      <thead><tr><th>Nome</th><th>Escolaridade</th><th className="r">Experiência</th><th>Nível</th><th className="r">Pretensão</th><th>Jornada preferida</th><th /></tr></thead>
      <tbody>{list.map((c) => (
        <tr key={c.id}>
          <td><b>{c.name}</b></td><td>{c.education_label}</td><td className="r num">{c.experience_years} ano(s)</td><td>{c.level_label}</td>
          <td className="r num">{fmtBRL(c.asking_salary)}</td><td>{c.hours_week} h/sem · {c.schedule}</td>
          <td className="r"><button type="button" className="btn small ghost" onClick={() => onPick(c)}>Fazer proposta</button></td>
        </tr>))}</tbody>
    </table></div>
  );
}

/** Popup de proposta: salário, horas por semana e escala; mostra o custo mensal REAL e a resposta do candidato. */
function OfferPopup({ d, cand, onClose, onAccepted, onRefused }: {
  d: CompanyDetail; cand: CoCandidate; onClose: () => void; onAccepted: (d: CompanyDetail, msg: string) => void; onRefused: (id: string, msg: string) => void;
}) {
  const [salary, setSalary] = useState(String(Math.round(Number(cand.asking_salary))));
  const [hours, setHours] = useState(String(cand.hours_week));
  const [schedule, setSchedule] = useState<CoSchedule>(cand.schedule);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [risk, setRisk] = useState<string | null>(null);
  const [counter, setCounter] = useState<{ value: string; text: string } | null>(null);
  const salaryNum = Number(parseMoneyInput(salary)) || 0;
  const hoursNum = Number(hours) || 0;
  async function send(value: string, confirmRisk: boolean) {
    setBusy(true); setMsg(null);
    try {
      const r = await api.coHire(d.company.id, { candidate_id: cand.id, salary: parseMoneyInput(value), hours_week: hoursNum, schedule, regime: cand.regime, confirm_risk: confirmRisk });
      if (r.status === "ACCEPTED" && r.company) onAccepted(r.company, r.message);
      else if (r.status === "COUNTER") { setCounter({ value: r.counter_offer ?? value, text: r.message }); setRisk(null); }
      else { setMsg(r.message); onRefused(cand.id, r.message); }
    } catch (err) {
      const m = errMsg(err);
      if (m.startsWith("RISCO")) setRisk(m); else setMsg(m);
    } finally { setBusy(false); }
  }
  const refused = msg != null && !risk && !counter && msg.includes("recusou");
  return (
    <Panel title={`Proposta para ${cand.name}`} onClose={onClose}>
      <p className="muted small" style={{ margin: 0 }}>{cand.role_label} · {cand.level_label} · {cand.education_label} · {cand.experience_years} ano(s) de experiência · pretensão {fmtBRL(cand.asking_salary)} · prefere {cand.hours_week} h/sem em {cand.schedule}.</p>
      <label>Salário mensal negociado (R$)<input inputMode="decimal" value={salary} onChange={(e) => { setSalary(e.target.value); setCounter(null); }} disabled={refused} /></label>
      <label>Horas por semana<input inputMode="numeric" value={hours} onChange={(e) => { setHours(e.target.value.replace(/\D/g, "")); setCounter(null); }} disabled={refused} /></label>
      <label>Escala<select value={schedule} onChange={(e) => { setSchedule(e.target.value as CoSchedule); setCounter(null); }} disabled={refused}>
        {SCHEDULES.map((x) => <option key={x.key} value={x.key}>{x.label} — {x.hint}</option>)}</select></label>
      <p className="card" style={{ margin: 0 }}>
        Custo mensal real: <b>{fmtNum(salaryNum * costMult(cand.regime))}</b> ({cand.regime === "CLT" ? "CLT: 2× o salário" : "PJ: 1× o salário"}) · custo de contratação: <b>{fmtNum(salaryNum * 0.5)}</b> (meio salário)
        {hoursNum > 44 && <><br /><span className="tone-warn">Jornada acima de 44 h/semana exige prêmio proporcional{hoursNum > 52 ? " e, acima de 52 h, pelo menos +40% sobre a pretensão" : ""}. Também aumenta o risco de processo se demitir.</span></>}
      </p>
      {counter && (
        <div className="ok">
          {counter.text}
          <div className="row-gap" style={{ marginTop: 8 }}>
            <button type="button" className="btn primary small" disabled={busy} onClick={() => { setSalary(String(Math.round(Number(counter.value)))); void send(counter.value, risk != null); }}>Aceitar contraproposta ({fmtBRL(counter.value)})</button>
          </div>
        </div>
      )}
      {risk && <div className="alert">{risk}</div>}
      {msg && <div className="alert">{msg}</div>}
      {!refused && <button type="button" className="btn primary" disabled={busy || salaryNum <= 0 || hoursNum < 20} onClick={() => void send(salary, risk != null)}>{busy ? "Enviando…" : risk ? "Propor assim mesmo" : "Propor"}</button>}
      {refused && <button type="button" className="btn ghost" onClick={onClose}>Voltar à lista</button>}
    </Panel>
  );
}

/** Contratação em passos: (a) cargo e regime, (b) candidatos, (c) proposta; (d) headhunter com briefing. */
export function HireModal({ d, initialRole, onClose, onDone, onChange }: {
  d: CompanyDetail; initialRole?: string; onClose: () => void; onDone: (d: CompanyDetail, msg: string) => void; onChange: (d: CompanyDetail) => void;
}) {
  const business = d.roles.filter((x) => !x.generic);
  const mandatory = d.roles.filter((x) => x.mandatory);
  const optional = d.roles.filter((x) => x.generic && !x.mandatory);
  const [role, setRole] = useState(initialRole ?? business[0]?.key ?? d.roles[0]?.key ?? "");
  const [regime, setRegime] = useState<CoRegime>("CLT");
  const [step, setStep] = useState<"role" | "list" | "headhunter">("role");
  const [list, setList] = useState<CoCandidate[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [offer, setOffer] = useState<CoCandidate | null>(null);
  const [maxSalary, setMaxSalary] = useState("");
  const [minLevel, setMinLevel] = useState("MID");
  const [hh, setHh] = useState<CoHeadhunterResult | null>(null);
  const r = d.roles.find((x) => x.key === role);
  const base = Number(r?.salary ?? 0);
  const present = (key: string) => d.compliance?.required.find((q) => q.role === key)?.present;

  async function loadList() {
    setBusy(true); setMsg(null);
    try { setList((await api.coCandidates(d.company.id, role, regime)).candidates); setStep("list"); }
    catch (err) { setMsg(errMsg(err)); } finally { setBusy(false); }
  }
  async function callHeadhunter() {
    setBusy(true); setMsg(null);
    try {
      const res = await api.coHeadhunter(d.company.id, { role, regime, max_salary: parseMoneyInput(maxSalary), min_level: minLevel });
      setHh(res); onChange(res.company);
    } catch (err) { setMsg(errMsg(err)); } finally { setBusy(false); }
  }
  const hhFee = (Number(parseMoneyInput(maxSalary)) || 0);
  const popup = offer && (
    <OfferPopup d={d} cand={offer} onClose={() => setOffer(null)} onAccepted={(next, m) => onDone(next, m)} onRefused={(id, m) => { setInfo(m); setList((l) => l.filter((x) => x.id !== id)); setHh((h) => h && { ...h, candidates: h.candidates.filter((x) => x.id !== id) }); }} />
  );
  return (
    <>
      <Panel title="Contratar funcionário" onClose={onClose} wide={step !== "role"}>
        {step === "role" && (
          <>
            <label>Cargo
              <select value={role} onChange={(e) => setRole(e.target.value)}>
                <optgroup label="Cargos do negócio">{business.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}</optgroup>
                <optgroup label="Cargos obrigatórios">{mandatory.map((x) => <option key={x.key} value={x.key}>{present(x.key) ? "✓" : "✗"} {x.label}</option>)}</optgroup>
                {optional.length > 0 && <optgroup label="Outros cargos gerais (opcionais)">{optional.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}</optgroup>}
              </select></label>
            <div className="seg" role="group" aria-label="Regime">
              <button type="button" className={regime === "CLT" ? "on" : ""} onClick={() => setRegime("CLT")}>CLT</button>
              <button type="button" className={regime === "PJ" ? "on" : ""} onClick={() => setRegime("PJ")}>PJ</button>
            </div>
            <p className="muted small" style={{ margin: 0 }}>
              {regime === "CLT"
                ? "CLT: a empresa paga 2× o salário combinado (encargos, benefícios, 13º e férias). Rescisão de 1 salário + aviso prévio; risco baixo de processo trabalhista (~6%)."
                : "PJ: a empresa paga 1× o salário combinado, sem encargos — mais barato. Mas, ao demitir, o risco de processo por reconhecimento de vínculo é muito maior (~35%) e sobe com jornada longa e escala 6x1."}
            </p>
            {r && <p className="card" style={{ margin: 0 }}>Custo mensal estimado ({r.label}, nível pleno, salário-base {fmtBRL(r.salary)}): <b>{fmtNum(base * costMult(regime))}</b> por mês. Custo de contratação: meio salário.{r.units === 0 ? " Este cargo não gera capacidade de produção." : ""}</p>}
            {msg && <div className="alert">{msg}</div>}
            <div className="row-gap" style={{ flexWrap: "wrap" }}>
              <button type="button" className="btn primary" disabled={busy || !role} onClick={() => void loadList()}>{busy ? "Buscando…" : "Ver candidatos"}</button>
              <button type="button" className="btn ghost" onClick={() => { setHh(null); setMaxSalary(String(Math.round(base * 1.3))); setStep("headhunter"); }}>Contratar via headhunter</button>
            </div>
          </>
        )}
        {step === "list" && (
          <>
            <p className="muted small" style={{ margin: 0 }}>{r?.label} · {regime} · candidatos do mês (a lista é a mesma até o fim do mês; quem recusa a sua proposta não volta a aparecer).</p>
            {info && <div className="alert">{info}</div>}
            <CandidateTable list={list} onPick={(c) => { setInfo(null); setOffer(c); }} />
            <button type="button" className="btn ghost small" onClick={() => { setStep("role"); setInfo(null); }}>← trocar cargo ou regime</button>
          </>
        )}
        {step === "headhunter" && (
          <>
            <p className="muted small" style={{ margin: 0 }}>Briefing para <b>{r?.label}</b> ({regime}). O headhunter cobra <b>1× o salário-teto</b> como honorário e devolve até 3 candidatos que cumprem o briefing. Se ninguém servir, cobra metade.</p>
            <label>Orçamento máximo de salário (R$)<input inputMode="decimal" value={maxSalary} onChange={(e) => { setMaxSalary(e.target.value); setHh(null); }} /></label>
            <label>Nível mínimo<select value={minLevel} onChange={(e) => { setMinLevel(e.target.value); setHh(null); }}>{Object.entries(LEVEL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            {!hh && <p className="card" style={{ margin: 0 }}>Honorário a pagar agora: <b>{fmtNum(hhFee)}</b> ({fmtNum(hhFee / 2)} se nenhum candidato servir). Caixa da empresa: {fmtBRL(d.company.cash)}.</p>}
            {msg && <div className="alert">{msg}</div>}
            {!hh && <button type="button" className="btn primary" disabled={busy || hhFee <= 0} onClick={() => void callHeadhunter()}>{busy ? "Procurando…" : `Confirmar e pagar ${fmtNum(hhFee)}`}</button>}
            {hh && (
              <>
                <div className={hh.found > 0 ? "ok" : "alert"}>{hh.message} Honorário cobrado: {fmtBRL(hh.fee)}.</div>
                {info && <div className="alert">{info}</div>}
                {hh.found > 0 && <CandidateTable list={hh.candidates} onPick={(c) => { setInfo(null); setOffer(c); }} />}
              </>
            )}
            <button type="button" className="btn ghost small" onClick={() => { setStep("role"); setHh(null); setInfo(null); }}>← trocar cargo ou regime</button>
          </>
        )}
      </Panel>
      {popup}
    </>
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

/** Mudança de endereço: escolha do local/modo/porte, orçamento da mudança (consulta ao servidor) e confirmação. */
export function RelocateModal({ d, onClose, onDone }: { d: CompanyDetail; onClose: () => void; onDone: (d: CompanyDetail) => void }) {
  const c = d.company;
  const [catalog, setCatalog] = useState<CoCatalog | null>(null);
  const [location, setLocation] = useState(c.location);
  const [mode, setMode] = useState<CoSiteMode>(c.site_mode ?? "RENT");
  const [size, setSize] = useState(c.size);
  const [quote, setQuote] = useState<CoRelocateQuote | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { api.coCatalog().then(setCatalog).catch((e) => setMsg(errMsg(e))); }, []);
  const seg = catalog?.segments.find((x) => x.key === c.segment);
  useEffect(() => {
    setQuote(null); setMsg(null);
    if (!seg) return;
    api.coRelocateQuote(c.id, { location, site_mode: mode, size }).then(setQuote).catch((e) => setMsg(errMsg(e)));
  }, [c.id, seg, location, mode, size]);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try { onDone(await api.coRelocate(c.id, { location, site_mode: mode, size })); } catch (err) { setMsg(errMsg(err)); setBusy(false); }
  }
  return (
    <Modal title="Mudar de endereço" onClose={onClose} onSubmit={submit}>
      <p className="muted small" style={{ margin: 0 }}>Use quando bater o teto de funcionários/estoque/produção do porte ou para ir a um ponto melhor. A mudança custa 3 meses do aluguel do novo ponto, a reinstalação (30% da estruturação) e, se você aluga, a multa de 2 aluguéis pelo contrato encerrado. A empresa fica parte do mês sem operar (vendas do fechamento caem para 35%) e perde parte da relevância — menos se o novo ponto tiver mais movimento. Funcionários e estoque ficam.</p>
      <label>Novo local
        <select value={location} onChange={(e) => setLocation(e.target.value)}>
          {(seg?.locations ?? []).map((l) => <option key={l.key} value={l.key}>{l.label} — movimento {l.demand.toFixed(2).replace(".", ",")}×{l.key === c.location ? " (atual)" : ""}</option>)}
        </select>
      </label>
      <div className="seg" role="group" aria-label="Terreno">
        <button type="button" className={mode === "RENT" ? "on" : ""} onClick={() => setMode("RENT")}>Alugar o ponto</button>
        <button type="button" className={mode === "BUY" ? "on" : ""} onClick={() => setMode("BUY")}>Comprar o terreno</button>
      </div>
      <label>Porte
        <select value={size} onChange={(e) => setSize(e.target.value)}>
          {(catalog?.sizes ?? []).map((z) => <option key={z.key} value={z.key}>{z.label}{z.key === c.size ? " (atual)" : ""}</option>)}
        </select>
      </label>
      {quote && (
        <dl className="facts">
          <div><dt>Mudança (3 meses de aluguel do novo ponto)</dt><dd className="num">{fmtBRL(quote.move)}</dd></div>
          <div><dt>Reinstalação</dt><dd className="num">{fmtBRL(quote.reinstall)}</dd></div>
          {Number(quote.fine) > 0 && <div><dt>Multa do contrato de aluguel encerrado</dt><dd className="num">{fmtBRL(quote.fine)}</dd></div>}
          {Number(quote.land_cost) > 0 && <div><dt>Compra do terreno</dt><dd className="num">{fmtBRL(quote.land_cost)}</dd></div>}
          {Number(quote.land_resale) > 0 && <div><dt>(−) Venda do terreno anterior</dt><dd className="num">{fmtBRL(quote.land_resale)}</dd></div>}
          <div><dt><b>Total a pagar pelo caixa da empresa</b></dt><dd className="num"><b>{fmtBRL(quote.total)}</b></dd></div>
          <div><dt>Relevância depois da mudança</dt><dd className="num">{c.relevance.toFixed(1).replace(".", ",")} → {quote.relevance_after.toFixed(1).replace(".", ",")}</dd></div>
        </dl>
      )}
      {msg && <div className="alert">{msg}</div>}
      <button className="btn primary" disabled={busy || !quote}>{busy ? "Mudando…" : "Confirmar mudança"}</button>
    </Modal>
  );
}
