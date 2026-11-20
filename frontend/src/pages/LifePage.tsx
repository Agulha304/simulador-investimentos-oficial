import { useCallback, useEffect, useState } from "react";
import { Meter } from "../components/Meter";
import { Toast } from "../components/Toast";
import { StatCard } from "../components/StatCard";
import { fmtBRL, fmtMonth } from "../lib/format";
import { sim, type Calendar, type HousingOffer, type Kid, type Life, type Rel } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
type Tab = "status" | "people" | "family" | "calendar";
const FAMILY_LABEL: Record<string, string> = { MOTHER: "👩 Mãe", FATHER: "👨 Pai", BROTHER: "👦 Irmão", SISTER: "👧 Irmã" };
const STAGE: Record<string, string> = { FAMILY: "Família", ACQUAINTANCE: "Conhecido(a)", FRIEND: "Amigo(a)", DATING: "Namoro", COHABITING: "União estável", MARRIED: "Casamento", ENDED: "Encerrado" };
const CHOICE_LABEL: Record<string, [string, Record<string, string>]> = {
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
    try { const l = await fn(); setLife(l); setNote(ok ? ok(l) : null); } catch (e) { const m = errMsg(e); if (/tempo livre insuficiente/i.test(m)) setNote("⏳ " + m); else setError(m); sim.life().then(setLife).catch(() => undefined); } finally { setBusy(false); }   // recusas mudam a afinidade: recarrega
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
      {note && <Toast text={note} onClose={() => setNote(null)} />}
      <div className="seg compact tabs">
        <button className={tab === "status" ? "on" : ""} onClick={() => setTab("status")}>Situação</button>
        <button className={tab === "people" ? "on" : ""} onClick={() => setTab("people")}>Pessoas ({life.relationships.filter((r) => r.stage !== "ENDED").length})</button>
        <button className={tab === "calendar" ? "on" : ""} onClick={() => setTab("calendar")}>Calendário</button>
        <button className={tab === "family" ? "on" : ""} onClick={() => setTab("family")}>Família e filhos</button>
      </div>

      {tab === "calendar" && <CalendarTab version={life.attributes.free_hours_left} />}
      {tab === "status" && (
        <>
          {(life.conditions ?? []).length > 0 && (
            <section className="card stack"><h2>🩺 Saúde física e mental</h2>
              {life.conditions!.map((c) => (
                <div key={c.key} className="card stack"><div className="row between"><b>{c.kind === "MENTAL" ? "🧠" : "🫀"} {c.label}</b><span className="chip down">{c.chronic ? "crônica" : `até ${fmtMonth(c.until!)}`}</span></div>
                  <span className="muted small">{c.text}</span>
                  <label className="check"><input type="checkbox" checked={c.treated} disabled={busy} onChange={(e) => void act(() => sim.lifeTreatment(c.key, e.target.checked), () => e.target.checked ? "Tratamento iniciado: custa todo mês, mas ameniza e acelera a recuperação." : "Tratamento interrompido.")} />Fazer tratamento ({fmtBRL(String(c.treatment_cost))}/mês)</label></div>))}
              <p className="muted small" style={{ margin: 0 }}>Sobrecarga constante (pouco tempo livre, jornada intensa, saúde ruim) causa doenças e pode levar ao burnout, que afasta você do trabalho e reduz a renda.</p></section>)}
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
              <button key={x.key} className="btn ghost small" disabled={busy} onClick={() => void act(() => sim.lifeActivity(x.key), (l) => l.result?.story ?? (l.result?.met ? `Você conheceu ${l.result.met}!` : "Boa atividade — ninguém novo desta vez."))}>
                {x.label} · {x.cost ? fmtBRL(String(x.cost)) : "grátis"} · {x.hours}h</button>))}</div>
          </section>
          <section className="card stack"><h2>Histórico</h2>
            <ul className="list-plain">{life.history.map((h, i) => <li key={i}><span>{h.text}</span><span className="muted small">{fmtMonth(h.month)}</span></li>)}</ul></section>
        </>
      )}

      {tab === "people" && (
        <section className="stack">
          {life.relationships.filter((r) => r.role).length > 0 && <><h2 style={{ margin: "0 0 4px" }}>👨‍👩‍👧 Família de origem</h2>
            {life.relationships.filter((r) => r.role).map((r) => <PersonCard key={r.person_id} r={r} life={life} busy={busy} act={act} />)}</>}
          <h2 style={{ margin: "8px 0 4px" }}>🤝 Amigos e conhecidos</h2>
          {life.relationships.filter((r) => !r.role).length === 0 && <div className="card muted">Você ainda não conheceu ninguém além da sua família. Participe de atividades sociais na aba “Situação”, faça faculdade ou aceite convites nas decisões do mês.</div>}
          {life.relationships.filter((r) => !r.role).map((r) => <PersonCard key={r.person_id} r={r} life={life} busy={busy} act={act} />)}
        </section>
      )}

      {tab === "family" && (
        <>
          <section className="stats-grid">
            <StatCard label="Parceiro(a)" value={partner ? partner.name : "—"} sub={partner ? STAGE[partner.stage] : "sem relacionamento sério"} />
            <StatCard label="Filhos" value={life.children.filter((c) => c.active).length} sub={life.pregnancy_due_month ? `nascimento previsto ${fmtMonth(life.pregnancy_due_month)}` : undefined} />
            <StatCard label="Despesas familiares (mês)" value={fmtBRL(life.family_expense_total)} />
            <StatCard label="Moradia" value={life.housing.kind === "EXISTING" ? "pelo orçamento" : fmtBRL(life.housing.monthly_cost)} sub={life.housing.pending ? `mudança em ${fmtMonth(life.housing.pending.effective_month)}` : (life.housing.description || life.housing.kind)} tone={life.housing.quality < 0 ? "down" : life.housing.quality > 0 ? "up" : "neutral"} />
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

    </div>
  );
}

type Act = (fn: () => Promise<Life>, ok?: (l: Life) => string | null) => Promise<void>;

function PersonCard({ r, life, busy, act }: { r: Rel; life: Life; busy: boolean; act: Act }) {
  const ended = r.stage === "ENDED" || !r.alive;
  const next: Record<string, [string, string] | undefined> = { ACQUAINTANCE: ["befriend", "Virar amigos"], FRIEND: ["date", "Convidar para namorar"], DATING: ["cohabit", "Morarem juntos"], COHABITING: ["marry", "Casar"] };
  const nx = next[r.stage];
  return (
    <div className="card stack" style={ended ? { opacity: 0.6 } : undefined}>
      <div className="row between"><h3 style={{ margin: 0 }}>{r.gender === "F" ? "👩" : "👨"} {r.name}, {r.age}{!r.alive && " ✝"}</h3><span className="chip">{r.role ? FAMILY_LABEL[r.role] : STAGE[r.stage]}{!r.alive && " (faleceu)"}</span></div>
      <p className="muted small">{r.personality} · {r.occupation} · interesses: {r.interests.join(", ")}</p>
      <p className="small">💼 Situação financeira: <b>{r.finance_label}</b> <span className="muted">· renda {fmtBRL(r.income)} · patrimônio {fmtBRL(r.assets)} · dívidas {fmtBRL(r.debts)}</span></p>
      <div className="cols-2"><Meter label="Afinidade" value={r.affinity} /><Meter label="Confiança" value={r.trust} /><Meter label={`Compatibilidade${r.compat_bonus ? ` (+${r.compat_bonus} por convivência)` : ""}`} value={r.compatibility} /></div>
      {!ended && (
        <div className="row">
          {life.interactions.map((i) => <button key={i.key} className="btn ghost small" disabled={busy} onClick={() => void act(() => sim.lifeInteract(r.person_id, i.key), (l) => l.result?.reaction_text ? `${l.result.delta! > 0 ? "💖" : "💔"} ${l.result.reaction_text} (${l.result.delta! > 0 ? "+" : ""}${l.result.delta} de afinidade)` : (l.result?.story ?? null))}>{i.label} · {i.cost ? fmtBRL(String(i.cost)) : "grátis"} · {i.hours}h</button>)}
          {nx && !r.role && <button className="btn primary small" disabled={busy} onClick={() => void act(() => sim.lifeRelationship(r.person_id, nx[0]))}>{nx[1]}</button>}
          {r.stage === "DATING" && !r.role && <button className="btn primary small" disabled={busy} onClick={() => void act(() => sim.lifeRelationship(r.person_id, "marry"))}>Casar</button>}
          {!r.role && <button className="btn danger small" disabled={busy} onClick={() => window.confirm(`Encerrar o relacionamento com ${r.name}?`) && void act(() => sim.lifeRelationship(r.person_id, "end"))}>Encerrar</button>}
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
  const [cost, setCost] = useState("1500");
  const [offer, setOffer] = useState<HousingOffer | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const rent = kind === "RENT" || kind === "SHARED";
  const go = async () => {
    setErr(null);
    if (!rent) { void act(() => sim.lifeMove(kind, "0"), () => "Mudança agendada para o próximo mês."); return; }
    try { setOffer(await sim.searchHousing(cost)); } catch (e) { setErr(errMsg(e)); }
  };
  return (
    <div className="stack">
      <div className="row">
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="RENT">Alugar um imóvel só para mim</option><option value="SHARED">Alugar uma residência compartilhada</option><option value="FAMILY_HOME">Morar na casa de familiares</option><option value="EXISTING">Voltar ao orçamento atual (sem custo extra)</option></select>
        {rent && <label className="row small">Quanto quero pagar (R$/mês)<input type="number" min={0} value={cost} onChange={(e) => setCost(e.target.value)} style={{ width: 120 }} /></label>}
        <button className="btn primary small" disabled={busy} onClick={() => void go()}>{rent ? "🔎 Procurar imóvel" : "Agendar mudança"}</button>
      </div>
      {rent && <p className="muted small" style={{ margin: 0 }}>Você diz quanto quer pagar; <b>o jogo decide se existe uma oferta</b> nesse valor e em que condições. Quanto mais barato, pior costuma ser o lugar — e onde você mora afeta a saúde, o bem-estar e a satisfação.</p>}
      {err && <div className="alert">{err}</div>}
      {offer && (
        <div className="modal-back" role="dialog" aria-modal="true" aria-label="Resultado da busca de imóvel">
          <div className="card modal">
            <div className="row between"><h2>{offer.available ? "🏠 Encontramos uma oferta!" : "😕 Sem oferta por esse valor"}</h2><button className="link-btn" onClick={() => setOffer(null)}>fechar ✕</button></div>
            <p>{offer.message}</p>
            {offer.available && (<>
              <div className="card"><b>{offer.title}</b><p style={{ margin: "6px 0" }}>{offer.description}</p>
                <p className="small" style={{ margin: 0 }}>Aluguel: <b>{fmtBRL(offer.rent ?? "0")}</b> por mês · Condição: {["muito precária", "ruim", "simples", "boa", "muito boa", "ótima", "excelente"][(offer.quality ?? 0) + 3]}</p></div>
              <div className={`notice`}>{(offer.quality ?? 0) < 0 ? "⚠️" : (offer.quality ?? 0) > 0 ? "✨" : "🙂"} {offer.effect}</div>
              <div className="row"><button className="btn primary" disabled={busy} onClick={() => { setOffer(null); void act(() => sim.lifeMove(kind, cost), () => "Mudança agendada: o aluguel começa no próximo mês."); }}>Alugar este imóvel</button>
                <button className="btn ghost" onClick={() => setOffer(null)}>Continuar procurando</button></div></>)}
            {!offer.available && <button className="btn primary" onClick={() => setOffer(null)}>Tentar outro valor</button>}
          </div>
        </div>)}
    </div>
  );
}



function CalendarTab({ version }: { version: number }) {
  const [c, setC] = useState<Calendar | null>(null);
  useEffect(() => { sim.lifeCalendar().then(setC).catch(() => setC(null)); }, [version]);
  if (!c) return <div className="muted">Carregando calendário…</div>;
  const COL = ["#7c6cff", "#4cc9f0", "#3ee59a", "#ffd23f", "#ff9f43", "#c13cff", "#ff6482", "#8bd3dd", "#f4a261"];
  return (
    <section className="card stack">
      <h2>🗓️ Seu calendário do mês</h2>
      <p className="muted small" style={{ margin: 0 }}>Um mês tem {c.total} horas. Veja onde o seu tempo está indo: trabalho, estudos, atividades e o que sobra de tempo livre.</p>
      {c.overloaded && <div className="alert">⚠️ Você está sobrecarregado(a): quase não sobra tempo livre. Isso aumenta o estresse e pode causar doenças e burnout.</div>}
      <div style={{ display: "flex", height: 28, borderRadius: 14, overflow: "hidden", border: "2px solid #4d40a8" }}>
        {c.rows.map((r, i) => <div key={r.key} title={`${r.label}: ${r.hours}h`} style={{ width: `${(r.hours / c.total) * 100}%`, background: r.key === "free" ? "#3ee59a" : COL[i % COL.length] }} />)}</div>
      <ul className="list-plain">{c.rows.map((r, i) => (
        <li key={r.key}><span><i style={{ display: "inline-block", width: 10, height: 10, borderRadius: 99, marginRight: 6, background: r.key === "free" ? "#3ee59a" : COL[i % COL.length] }} />{r.label}</span><b className="num">{r.hours}h <span className="muted small">({Math.round((r.hours / c.total) * 100)}%)</span></b></li>))}</ul>
      <Meter label={`Estresse acumulado: ${c.stress}/100`} value={c.stress} />
    </section>
  );
}
