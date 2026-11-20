import { useCallback, useEffect, useState } from "react";
import { Meter } from "../components/Meter";
import { StatCard } from "../components/StatCard";
import { fmtBRL, fmtMonth } from "../lib/format";
import { sim, type Kid, type Life, type Rel } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
type Tab = "status" | "people" | "family" | "decisions";
const STAGE: Record<string, string> = { ACQUAINTANCE: "Conhecido(a)", FRIEND: "Amigo(a)", DATING: "Namoro", COHABITING: "União estável", MARRIED: "Casamento", ENDED: "Encerrado" };
const CHOICE_LABEL: Record<string, [string, Record<string, string>]> = {
  work_level: ["Jornada de trabalho", { REDUCED: "Reduzida (menos renda, mais tempo)", NORMAL: "Normal", INTENSE: "Intensa (mais renda, menos tempo)" }],
  food_level: ["Alimentação", { BASIC: "Econômica", NORMAL: "Normal", PREMIUM: "Qualidade premium" }],
  health_level: ["Saúde", { NONE: "Sem investimento", BASIC: "Básico", PLUS: "Investindo em saúde" }],
  leisure_level: ["Lazer", { LOW: "Pouco", NORMAL: "Normal", HIGH: "Muito" }],
  family_time: ["Tempo em família", { LOW: "Pouco", NORMAL: "Normal", HIGH: "Muito" }],
};
const LINE: Record<string, string> = { food: "Alimentação", health: "Saúde", education: "Educação", clothing: "Vestuário", leisure: "Lazer", housing: "Moradia", transport: "Transporte" };

export function LifePage() {
  const [life, setLife] = useState<Life | null>(null);
  const [tab, setTab] = useState<Tab>("status");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { sim.life().then(setLife).catch((e) => setError(errMsg(e))); }, []);
  const act = useCallback(async (fn: () => Promise<Life>, ok?: (l: Life) => string | null) => {
    setBusy(true); setError(null); setNote(null);
    try { const l = await fn(); setLife(l); setNote(ok ? ok(l) : null); } catch (e) { setError(errMsg(e)); sim.life().then(setLife).catch(() => undefined); } finally { setBusy(false); }   // recusas mudam a afinidade: recarrega
  }, []);

  if (!life) return error ? <div className="alert">{error}</div> : <div className="muted">Carregando vida pessoal…</div>;
  const a = life.attributes;
  const partner = life.relationships.find((r) => ["DATING", "COHABITING", "MARRIED"].includes(r.stage));
  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Vida pessoal</h1><p className="muted">{life.character.name}, {life.character.age_years} anos · {fmtMonth(life.month)}. Suas escolhas afetam saúde, tempo, relacionamentos e o orçamento.</p></div>
      </header>
      {error && <div className="alert">{error}</div>}
      {note && <div className="card small">{note}</div>}
      <div className="seg compact tabs">
        <button className={tab === "status" ? "on" : ""} onClick={() => setTab("status")}>Situação</button>
        <button className={tab === "people" ? "on" : ""} onClick={() => setTab("people")}>Relacionamentos ({life.relationships.filter((r) => r.stage !== "ENDED").length})</button>
        <button className={tab === "family" ? "on" : ""} onClick={() => setTab("family")}>Família e filhos</button>
        <button className={tab === "decisions" ? "on" : ""} onClick={() => setTab("decisions")}>Decisões ({life.pending_decisions.length})</button>
      </div>

      {tab === "status" && (
        <>
          <section className="card stack">
            <h2>Indicadores</h2>
            <div className="cols-2">
              <Meter label="Saúde" value={a.health} /><Meter label="Bem-estar" value={a.wellbeing} />
              <Meter label="Qualidade de vida" value={a.quality} /><Meter label="Satisfação pessoal" value={a.satisfaction} />
              <Meter label="Vida social" value={a.social} /><Meter label="Estabilidade financeira" value={a.financial_stability} />
            </div>
            <p className="muted small">Tempo livre neste mês: <b className="num">{a.free_hours_left}h</b> de {a.free_hours_total}h. Atividades e convivência consomem horas.</p>
          </section>
          <section className="card stack">
            <h2>Como você quer viver</h2>
            <div className="cols-2">
              {Object.entries(CHOICE_LABEL).map(([k, [label, opts]]) => (
                <label key={k} className="stack"><span className="muted small">{label}</span>
                  <select value={life.choices[k]} disabled={busy} onChange={(e) => void act(() => sim.lifeChoices({ [k]: e.target.value }))}>
                    {life.options[k].map((o) => <option key={o} value={o}>{opts[o] ?? o}</option>)}
                  </select></label>))}
            </div>
            <p className="muted small">Não há opção “sempre melhor”: trabalhar mais rende mais e cobra tempo e saúde; investir em saúde e lazer custa dinheiro.</p>
          </section>
          <section className="card stack">
            <h2>Atividades sociais</h2>
            <p className="muted small">Atividades gratuitas também funcionam para conhecer pessoas.</p>
            <div className="row">{life.activities.map((x) => (
              <button key={x.key} className="btn ghost small" disabled={busy} onClick={() => void act(() => sim.lifeActivity(x.key), (l) => l.result?.met ? `Você conheceu ${l.result.met}!` : "Boa atividade — ninguém novo desta vez.")}>
                {x.label} · {x.cost ? fmtBRL(String(x.cost)) : "grátis"} · {x.hours}h</button>))}</div>
          </section>
          <section className="card stack"><h2>Histórico</h2>
            <ul className="list-plain">{life.history.map((h, i) => <li key={i}><span>{h.text}</span><span className="muted small">{fmtMonth(h.month)}</span></li>)}</ul></section>
        </>
      )}

      {tab === "people" && (
        <section className="stack">
          {life.relationships.length === 0 && <div className="card muted">Você ainda não conheceu ninguém. Participe de atividades sociais na aba “Situação”.</div>}
          {life.relationships.map((r) => <PersonCard key={r.person_id} r={r} life={life} busy={busy} act={act} />)}
        </section>
      )}

      {tab === "family" && (
        <>
          <section className="stats-grid">
            <StatCard label="Parceiro(a)" value={partner ? partner.name : "—"} sub={partner ? STAGE[partner.stage] : "sem relacionamento sério"} />
            <StatCard label="Filhos" value={life.children.filter((c) => c.active).length} sub={life.pregnancy_due_month ? `nascimento previsto ${fmtMonth(life.pregnancy_due_month)}` : undefined} />
            <StatCard label="Despesas familiares (mês)" value={fmtBRL(life.family_expense_total)} />
            <StatCard label="Moradia" value={life.housing.kind === "EXISTING" ? "pelo orçamento" : fmtBRL(life.housing.monthly_cost)} sub={life.housing.pending ? `mudança em ${fmtMonth(life.housing.pending.effective_month)}` : life.housing.kind} />
          </section>
          <section className="card stack">
            <div className="row between"><h2>Filhos</h2>
              <button className="btn primary small" disabled={busy} onClick={() => void act(sim.lifePlanChild, () => "Gestação iniciada: o nascimento ocorre em 9 meses.")}>Planejar um filho</button></div>
            {life.children.length === 0 && <p className="muted small">Planejar filhos exige parceiro(a) em união estável ou casamento.</p>}
            {life.children.map((c) => <ChildCard key={c.id} c={c} busy={busy} act={act} />)}
          </section>
          <section className="card stack">
            <h2>Mudar de residência</h2>
            <MoveForm busy={busy} act={act} />
          </section>
          <section className="card stack">
            <h2>Despesas familiares do mês</h2>
            <p className="muted small">Cada linha mostra de onde vem o custo. As despesas pessoais que você já cadastrou no orçamento não são contadas de novo.</p>
            <div className="table-wrap"><table><thead><tr><th>Item</th><th>Origem</th><th>Categoria</th><th className="r">Valor</th></tr></thead>
              <tbody>{life.expenses.map((e) => <tr key={e.key}><td>{e.name}</td><td>{e.origin}</td><td>{e.category}</td>
                <td className={`r num ${e.kind === "INCOME" ? "tone-up" : ""}`}>{e.kind === "INCOME" ? "+" : ""}{fmtBRL(e.amount)}</td></tr>)}
                {life.expenses.length === 0 && <tr><td colSpan={4} className="muted">Nenhuma despesa familiar neste mês.</td></tr>}</tbody></table></div>
          </section>
        </>
      )}

      {tab === "decisions" && (
        <section className="card stack">
          <h2>Decisões e oportunidades</h2>
          {life.pending_decisions.length === 0 ? <p className="muted">Nada pendente agora.</p> :
            <ul className="list-plain">{life.pending_decisions.map((d) => <li key={d.key}><span>{d.text}</span></li>)}</ul>}
          <p className="muted small">Acontecimentos econômicos e profissionais que pedem escolha aparecem em “Economia”.</p>
        </section>
      )}
    </div>
  );
}

type Act = (fn: () => Promise<Life>, ok?: (l: Life) => string | null) => Promise<void>;

function PersonCard({ r, life, busy, act }: { r: Rel; life: Life; busy: boolean; act: Act }) {
  const ended = r.stage === "ENDED";
  const next: Record<string, [string, string] | undefined> = { ACQUAINTANCE: ["befriend", "Virar amigos"], FRIEND: ["date", "Convidar para namorar"], DATING: ["cohabit", "Morarem juntos"], COHABITING: ["marry", "Casar"] };
  const nx = next[r.stage];
  return (
    <div className="card stack" style={ended ? { opacity: 0.6 } : undefined}>
      <div className="row between"><h3 style={{ margin: 0 }}>{r.name}, {r.age}</h3><span className="chip">{STAGE[r.stage]}</span></div>
      <p className="muted small">{r.personality} · {r.occupation} · interesses: {r.interests.join(", ")}</p>
      <div className="cols-2"><Meter label="Afinidade" value={r.affinity} /><Meter label="Confiança" value={r.trust} /><Meter label="Compatibilidade" value={r.compatibility} /></div>
      {!ended && (
        <div className="row">
          {life.interactions.map((i) => <button key={i.key} className="btn ghost small" disabled={busy} onClick={() => void act(() => sim.lifeInteract(r.person_id, i.key))}>{i.label} · {i.cost ? fmtBRL(String(i.cost)) : "grátis"} · {i.hours}h</button>)}
          {nx && <button className="btn primary small" disabled={busy} onClick={() => void act(() => sim.lifeRelationship(r.person_id, nx[0]))}>{nx[1]}</button>}
          {r.stage === "DATING" && <button className="btn primary small" disabled={busy} onClick={() => void act(() => sim.lifeRelationship(r.person_id, "marry"))}>Casar</button>}
          <button className="btn danger small" disabled={busy} onClick={() => window.confirm(`Encerrar o relacionamento com ${r.name}?`) && void act(() => sim.lifeRelationship(r.person_id, "end"))}>Encerrar</button>
        </div>)}
      {["COHABITING", "MARRIED"].includes(r.stage) && (
        <div className="row"><span className="muted small">Finanças do casal:</span>
          <select value={r.finance_mode} disabled={busy} onChange={(e) => void act(() => sim.lifeFinances(r.person_id, e.target.value, r.contribution_pct))}>
            <option value="SEPARATE">Separadas</option><option value="SHARED">Compartilhadas ({Number(r.contribution_pct)}% das despesas comuns)</option></select>
          {r.finance_mode === "SHARED" && <input style={{ width: 90 }} type="number" min={0} max={100} defaultValue={Number(r.contribution_pct)} onBlur={(e) => void act(() => sim.lifeFinances(r.person_id, "SHARED", e.target.value))} />}
          <span className="muted small">renda dele(a): {fmtBRL(r.income)} · dívidas: {fmtBRL(r.debts)}</span></div>)}
    </div>
  );
}

function ChildCard({ c, busy, act }: { c: Kid; busy: boolean; act: Act }) {
  return (
    <div className="card stack">
      <div className="row between"><h3 style={{ margin: 0 }}>{c.name} · {c.age_years} ano(s)</h3>{!c.active && <span className="chip">independente</span>}</div>
      <div className="cols-2"><Meter label="Saúde" value={c.health} /><Meter label="Desenvolvimento" value={c.development} /></div>
      <p className="muted small">Necessidades: {c.needs.map((n) => LINE[n] ?? n).join(", ") || "—"} · custo de referência {fmtBRL(String(c.monthly_reference_cost))}/mês</p>
      {c.active && <div className="row">
        <select value={c.school_kind} disabled={busy} onChange={(e) => void act(() => sim.lifeChild(c.id, { school_kind: e.target.value as "PUBLIC" | "PRIVATE" }))}><option value="PUBLIC">Escola pública</option><option value="PRIVATE">Escola particular</option></select>
        {c.age_years <= 2 && <label className="row small"><input type="checkbox" checked={c.daycare} onChange={(e) => void act(() => sim.lifeChild(c.id, { daycare: e.target.checked }))} /> Creche</label>}
        {c.age_years >= 4 && <label className="row small"><input type="checkbox" checked={c.activities} onChange={(e) => void act(() => sim.lifeChild(c.id, { activities: e.target.checked }))} /> Atividades extracurriculares</label>}
      </div>}
    </div>
  );
}

function MoveForm({ busy, act }: { busy: boolean; act: Act }) {
  const [kind, setKind] = useState("RENT");
  const [cost, setCost] = useState("2000");
  return (
    <div className="row">
      <select value={kind} onChange={(e) => setKind(e.target.value)}>
        <option value="RENT">Aluguel próprio</option><option value="SHARED">Residência compartilhada</option><option value="FAMILY_HOME">Casa da família</option><option value="EXISTING">Voltar ao orçamento atual (sem custo extra)</option></select>
      <input type="number" min={0} value={cost} onChange={(e) => setCost(e.target.value)} aria-label="Custo mensal" />
      <button className="btn primary small" disabled={busy} onClick={() => void act(() => sim.lifeMove(kind, cost), () => "Mudança agendada para o próximo mês: os custos antigos terminam e os novos começam lá.")}>Agendar mudança</button>
    </div>
  );
}
