import { useCallback, useEffect, useState } from "react";
import { Toast } from "./Toast";
import { fmtBRL } from "../lib/format";
import { sim, type ArtistView, type PoliticsView } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
const pct = (v: number) => `${Math.round(v * 100)}%`;

/** Carreira política: partido, lado político, propostas, postura com a mídia, candidatura, campanha (marqueteiro, comícios), mandato e polêmicas. */
export function PoliticsTab() {
  const [v, setV] = useState<PoliticsView | null>(null);
  const [dec, setDec] = useState<ArtistView["decisions"][number] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [spend, setSpend] = useState("10000");
  const loadDec = useCallback(() => { sim.artist().then((a) => setDec(a.decisions[0] ?? null)).catch(() => undefined); }, []);
  useEffect(() => { sim.politics().then(setV).catch((e) => setErr(errMsg(e))); loadDec(); }, [loadDec]);
  const run = useCallback(async (path: string, method: "POST" | "PUT" | "DELETE" = "POST", body?: unknown) => {
    setBusy(true); setErr(null); setNote(null);
    try { const r = await sim.polDo(path, method, body); setV(r); setNote(r.result?.message ?? null); } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  }, []);
  const decide = async (id: number, option: string) => {
    setBusy(true); setErr(null);
    try { const r = await sim.artistDo(`/decisions/${id}`, "POST", { option }); setNote(r.result?.message ?? null); setDec(r.decisions[0] ?? null); setV(await sim.politics()); } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  };
  if (!v) return err ? <div className="alert">{err}</div> : <div className="muted">Carregando…</div>;
  const pr = v.profile;
  const party = v.catalog.parties.find((p) => p.key === pr.party);
  const running = v.campaigns.filter((c) => c.status === "RUNNING");
  const activeTerms = v.terms.filter((t) => t.status === "ACTIVE");
  return (
    <>
      {err && <div className="alert">{err}</div>}
      {note && <Toast text={note} onClose={() => setNote(null)} />}
      <section className="card stack">
        <div className="row-gap" style={{ flexWrap: "wrap" }}>
          <span className="chip">Fama política <b>{v.fame}</b></span><span className="chip">Habilidade <b>{v.skill}</b></span><span className="chip">Relevância pública <b>{v.relevance}</b></span>
          <span className="chip">Idade <b>{v.age}</b></span>
        </div>
        <span className="muted small">Cargos exigem idade mínima, filiação a um partido com {6} meses de antecedência e propostas definidas. Diplomas de direito, administração, economia, relações internacionais e matemática ajudam. Polêmicas aparecem como decisões e mexem na sua relevância.</span>
      </section>
      <section className="card stack">
        <h3>Perfil político</h3>
        <div className="row-gap" style={{ flexWrap: "wrap" }}>
          <label>Partido<select value={pr.party ?? ""} disabled={busy} onChange={(e) => e.target.value && void run("/profile", "PUT", { party: e.target.value })}><option value="">Filie-se…</option>{v.catalog.parties.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}</select></label>
          <label>Lado político<select value={pr.ideology} disabled={busy} onChange={(e) => void run("/profile", "PUT", { ideology: e.target.value })}>{v.catalog.ideologies.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}</select></label>
          <label>Postura com a mídia<select value={pr.media} disabled={busy} onChange={(e) => void run("/profile", "PUT", { media: e.target.value })}>{v.catalog.media.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}</select></label>
        </div>
        <span className="muted small">{v.catalog.media.find((m) => m.key === pr.media)?.desc}{party ? ` Partido com força ${pct(party.strength)}${pr.joined ? `, filiado desde ${pr.joined.slice(0, 7)}` : ""}.` : ""}</span>
        <b className="small">Propostas (até {v.catalog.max_proposals})</b>
        <div className="row-gap" style={{ flexWrap: "wrap" }}>{v.catalog.proposals.map((p) => (
          <label key={p.key} className="check"><input type="checkbox" checked={pr.proposals.includes(p.key)} disabled={busy || (!pr.proposals.includes(p.key) && pr.proposals.length >= v.catalog.max_proposals)}
            onChange={() => void run("/profile", "PUT", { proposals: pr.proposals.includes(p.key) ? pr.proposals.filter((x) => x !== p.key) : [...pr.proposals, p.key] })} />{p.name}</label>))}</div>
      </section>
      {activeTerms.map((t) => (
        <section key={t.id} className="card stack">
          <div className="row between"><h3>Mandato: {t.name}</h3><span className="chip">aprovação {t.approval}%</span></div>
          <span className="muted small">Subsídio bruto {fmtBRL(String(t.salary))}/mês · de {t.start.slice(0, 7)} a {t.end.slice(0, 7)}</span>
          <div className="row-gap" style={{ flexWrap: "wrap" }}>
            <button className="btn primary small" disabled={busy} onClick={() => void run(`/terms/${t.id}/action`, "POST", { kind: "bill" })}>Propor projeto de lei (10h)</button>
            <button className="btn small" disabled={busy} onClick={() => void run(`/terms/${t.id}/action`, "POST", { kind: "town_hall" })}>Reunião com a população (8h)</button>
            <button className="btn danger small" disabled={busy} onClick={() => window.confirm("Renunciar ao mandato?") && void run(`/terms/${t.id}`, "DELETE")}>Renunciar</button>
          </div>
        </section>))}
      {running.map((c) => (
        <section key={c.id} className="card stack">
          <div className="row between"><h3>{c.name}</h3><span className="chip">eleição em {c.election.slice(0, 7)}</span></div>
          <div className="stats-grid">
            <div className="card"><span className="muted small">Chance estimada</span><b className="num">{c.estimate ? pct(c.estimate.win_chance) : "—"}</b></div>
            <div className="card"><span className="muted small">Embalo da campanha</span><b className="num">{c.momentum}/100</b></div>
            <div className="card"><span className="muted small">Gasto até agora</span><b className="num">{fmtBRL(String(c.spent))}</b></div>
          </div>
          <b className="small">Marqueteiro de campanha</b>
          <div className="row-gap" style={{ flexWrap: "wrap" }}>{v.catalog.marketers.map((m) => (
            <button key={m.key} className={`btn small ${c.marketer === m.key ? "primary" : "ghost"}`} disabled={busy} onClick={() => void run(`/campaigns/${c.id}/marketer`, "POST", { level: m.key })}>{m.name} — {fmtBRL(String(m.fee))}/mês</button>))}
            {c.marketer && <button className="btn small danger" disabled={busy} onClick={() => void run(`/campaigns/${c.id}/marketer`, "DELETE")}>Dispensar</button>}</div>
          <b className="small">Ações de campanha (uma de cada por mês)</b>
          <div className="row-gap" style={{ flexWrap: "wrap" }}>{v.catalog.rallies.map((r) => (
            <button key={r.key} className="btn small" disabled={busy || c.done.some((d) => d.includes(r.key))} onClick={() => void run(`/campaigns/${c.id}/rally`, "POST", { kind: r.key })}>{r.name} — {fmtBRL(String(r.cost))}</button>))}</div>
          <div className="row-gap"><input inputMode="decimal" value={spend} onChange={(e) => setSpend(e.target.value)} style={{ width: 120 }} aria-label="Valor" />
            <button className="btn small" disabled={busy} onClick={() => void run(`/campaigns/${c.id}/spend`, "POST", { amount: Number(spend.replace(/\./g, "").replace(",", ".")) })}>Investir na campanha</button>
            <button className="btn danger small" disabled={busy} onClick={() => window.confirm("Desistir da candidatura?") && void run(`/campaigns/${c.id}`, "DELETE")}>Desistir</button></div>
        </section>))}
      <section className="card stack">
        <h3>Cargos e eleições</h3>
        <div className="table-wrap"><table>
          <thead><tr><th>Cargo</th><th>Esfera</th><th className="r">Subsídio</th><th className="r">Campanha competitiva</th><th>Eleição</th><th className="r">Chance hoje</th><th></th></tr></thead>
          <tbody>{v.offices.map((o) => (
            <tr key={o.key}><td>{o.name}<br /><span className="muted small">idade mínima {o.min_age}</span></td><td>{o.sphere}</td><td className="r num">{fmtBRL(String(o.salary))}</td><td className="r num">{fmtBRL(String(o.campaign_cost))}</td>
              <td>{o.election.slice(0, 7)}</td><td className="r num">{o.estimate ? pct(o.estimate.win_chance) : "—"}</td>
              <td>{o.can_run ? <button className="btn primary small" disabled={busy} onClick={() => void run("/candidacy", "POST", { office: o.key })}>Candidatar-me</button> : <span className="muted small">{o.blocked_by.join("; ")}</span>}</td></tr>))}</tbody>
        </table></div>
      </section>
      {v.campaigns.filter((c) => c.status !== "RUNNING").length > 0 && <><h3>Histórico eleitoral</h3><ul className="list-plain">{v.campaigns.filter((c) => c.status !== "RUNNING").map((c) => <li key={c.id}><span>{c.name}</span><span className={`chip ${c.status === "WON" ? "up" : "down"}`}>{c.status === "WON" ? "eleito(a)" : c.status === "LOST" ? "não eleito(a)" : "desistiu"}</span></li>)}</ul></>}
      {dec && (
        <div className="modal-back" role="dialog" aria-modal="true" aria-label="Situação">
          <div className="card modal"><h2>{dec.title}</h2><p className="muted small">{dec.desc}</p>
            {dec.options.map((o) => (
              <div key={o.key} className="card stack" style={{ marginBottom: 8 }}><b>{o.label}{o.cost ? ` — ${fmtBRL(String(o.cost))}` : ""}</b>
                <div><button className="btn primary small" disabled={busy} onClick={() => void decide(dec.id, o.key)}>Escolher</button></div></div>))}</div>
        </div>)}
    </>
  );
}
