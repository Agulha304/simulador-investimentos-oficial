import { useState } from "react";
import { api, type CoAideKind, type CompanyDetail } from "../services/api";
import { fmtBRL, fmtMonth } from "../lib/format";
import { AideBox } from "./CompanyGrowth";
import { RecruiterCard } from "./CompanyRecruiter";

type Act = (fn: () => Promise<CompanyDetail>, msg: string) => Promise<void>;
export type StaffKind = CoAideKind | "RECRUITER";
const LABEL: Record<StaffKind, string> = { MARKETER: "Marketeiro", MANAGER: "Gerente", CEO: "CEO", RECRUITER: "Contratador (headhunter)" };

/** Profissionais de gestão contratados (marketeiro, gerente, CEO, contratador): aparecem como funcionários, com briefing. */
export function staffList(d: CompanyDetail): { kind: StaffKind; title: string; level: string; fee: string; since: string }[] {
  const out: { kind: StaffKind; title: string; level: string; fee: string; since: string }[] = [];
  const a = d.aides;
  if (a?.marketer) out.push({ kind: "MARKETER", title: LABEL.MARKETER, level: a.marketer.label, fee: a.marketer.fee, since: a.marketer.hired_month });
  if (a?.manager) out.push({ kind: "MANAGER", title: LABEL.MANAGER, level: a.manager.label, fee: a.manager.fee, since: a.manager.hired_month });
  if (a?.ceo) out.push({ kind: "CEO", title: LABEL.CEO, level: a.ceo.label, fee: a.ceo.fee, since: a.ceo.hired_month });
  if (d.recruiter && d.recruiter.status === "ACTIVE") out.push({ kind: "RECRUITER", title: LABEL.RECRUITER, level: d.recruiter.tier_label, fee: d.recruiter.monthly_fee, since: d.recruiter.hired_month });
  return out;
}

export function StaffRows({ d, act, onBriefing }: { d: CompanyDetail; act: Act; onBriefing: (k: StaffKind) => void }) {
  const id = d.company.id;
  return (
    <>{staffList(d).map((s) => (
      <tr key={s.kind}>
        <td><b>{s.title}</b><br /><span className="muted small">{s.level} · gestão</span></td>
        <td><span className="chip">Contrato</span></td><td className="muted small">—</td><td className="muted small">—</td><td className="muted small">—</td>
        <td className="r num">{fmtBRL(s.fee)}</td><td className="r num">{fmtBRL(s.fee)}<br /><span className="muted small">taxa mensal</span></td>
        <td>desde {fmtMonth(s.since)}</td>
        <td className="r"><button className="btn small" onClick={() => onBriefing(s.kind)}>Briefing</button>{" "}
          <button className="link-btn" onClick={() => window.confirm(`Dispensar ${s.title}? Sem multa.`) && void act(() => (s.kind === "RECRUITER" ? api.coRecruiterDismiss(id) : api.coAideDismiss(id, s.kind as CoAideKind)), `${s.title} dispensado.`)}>dispensar</button></td>
      </tr>))}</>
  );
}

/** Popup do briefing do profissional de gestão (o mesmo conteúdo de antes, em janela). */
export function StaffBriefing({ d, kind, act, onClose, onReport, onTeam }: {
  d: CompanyDetail; kind: StaffKind; act: Act; onClose: () => void; onReport: (fn: () => Promise<never>) => Promise<void>; onTeam: () => void;
}) {
  return (
    <div className="modal-back" role="dialog" aria-modal="true" aria-label={`Briefing: ${LABEL[kind]}`}>
      <div className="card modal" style={{ maxWidth: 820, maxHeight: "88vh", overflow: "auto" }}>
        <div className="row between"><h2>Briefing — {LABEL[kind]}</h2><button className="link-btn" onClick={onClose}>fechar ✕</button></div>
        {kind === "RECRUITER" ? <RecruiterCard d={d} act={act} onReport={onReport as never} onTeam={() => { onClose(); onTeam(); }} /> : <AideBox d={d} kind={kind} title={LABEL[kind]} act={act} id={d.company.id} />}
      </div>
    </div>
  );
}

/** Opções de contratação de gestão (marketeiro, gerente, CEO e contratador) por nível, dentro do modal de contratar funcionário. */
export function HireStaff({ d, kind, onDone }: { d: CompanyDetail; kind: StaffKind; onDone: (d: CompanyDetail, msg: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const id = d.company.id;
  const opts = kind === "RECRUITER"
    ? (d.recruiter_tiers ?? []).map((t) => ({ level: t.tier, label: t.label, fee: t.monthly_fee, note: `comissão de ${t.commission_pct}% por contratação · avalia ${t.pool} candidatos por vaga` }))
    : (kind === "MARKETER" ? d.aide_options?.marketer : kind === "CEO" ? d.aide_options?.ceo : d.aide_options?.manager)?.map((o) => ({ level: o.level, label: o.label, fee: o.fee, note: "" })) ?? [];
  const current = kind === "RECRUITER" ? d.recruiter?.status === "ACTIVE" : !!(kind === "MARKETER" ? d.aides?.marketer : kind === "CEO" ? d.aides?.ceo : d.aides?.manager);
  async function hire(level: string) {
    setBusy(true); setErr(null);
    try { const r = kind === "RECRUITER" ? await api.coRecruiterHire(id, level as never) : await api.coAideHire(id, kind as CoAideKind, level as never); onDone(r, `${LABEL[kind]} contratado: configure o briefing pelo botão "Briefing" na lista de funcionários.`); }
    catch (e) { setErr(e instanceof Error ? e.message : "Erro inesperado"); } finally { setBusy(false); }
  }
  const blurb: Record<StaffKind, string> = {
    MARKETER: "Gasta o orçamento mensal que você definir em campanhas; quanto melhor o nível, maior a chance de dar certo.",
    MANAGER: "Aumenta a produtividade; quanto mais rígido, mais rende, mas funcionários podem pedir demissão.",
    CEO: "Toca a empresa por você: faz uma melhoria por mês (custos, marca, qualidade ou processos) e envia um relatório mensal.",
    RECRUITER: "Contrata por você: obrigatórios, equipe e fornecedores, seguindo o seu briefing.",
  };
  return (
    <>
      <p className="muted small" style={{ margin: 0 }}>{blurb[kind]} Cobra uma taxa mensal (como salário) e pode ser dispensado sem multa.</p>
      {current && <div className="notice">Você já tem um {LABEL[kind].toLowerCase()}: dispense-o na lista de funcionários para contratar outro nível.</div>}
      {err && <div className="alert">{err}</div>}
      <div className="goods-grid">{opts.map((o) => (
        <div key={o.level} className="card good-card"><b>{o.label}</b><span className="num">{fmtBRL(o.fee)}/mês</span>{o.note && <span className="muted small">{o.note}</span>}
          <button type="button" className="btn small primary" disabled={busy || current} onClick={() => void hire(o.level)}>Contratar</button></div>))}</div>
    </>
  );
}
