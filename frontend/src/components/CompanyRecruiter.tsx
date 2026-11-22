import { useEffect, useState, type FormEvent } from "react";
import { api, type CoRecruiterReport, type CoRecruiterSettings, type CoRecruiterTier, type CoSchedule, type CoSupplierContract, type CoRegimePolicy, type CompanyDetail } from "../services/api";
import { REGIME_POLICY_LABEL, fmtBRL, parseMoneyInput } from "../lib/format";
import { Panel, lawsuitHistoryLabel } from "./CompanyModals";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
const SCHEDULE_HOURS: Record<CoSchedule, number> = { "6x1": 44, "5x2": 40, "12x36": 36, "4x3": 40 };
const SCHEDULE_LABEL: Record<CoSchedule, string> = { "5x2": "5x2 (segunda a sexta)", "6x1": "6x1 (seis dias, uma folga)", "12x36": "12x36", "4x3": "4x3 (quatro dias, três de folga)" };
const optMoney = (v: string) => (v.trim() ? parseMoneyInput(v) : null);
const optInt = (v: string) => (v.trim() ? Math.round(Number(v)) : null);
/** Campo OPCIONAL de fornecedor: vazio (ou zero) = sem restrição = null; nunca envia zero por padrão. */
const optLimit = (v: string) => { const m = optMoney(v); return m !== null && Number(m) > 0 ? m : null; };
const optLimitInt = (v: string) => { const n = optInt(v); return n !== null && n > 0 ? n : null; };
const optPct = (v: string) => (v.trim() ? Number(v.replace(",", ".")) / 100 : null);
const optLimitPct = (v: string) => { const n = optPct(v); return n !== null && Number.isFinite(n) && n > 0 ? n : null; };
const pctStr = (v: number | null | undefined) => (v == null ? "" : String(Math.round(v * 100)));
const numStr = (v: string | number | null | undefined) => (v == null ? "" : String(v));

/** Cartão "Contratador (headhunter)": serviço OPCIONAL. Sem contratador: explicação e níveis; com contratador: briefing e ações. */
export function RecruiterCard({ d, act, onReport, onTeam }: {
  d: CompanyDetail; act: (fn: () => Promise<CompanyDetail>, msg: string) => Promise<void>;
  onReport: (fn: () => Promise<CoRecruiterReport>) => Promise<void>; onTeam: () => void;
}) {
  const r = d.recruiter && d.recruiter.status === "ACTIVE" ? d.recruiter : null;
  const tiers = d.recruiter_tiers ?? [];
  const missing = d.compliance?.missing_labels ?? [];
  const noContract = (d.supply?.checklist ?? []).filter((x) => !x.present).map((x) => x.label);
  const id = d.company.id;
  return (
    <section className="card stack" aria-label="Contratador (headhunter)">
      <div className="row">
        <h2>Contratador (headhunter)</h2>
        {r && <span className="row-gap">
          <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>Trocar nível
            <select value={r.tier} aria-label="Trocar nível do contratador" onChange={(e) => void act(() => api.coRecruiterHire(id, e.target.value as CoRecruiterTier), "Nível do contratador alterado.")}>
              {tiers.map((t) => <option key={t.tier} value={t.tier}>{t.label} — {fmtBRL(t.monthly_fee)}/mês</option>)}</select></label>
          <button type="button" className="btn small ghost" onClick={() => window.confirm("Dispensar o contratador? Sem multa; a taxa mensal deixa de ser cobrada.") && void act(() => api.coRecruiterDismiss(id), "Contratador dispensado.")}>Dispensar</button>
        </span>}
      </div>
      {!r && (
        <>
          <p className="muted small" style={{ margin: 0 }}>
            <b>Opcional.</b> O contratador contrata por você: você dá o salário máximo e a escala; ele contrata sozinho os cargos obrigatórios, a equipe que você pedir (por cargo/área) e os
            fornecedores (se você quiser, respeitando limites opcionais de gasto, confiabilidade, prazo e volume; sem limites ele escolhe o melhor custo-benefício), ajustando salários e jornadas dentro do orçamento da empresa. Quanto melhor o nível, mais candidatos e
            fornecedores ele avalia e melhor o custo-benefício que consegue. Cobra uma taxa mensal (no fechamento) e uma comissão por contratação (no lugar do custo de recrutamento); pode ser dispensado a qualquer momento, sem multa.
          </p>
          <div className="goods-grid">{tiers.map((t) => (
            <div key={t.tier} className="card good-card"><b>{t.label}</b>
              <span className="num">{fmtBRL(t.monthly_fee)}/mês</span>
              <span className="muted small">comissão de {t.commission_pct}% do salário por contratação · avalia {t.pool} candidatos por vaga e {t.offers} fornecedores por categoria (acha {t.find_chance_pct}% deles) · desconto de negociação {String(t.discount_pct).replace(".", ",")}% · sucesso {t.success_pct}%</span>
              <button type="button" className="btn small primary" onClick={() => void act(() => api.coRecruiterHire(id, t.tier), `Contratador ${t.label} contratado: configure o briefing abaixo.`)}>Contratar contratador</button></div>
          ))}</div>
        </>
      )}
      {r && (
        <>
          <p className="muted small" style={{ margin: 0 }}>
            Nível <b>{r.tier_label}</b> · taxa mensal <b>{fmtBRL(r.monthly_fee)}</b> (no fechamento do mês, entra nos custos fixos) · comissão {r.commission_pct}% do salário por contratação · avalia {r.pool} candidatos por vaga e {r.offers} fornecedores por categoria · desconto de negociação {String(r.discount_pct).replace(".", ",")}% · sucesso {r.success_pct}%.
          </p>
          <BriefingForm d={d} s={r.settings} onSave={(b) => act(() => api.coRecruiterSettings(id, b), "Briefing do contratador salvo.")} />
          <div className="row-gap" style={{ flexWrap: "wrap" }}>
            <button type="button" className="btn small primary" disabled={missing.length === 0} title={missing.length ? `Faltam: ${missing.join(", ")}` : "Todos os cargos obrigatórios já estão preenchidos"}
              onClick={() => void onReport(() => api.coRecruiterMandatory(id))}>Contratar cargos obrigatórios{missing.length ? ` (${missing.length})` : ""}</button>
            <button type="button" className="btn small ghost" onClick={onTeam}>Contratar equipe…</button>
            {d.supply?.required && <button type="button" className="btn small ghost" disabled={noContract.length === 0} title={noContract.length ? `Sem contrato: ${noContract.join(", ")}` : "Todas as categorias já têm contrato"}
              onClick={() => void onReport(() => api.coRecruiterSuppliers(id))}>Contratar fornecedores{noContract.length ? ` (${noContract.length})` : ""}</button>}
          </div>
        </>
      )}
    </section>
  );
}

function BriefingForm({ d, s, onSave }: { d: CompanyDetail; s: CoRecruiterSettings; onSave: (b: CoRecruiterSettings) => Promise<void> }) {
  const cats = d.supply?.checklist ?? [];
  const [maxSalary, setMaxSalary] = useState(numStr(s.max_salary));
  const [schedule, setSchedule] = useState<CoSchedule>(s.schedule);
  const [hours, setHours] = useState(String(s.hours_week));
  const [policy, setPolicy] = useState<CoRegimePolicy>(s.regime_policy);
  const [payroll, setPayroll] = useState(numStr(s.max_monthly_payroll));
  const [total, setTotal] = useState(numStr(s.supplier_max_total_spend));
  const [rel, setRel] = useState(pctStr(s.supplier_min_reliability));
  const [lead, setLead] = useState(numStr(s.supplier_max_lead_days));
  const [vol, setVol] = useState(numStr(s.supplier_volume_cap));
  const [ov, setOv] = useState<Record<string, { spend: string; rel: string; lead: string; vol: string }>>({});
  useEffect(() => {
    setMaxSalary(numStr(s.max_salary)); setSchedule(s.schedule); setHours(String(s.hours_week)); setPolicy(s.regime_policy); setPayroll(numStr(s.max_monthly_payroll));
    setTotal(numStr(s.supplier_max_total_spend)); setRel(pctStr(s.supplier_min_reliability)); setLead(numStr(s.supplier_max_lead_days)); setVol(numStr(s.supplier_volume_cap));
    const o: Record<string, { spend: string; rel: string; lead: string; vol: string }> = {};
    for (const [k, v] of Object.entries(s.supplier_overrides ?? {})) o[k] = { spend: numStr(v.max_spend), rel: pctStr(v.min_reliability), lead: numStr(v.max_lead_days), vol: numStr(v.volume_cap) };
    setOv(o);
  }, [s]);
  const noSupLimits = !total && !rel && !lead && !vol && Object.values(ov).every((v) => !v.spend && !v.rel && !v.lead && !v.vol);
  const clearAllSup = () => { setTotal(""); setRel(""); setLead(""); setVol(""); setOv({}); };
  const setO = (k: string, f: "spend" | "rel" | "lead" | "vol", v: string) => setOv((p) => ({ ...p, [k]: { ...(p[k] ?? { spend: "", rel: "", lead: "", vol: "" }), [f]: v } }));
  function submit(e: FormEvent) {
    e.preventDefault();
    const overrides: CoRecruiterSettings["supplier_overrides"] = {};
    for (const [k, v] of Object.entries(ov)) {
      const o = { max_spend: optLimit(v.spend), min_reliability: optLimitPct(v.rel), max_lead_days: optLimitInt(v.lead), volume_cap: optLimit(v.vol) };
      if (Object.values(o).some((x) => x !== null)) overrides[k] = o;           // linha toda vazia = sem override
    }
    void onSave({
      max_salary: optMoney(maxSalary), schedule, hours_week: Number(hours) || SCHEDULE_HOURS[schedule], regime_policy: policy, max_monthly_payroll: optMoney(payroll),
      supplier_max_total_spend: optLimit(total), supplier_min_reliability: optLimitPct(rel), supplier_max_lead_days: optLimitInt(lead), supplier_volume_cap: optLimit(vol), supplier_overrides: overrides,
    });
  }
  return (
    <form className="stack" onSubmit={submit} aria-label="Briefing do contratador">
      <h3 style={{ margin: 0 }}>Briefing</h3>
      <div className="row-gap" style={{ maxWidth: "none", flexWrap: "wrap" }}>
        <label>Salário máximo por funcionário (R$)<input inputMode="decimal" value={maxSalary} onChange={(e) => setMaxSalary(e.target.value)} placeholder="obrigatório para contratar" /></label>
        <label>Escala<select value={schedule} onChange={(e) => { const v = e.target.value as CoSchedule; setSchedule(v); setHours(String(SCHEDULE_HOURS[v])); }}>
          {(Object.keys(SCHEDULE_LABEL) as CoSchedule[]).map((k) => <option key={k} value={k}>{SCHEDULE_LABEL[k]}</option>)}</select></label>
        <label>Horas por semana (máx. 44)<input inputMode="numeric" value={hours} onChange={(e) => setHours(e.target.value.replace(/\D/g, ""))} /></label>
        <label>Regime<select value={policy} onChange={(e) => setPolicy(e.target.value as CoRegimePolicy)}>
          {Object.entries(REGIME_POLICY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label>Teto de folha extra por operação (R$/mês, opcional)<input inputMode="decimal" value={payroll} onChange={(e) => setPayroll(e.target.value)} /></label>
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        {policy === "BOTH" ? "CLT e PJ: o contratador escolhe pelo histórico do funcionário — com processos trabalhistas anteriores contrata CLT (menor risco de vínculo e ação); sem histórico contrata PJ (mais barato) e, se não couber no teto, cai para CLT." : policy === "CLT_ONLY" ? "Só CLT: custo de 2× o salário, risco baixo de processo." : "Só PJ: custo de 1× o salário, mas risco alto de processo ao demitir."}
      </p>
      {d.supply?.required && (
        <>
          <div className="row"><h3 style={{ margin: 0 }}>Fornecedores (opcional)</h3>
            <button type="button" className="link-btn" onClick={clearAllSup}>limpar todas as restrições</button></div>
          <p className="muted small" style={{ margin: 0 }}>
            Tudo aqui é opcional: campo vazio = <b>sem limite</b> (o contratador escolhe o melhor custo-benefício disponível e as compras não são travadas por esse critério).
            {noSupLimits ? " Hoje o briefing não restringe nenhum fornecedor." : ""} A linha de uma categoria só vale se tiver algum campo preenchido; campo vazio na categoria usa o valor geral acima (ou nenhum).
          </p>
          <div className="row-gap" style={{ maxWidth: "none", flexWrap: "wrap" }}>
            <label>Gasto máximo total/mês (R$, opcional)<input inputMode="decimal" value={total} placeholder="sem limite" onChange={(e) => setTotal(e.target.value)} /></label>
            <label>Confiabilidade mínima (%, opcional)<input inputMode="numeric" value={rel} placeholder="sem limite" onChange={(e) => setRel(e.target.value)} /></label>
            <label>Prazo máximo (dias, opcional)<input inputMode="numeric" value={lead} placeholder="sem limite" onChange={(e) => setLead(e.target.value.replace(/\D/g, ""))} /></label>
            <label>Volume máximo/mês (unidades, opcional)<input inputMode="decimal" value={vol} placeholder="sem limite" onChange={(e) => setVol(e.target.value)} /></label>
          </div>
          <div className="table-wrap"><table>
            <thead><tr><th>Categoria (opcional; sobrepõe o geral)</th><th>Gasto máx. (R$)</th><th>Confiab. mín. (%)</th><th>Prazo máx. (dias)</th><th>Volume máx.</th><th /></tr></thead>
            <tbody>{cats.map((x) => {
              const v = ov[x.category] ?? { spend: "", rel: "", lead: "", vol: "" };
              const filled = !!(v.spend || v.rel || v.lead || v.vol);
              return (
                <tr key={x.category}><td><b>{x.label}</b>{!filled && <><br /><span className="muted small">sem limite</span></>}</td>
                  <td><input inputMode="decimal" placeholder="sem limite" aria-label={`Gasto máximo de ${x.label} (opcional)`} value={v.spend} onChange={(e) => setO(x.category, "spend", e.target.value)} /></td>
                  <td><input inputMode="numeric" placeholder="sem limite" aria-label={`Confiabilidade mínima de ${x.label} (opcional)`} value={v.rel} onChange={(e) => setO(x.category, "rel", e.target.value)} /></td>
                  <td><input inputMode="numeric" placeholder="sem limite" aria-label={`Prazo máximo de ${x.label} (opcional)`} value={v.lead} onChange={(e) => setO(x.category, "lead", e.target.value.replace(/\D/g, ""))} /></td>
                  <td><input inputMode="decimal" placeholder="sem limite" aria-label={`Volume máximo de ${x.label} (opcional)`} value={v.vol} onChange={(e) => setO(x.category, "vol", e.target.value)} /></td>
                  <td>{filled && <button type="button" className="link-btn" aria-label={`Limpar ${x.label}`} onClick={() => setOv((p) => ({ ...p, [x.category]: { spend: "", rel: "", lead: "", vol: "" } }))}>limpar</button>}</td></tr>);
            })}</tbody>
          </table></div>
        </>
      )}
      <div><button className="btn small primary">Salvar briefing</button></div>
    </form>
  );
}

/** Modal "Contratar equipe": steppers de quantidade por cargo/área do segmento. */
export function TeamModal({ d, onClose, onReport }: { d: CompanyDetail; onClose: () => void; onReport: (fn: () => Promise<CoRecruiterReport>) => Promise<void> }) {
  const [qty, setQty] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const total = Object.values(qty).reduce((a, b) => a + b, 0);
  const groups: [string, typeof d.roles][] = [["Cargos do negócio", d.roles.filter((x) => !x.generic)], ["Cargos gerais", d.roles.filter((x) => x.generic)]];
  const cap = d.market ? Math.max(d.market.max_staff - d.market.staff_count, 0) : null;
  async function go() {
    setBusy(true);
    await onReport(() => api.coRecruiterTeam(d.company.id, Object.entries(qty).filter(([, n]) => n > 0).map(([role, count]) => ({ role, count }))));
    setBusy(false);
  }
  return (
    <Panel title="Contratar equipe via contratador" onClose={onClose}>
      <p className="muted small" style={{ margin: 0 }}>
        Escolha quantos funcionários de cada área você quer. O contratador ranqueia por custo-benefício (produtividade ÷ custo mensal real) e contrata os melhores que cabem no salário máximo, no teto de funcionários{cap != null ? ` (cabem mais ${cap})` : ""}, no teto de folha extra e no caixa (a empresa precisa seguir com pelo menos 2 meses de folga).
      </p>
      {groups.map(([title, roles]) => roles.length > 0 && (
        <div key={title}><b className="small">{title}</b>
          <ul className="list-plain">{roles.map((x) => (
            <li key={x.key}><span>{x.label} <span className="muted small">· base {fmtBRL(x.salary)}</span></span>
              <span className="row-gap">
                <button type="button" className="btn small ghost" aria-label={`Menos ${x.label}`} onClick={() => setQty((q) => ({ ...q, [x.key]: Math.max((q[x.key] ?? 0) - 1, 0) }))}>−</button>
                <b className="num" aria-label={`Quantidade de ${x.label}`}>{qty[x.key] ?? 0}</b>
                <button type="button" className="btn small ghost" aria-label={`Mais ${x.label}`} onClick={() => setQty((q) => ({ ...q, [x.key]: Math.min((q[x.key] ?? 0) + 1, 20) }))}>+</button>
              </span></li>))}</ul>
        </div>))}
      <button type="button" className="btn primary" disabled={busy || total === 0} onClick={() => void go()}>{busy ? "Contratando…" : `Contratar ${total} funcionário(s)`}</button>
    </Panel>
  );
}

/** Relatório do resultado de uma operação do contratador: contratados, não contratados (com motivo) e custo total. */
export function ReportPanel({ r, onClose }: { r: CoRecruiterReport; onClose: () => void }) {
  return (
    <Panel title="Resultado do contratador" onClose={onClose} wide>
      <div className={r.hired.length + r.contracted.length > 0 ? "ok" : "alert"}>{r.message}{r.replayed ? " (operação já registrada: nada foi cobrado de novo)" : ""}</div>
      {r.hired.length > 0 && (
        <div className="table-wrap"><table>
          <thead><tr><th>Contratado</th><th>Regime</th><th className="r">Salário</th><th>Jornada · escala</th><th className="r">Custo mensal</th><th className="r">Comissão</th><th>Histórico</th></tr></thead>
          <tbody>{r.hired.map((h, i) => (
            <tr key={i}><td><b>{h.name}</b><br /><span className="muted small">{h.role_label}</span></td>
              <td><span className={`chip ${h.regime === "CLT" ? "up" : "down"}`}>{h.regime}</span><br /><span className="muted small">{h.why_regime}</span></td>
              <td className="r num">{fmtBRL(h.salary)}</td><td>{h.hours_week} h · {h.schedule}</td><td className="r num">{fmtBRL(h.monthly_cost)}</td><td className="r num">{fmtBRL(h.commission)}</td>
              <td>{lawsuitHistoryLabel(h.lawsuit_history)}</td></tr>))}</tbody>
        </table></div>
      )}
      {r.contracted.length > 0 && (
        <div className="table-wrap"><table>
          <thead><tr><th>Categoria</th><th>Fornecedor</th><th className="r">Preço negociado</th><th className="r">Volume/mês</th><th className="r">Gasto previsto</th><th>Confiab. · prazo</th></tr></thead>
          <tbody>{r.contracted.map((c) => (
            <tr key={c.category}><td><b>{c.label}</b></td><td>{c.supplier}</td><td className="r num">{fmtBRL(c.unit_price)}/{c.unit}<br /><span className="muted small">ref. {fmtBRL(c.reference_price)}</span></td>
              <td className="r num">{c.volume} {c.unit}</td><td className="r num">{fmtBRL(c.expected_spend)}</td><td>{Math.round(c.reliability * 100)}% · {c.lead_days} d</td></tr>))}</tbody>
        </table></div>
      )}
      {r.skipped.length > 0 && (
        <div><b className="small">Não contratado</b>
          <ul className="list-plain">{r.skipped.map((s, i) => (
            <li key={i}><span><b>{s.role_label ?? s.label}</b>{s.missing != null ? ` (faltaram ${s.missing} de ${s.requested})` : ""}</span><span className="tone-warn small">{s.reason}</span></li>))}</ul>
        </div>
      )}
      <p className="muted small" style={{ margin: 0 }}>
        {r.hired.length > 0 && <>Custo mensal adicionado: <b>{fmtBRL(r.total_monthly_cost)}</b> · comissão total paga agora: <b>{fmtBRL(r.total_commission)}</b>. </>}
        {r.contracted.length > 0 && <>Gasto mensal previsto com os novos fornecedores: <b>{fmtBRL(r.total_expected_spend)}</b>.</>}
      </p>
      <button type="button" className="btn ghost" onClick={onClose}>Fechar</button>
    </Panel>
  );
}

/** Limites de UM contrato de fornecedor: gasto e volume (valem nas compras) e confiabilidade/prazo (critérios do contratador). */
export function SupplierLimitsModal({ d, ct, onClose, onDone }: { d: CompanyDetail; ct: CoSupplierContract; onClose: () => void; onDone: (d: CompanyDetail) => void }) {
  const [spend, setSpend] = useState(numStr(ct.max_monthly_spend));
  const [vol, setVol] = useState(numStr(ct.volume_cap));
  const [rel, setRel] = useState(pctStr(ct.min_reliability));
  const [lead, setLead] = useState(numStr(ct.max_lead_days));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try { onDone(await api.coSupplierLimits(d.company.id, ct.id, { max_monthly_spend: optLimit(spend), volume_cap: optLimit(vol), min_reliability: optLimitPct(rel), max_lead_days: optLimitInt(lead) })); }
    catch (err) { setMsg(errMsg(err)); setBusy(false); }
  }
  return (
    <Panel title={`Limites — ${ct.name}`} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <p className="muted small" style={{ margin: 0 }}>{ct.category_label}. Todos os limites são <b>opcionais</b>: campo vazio = <b>sem limite</b>. Gasto máximo e volume máximo são aplicados em TODA compra (manual e reposição automática): ao atingi-los a compra trava e a tela explica. Confiabilidade mínima e prazo máximo são critérios do contratador ao renovar ou trocar o fornecedor.</p>
        <label>Gasto máximo por mês (R$, opcional)<input inputMode="decimal" value={spend} placeholder="sem limite" onChange={(e) => setSpend(e.target.value)} /></label>
        <label>Volume máximo por mês ({ct.unit}; contrato: {ct.max_units_month}; opcional)<input inputMode="decimal" value={vol} placeholder="sem limite" onChange={(e) => setVol(e.target.value)} /></label>
        <label>Confiabilidade mínima (%, opcional)<input inputMode="numeric" value={rel} placeholder="sem limite" onChange={(e) => setRel(e.target.value)} /></label>
        <label>Prazo máximo (dias, opcional)<input inputMode="numeric" value={lead} placeholder="sem limite" onChange={(e) => setLead(e.target.value.replace(/\D/g, ""))} /></label>
        <div><button type="button" className="link-btn" disabled={!spend && !vol && !rel && !lead} onClick={() => { setSpend(""); setVol(""); setRel(""); setLead(""); }}>limpar todos os limites</button></div>
        {msg && <div className="alert">{msg}</div>}
        <button className="btn primary" disabled={busy}>{busy ? "Salvando…" : "Salvar limites"}</button>
      </form>
    </Panel>
  );
}
