import { useCallback, useEffect, useState } from "react";
import { Toast } from "../components/Toast";
import { fmtBRL } from "../lib/format";
import { sim, type Abroad, type AbroadCost } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
const KIND: Record<string, string> = { IDIOMA: "Idioma", ACADEMICO: "Acadêmico", TECNICO: "Curso técnico", BOLSA: "Bolsa", ESTAGIO: "Estágio" };
const FIELD: Record<string, string> = { geral: "pontos gerais", tecnologia: "Tecnologia", saude: "Saúde", engenharia: "Engenharia", financas: "Finanças", direito: "Direito", educacao: "Educação",
  comercio: "Comércio", artes: "Artes", agro: "Agro", gastronomia: "Gastronomia", logistica: "Logística", seguranca: "Segurança", industria: "Indústria", ciencia: "Ciência" };

function Cost({ c }: { c: AbroadCost }) {
  const l = c.living_month;
  return (
    <span className="muted small">
      Saída (passagem {fmtBRL(c.upfront.flight)} + visto/seguro {fmtBRL(c.upfront.visa)} + instalação {fmtBRL(c.upfront.deposit)}) = <b>{fmtBRL(c.upfront.total)}</b> ·
      por mês: vida lá <b>{fmtBRL(l.total)}</b> (aluguel {fmtBRL(l.rent)}, comida {fmtBRL(l.food)}, contas {fmtBRL(l.utilities)}, transporte {fmtBRL(l.transport)}, saúde {fmtBRL(l.health)})
      {Number(c.tuition_month) > 0 ? <> + curso {fmtBRL(c.tuition_month)}</> : null}{Number(c.stipend_month) > 0 ? <> − bolsa/estágio {fmtBRL(c.stipend_month)}</> : null}
      {c.total ? <> · total do programa ≈ <b>{fmtBRL(c.total)}</b></> : null} · câmbio hoje: 1 {c.currency} = R$ {Number(c.rate).toFixed(4)} (inclui IOF e spread)
    </span>
  );
}

/** Mundo: intercâmbio, morar em outro país e voltar. Tudo cobrado em moeda local, convertido pelo câmbio do mês. */
export function WorldPage() {
  const [a, setA] = useState<Abroad | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => { sim.lifeAbroad().then(setA).catch((x) => setErr(errMsg(x))); }, []);
  useEffect(() => { load(); }, [load]);
  const act = async (fn: () => Promise<unknown>, ok: (r: unknown) => string) => {
    setBusy(true); setErr(null); setNote(null);
    try { setNote(ok(await fn())); } catch (x) { setErr(errMsg(x)); } finally { setBusy(false); load(); }
  };
  if (!a) return err ? <div className="alert">{err}</div> : <div className="muted">Carregando…</div>;
  const abroad = a.country !== "BR";
  return (
    <div className="page">
      <header className="page-head"><div><h1>✈️ Mundo</h1>
        <p className="muted">Faça intercâmbio ou mude de país. Fora do Brasil você paga a vida na moeda local (convertida pelo câmbio do mês, com IOF e spread). Quem viaja larga os empregos presenciais do Brasil (os remotos continuam); amigos, namorados e família podem se afastar ou romper.</p></div></header>
      {err && <div className="alert">{err}</div>}
      {note && <Toast text={note} onClose={() => setNote(null)} />}
      <section className="card stack">
        <h2>{a.flag} Você mora em: {a.country_name}</h2>
        {abroad ? <>
          <span className="muted small">Desde {a.since?.slice(0, 7)} · câmbio: 1 {a.currency} = R$ {Number(a.rate).toFixed(4)} · custo de vida {a.living_month ? fmtBRL(a.living_month.total) : "—"}/mês</span>
          {a.exchange ? <div className="notice">Intercâmbio: <b>{a.exchange.name}</b> — {a.exchange.progress} de {a.exchange.months} meses (ao final: +{a.exchange.points} pontos {FIELD[a.exchange.field] ?? a.exchange.field} no currículo).
            <div style={{ marginTop: 6 }}><button className="btn danger small" disabled={busy} onClick={() => window.confirm("Interromper o intercâmbio? Você volta ao Brasil sem os pontos.") && void act(sim.lifeExchangeCancel, () => "Intercâmbio interrompido.")}>Interromper e voltar</button></div></div>
            : <div><button className="btn primary small" disabled={busy} onClick={() => window.confirm("Voltar ao Brasil? Os empregos presenciais de lá terminam e a passagem de volta entra no orçamento.") && void act(sim.lifeReturnHome, (r) => `Você voltou ao Brasil (passagem ${fmtBRL((r as { result: { flight_brl: string } }).result.flight_brl)}).`)}>🇧🇷 Voltar para o Brasil</button></div>}
        </> : <span className="muted small">Câmbio e custos dos outros países estão em Economia → Países e câmbio.</span>}
      </section>
      {!abroad && (
        <>
          <h2>🎒 Intercâmbio</h2>
          <p className="muted small">Programas baseados em oportunidades reais de cada país. Rendem pontos no currículo em uma área ou pontos gerais.</p>
          <div className="cols-2">{a.programs.map((p) => (
            <div key={p.key} className="card stack">
              <div className="row between"><b>{p.flag} {p.name}</b><span className="chip">{KIND[p.kind] ?? p.kind}</span></div>
              <span className="small">{p.country_name} · {p.months} meses · idioma: {p.language} · <b>+{p.points}</b> pontos ({FIELD[p.field] ?? p.field}){p.note ? ` · ${p.note}` : ""}</span>
              <Cost c={p.cost} />
              <div><button className="btn primary small" disabled={busy} onClick={() => window.confirm(`Ir para ${p.country_name}? Você larga os empregos presenciais do Brasil e a saída custa ${fmtBRL(p.cost.upfront.total)}.`) && void act(() => sim.lifeExchange(p.key), () => `Boa viagem! Você foi para ${p.country_name}.`)}>Fazer intercâmbio</button></div>
            </div>))}</div>
          <h2>🏠 Morar em outro país</h2>
          <p className="muted small">Mudar de vez: você paga a vida local todo mês. Empregos presenciais no Brasil terminam; empregos remotos continuam (o salário segue em reais). Procure vagas no país em Carreira.</p>
          <div className="cols-2">{a.countries.map((c) => (
            <div key={c.code} className="card stack">
              <b>{c.flag} {c.name}</b><span className="muted small">{c.currency} · idioma: {c.language}</span>
              <Cost c={c.cost} />
              <div><button className="btn small" disabled={busy} onClick={() => window.confirm(`Mudar para ${c.name}? Relacionamentos podem se afastar ou romper.`) && void act(() => sim.lifeMoveAbroad(c.code), (r) => { const x = (r as { result: { ended_jobs: string[]; reactions: string[] } }).result; return `Você se mudou para ${c.name}.${x.ended_jobs.length ? ` Largou: ${x.ended_jobs.join(", ")}.` : ""}${x.reactions.length ? ` ${x.reactions.join("; ")}.` : ""}`; })}>Mudar para {c.name}</button></div>
            </div>))}</div>
        </>
      )}
      {a.done.length > 0 && <><h2>Meus intercâmbios</h2><ul className="list-plain">{a.done.map((d) => <li key={d.id}><span>{d.name} · {d.months} meses</span><span className={`chip ${d.status === "DONE" ? "up" : "down"}`}>{d.status === "DONE" ? `+${d.points} pontos` : "interrompido"}</span></li>)}</ul></>}
    </div>
  );
}
