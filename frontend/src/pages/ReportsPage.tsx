import { useEffect, useState } from "react";
import { Meter } from "../components/Meter";
import { StatCard } from "../components/StatCard";
import { fmtBRL, fmtMonth, trend } from "../lib/format";
import { sim, type Achievement, type AnnualReport, type Goal, type MonthReport } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
const n = (v: number) => fmtBRL(String(v));
type Tab = "month" | "year" | "goals" | "achievements";
const ATTR: Record<string, string> = { health: "Saúde", wellbeing: "Bem-estar", quality: "Qualidade de vida", satisfaction: "Satisfação", social: "Vida social" };

export function ReportsPage() {
  const [tab, setTab] = useState<Tab>("month");
  const [list, setList] = useState<{ month: string }[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { sim.reports().then(setList).catch((e) => setError(errMsg(e))); }, []);
  const years = [...new Set((list ?? []).map((r) => Number(r.month.slice(0, 4))))];
  return (
    <div className="page">
      <header className="page-head"><div><h1>Resumos e progresso</h1><p className="muted">Relatórios feitos com os dados reais de cada mês fechado, objetivos e conquistas.</p></div></header>
      {error && <div className="alert">{error}</div>}
      <div className="seg compact tabs">
        <button className={tab === "month" ? "on" : ""} onClick={() => setTab("month")}>Resumo mensal</button>
        <button className={tab === "year" ? "on" : ""} onClick={() => setTab("year")}>Relatório anual</button>
        <button className={tab === "goals" ? "on" : ""} onClick={() => setTab("goals")}>Objetivos</button>
        <button className={tab === "achievements" ? "on" : ""} onClick={() => setTab("achievements")}>Conquistas</button>
      </div>
      {tab === "month" && <Monthly months={(list ?? []).map((r) => r.month)} />}
      {tab === "year" && <Annual years={years} />}
      {tab === "goals" && <Goals />}
      {tab === "achievements" && <Achievements />}
    </div>
  );
}

function Monthly({ months }: { months: string[] }) {
  const [sel, setSel] = useState<string>("");
  const [r, setR] = useState<MonthReport | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (months.length && !sel) setSel(months[months.length - 1].slice(0, 7)); }, [months, sel]);
  useEffect(() => { if (sel) sim.report(sel).then((x) => { setR(x); setErr(null); }).catch((e) => setErr(errMsg(e))); }, [sel]);
  if (months.length === 0) return <div className="card muted">Nenhum mês fechado ainda. Feche o mês no Orçamento para ver o resumo.</div>;
  return (
    <>
      <select value={sel} onChange={(e) => setSel(e.target.value)} style={{ maxWidth: 240 }}>{months.map((m) => <option key={m} value={m.slice(0, 7)}>{fmtMonth(m)}</option>)}</select>
      {err && <div className="alert">{err}</div>}
      {r && (
        <>
          <section className="stats-grid">
            <StatCard label="Receitas" value={n(r.income)} tone="up" />
            <StatCard label="Despesas" value={n(r.expense)} sub={`família ${n(r.family_expense)}`} />
            <StatCard label="Resultado" value={n(r.result)} tone={trend(String(r.result))} emphasis />
            <StatCard label="Investido no mês" value={n(r.invested)} />
            <StatCard label="Patrimônio" value={n(r.net_worth)} sub={r.net_worth_change != null ? `${r.net_worth_change >= 0 ? "+" : ""}${n(r.net_worth_change)} no mês` : undefined} tone={r.net_worth_change != null ? trend(String(r.net_worth_change)) : "neutral"} />
            <StatCard label="Dívidas" value={n(r.debts)} />
          </section>
          {r.real && (
            <section className="card stack"><h2>🛒 Valores nominais e reais</h2>
              <p className="muted small">Nominal = o valor em reais da época. Real = o mesmo valor corrigido pelo custo de vida (o que ele realmente compra).</p>
              <ul className="list-plain">
                <li><span>Renda (nominal → real)</span><b className="num">{n(r.income)} → {n(r.real.income_real)}</b></li>
                <li><span>Despesas (nominal → real)</span><b className="num">{n(r.expense)} → {n(r.real.expense_real)}</b></li>
                <li><span>Poder de compra do real desde o início</span><b className={`num ${r.real.purchasing_power < 1 ? "tone-down" : "tone-up"}`}>{(r.real.purchasing_power * 100).toFixed(1)}%</b></li>
                <li><span>Custo de vida acumulado</span><b className="num">{((r.real.cpi - 1) * 100).toFixed(1)}%</b></li></ul></section>)}
          <div className="cols-2">
            <section className="card stack"><h2>Empresas</h2>
              {r.companies.length === 0 ? <p className="muted small">Sem empresas neste mês.</p> : <ul className="list-plain">{r.companies.map((c) => <li key={c.company_id}><span>{c.name}<br /><span className="muted small">receita {n(c.revenue)}</span></span><b className={`num ${c.net_result >= 0 ? "tone-up" : "tone-down"}`}>{n(c.net_result)}</b></li>)}</ul>}</section>
            <section className="card stack"><h2>Família</h2>
              {r.family_changes.length === 0 ? <p className="muted small">Sem mudanças.</p> : <ul className="list-plain">{r.family_changes.map((c, i) => <li key={i}><span>{c.text}</span></li>)}</ul>}</section>
            <section className="card stack"><h2>Eventos econômicos</h2>
              {r.economy && <p className="muted small">Inflação {r.economy.inflation.toFixed(2)}% · juros {r.economy.interest.toFixed(2)}% · desemprego {r.economy.unemployment.toFixed(1)}%</p>}
              {r.events.length === 0 ? <p className="muted small">Nenhum evento novo.</p> : <ul className="list-plain">{r.events.map((e, i) => <li key={i}><span>{e.name}</span><span className="chip">{e.status === "PENDING" ? "aguarda decisão" : "ativo"}</span></li>)}</ul>}</section>
            <section className="card stack"><h2>Conquistas e objetivos</h2>
              {r.achievements.length + r.goals_done.length === 0 ? <p className="muted small">Nada novo neste mês.</p> : <ul className="list-plain">
                {r.achievements.map((a) => <li key={a.key}><span>🏆 {a.name}</span></li>)}{r.goals_done.map((g) => <li key={g.key}><span>✓ Objetivo concluído: {g.title}</span></li>)}</ul>}</section>
          </div>
          <section className="card stack"><h2>Despesas por categoria</h2>
            <ul className="list-plain">{Object.entries(r.expense_by_category).map(([k, v]) => <li key={k}><span>{k}</span><b className="num">{n(v)}</b></li>)}</ul></section>
        </>
      )}
    </>
  );
}

function Annual({ years }: { years: number[] }) {
  const [year, setYear] = useState<number | null>(null);
  const [a, setA] = useState<AnnualReport | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (years.length && year == null) setYear(years[years.length - 1]); }, [years, year]);
  useEffect(() => { if (year != null) sim.annual(year).then((x) => { setA(x); setErr(null); }).catch((e) => setErr(errMsg(e))); }, [year]);
  if (years.length === 0) return <div className="card muted">O relatório anual aparece depois do primeiro mês fechado.</div>;
  const max = Math.max(1, ...(a?.monthly ?? []).map((m) => Math.abs(m.result)));
  return (
    <>
      <select value={year ?? ""} onChange={(e) => setYear(Number(e.target.value))} style={{ maxWidth: 160 }}>{years.map((y) => <option key={y} value={y}>{y}</option>)}</select>
      {err && <div className="alert">{err}</div>}
      {a && (
        <>
          {!a.complete && <div className="card small muted">Ano parcial: {a.months} de 12 meses simulados.</div>}
          <section className="stats-grid">
            <StatCard label="Patrimônio inicial" value={n(a.net_worth_start)} />
            <StatCard label="Patrimônio final" value={n(a.net_worth_end)} sub={`${a.net_worth_change >= 0 ? "+" : ""}${n(a.net_worth_change)}`} tone={trend(String(a.net_worth_change))} emphasis />
            <StatCard label="Receitas acumuladas" value={n(a.income)} tone="up" />
            <StatCard label="Despesas acumuladas" value={n(a.expense)} />
            <StatCard label="Investimentos" value={n(a.invested)} />
            <StatCard label="Lucros empresariais" value={n(a.company_profit)} tone={trend(String(a.company_profit))} />
            <StatCard label="Dívidas (início → fim)" value={`${n(a.debts_start)} → ${n(a.debts_end)}`} />
          </section>
          {a.real && (
            <section className="card stack"><h2>🛒 Poder de compra no ano</h2>
              <ul className="list-plain">
                <li><span>Custo de vida no ano</span><b className="num">{a.real.cost_of_living_change_pct.toFixed(1)}%</b></li>
                <li><span>Salários do mercado no ano</span><b className="num">{a.real.wage_index_change_pct.toFixed(1)}%</b></li>
                <li><span>Renda do ano: nominal → real</span><b className="num">{n(a.income)} → {n(a.real.income_real)}</b></li>
                <li><span>Patrimônio final em valores reais</span><b className="num">{n(a.real.net_worth_real_end)}</b></li></ul>
              <p className="muted small">Se o custo de vida subiu mais que a sua renda, você perdeu poder de compra mesmo ganhando o mesmo valor.</p></section>)}
          <section className="card stack"><h2>Resultado mês a mês</h2>
            <div className="bars">{a.monthly.map((m) => <div key={m.month} title={`${fmtMonth(m.month)}: ${n(m.result)}`} className={m.result < 0 ? "neg" : ""} style={{ height: `${(Math.abs(m.result) / max) * 100}%` }} />)}</div></section>
          <div className="cols-2">
            <section className="card stack"><h2>Mudanças pessoais</h2>
              {a.personal_change ? Object.entries(a.personal_change).map(([k, v]) => <p key={k} className="small">{ATTR[k] ?? k}: <b className={`num ${v >= 0 ? "tone-up" : "tone-down"}`}>{v >= 0 ? "+" : ""}{v}</b></p>) : <p className="muted small">Sem dados de vida pessoal.</p>}
              {a.family_changes.map((c, i) => <p key={i} className="small">{fmtMonth(c.month)} — {c.text}</p>)}</section>
            <section className="card stack"><h2>Principais acontecimentos</h2>
              {a.events.length === 0 ? <p className="muted small">Sem eventos.</p> : <ul className="list-plain">{a.events.slice(0, 12).map((e, i) => <li key={i}><span>{e.name}</span><span className="muted small">{fmtMonth(e.month)}</span></li>)}</ul>}</section>
          </div>
        </>
      )}
    </>
  );
}

function Goals() {
  const [goals, setGoals] = useState<Goal[] | null>(null);
  const [tpls, setTpls] = useState<{ key: string; title: string; default_target: number }[]>([]);
  const [tpl, setTpl] = useState("net_worth");
  const [target, setTarget] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const load = () => sim.goals().then(setGoals).catch((e) => setErr(errMsg(e)));
  useEffect(() => { void load(); sim.game().then((g) => setTpls(g.goal_templates)).catch(() => undefined); }, []);
  const add = async () => { setErr(null); try { await sim.addGoal(tpl, target || undefined); setTarget(""); await load(); } catch (e) { setErr(errMsg(e)); } };
  return (
    <>
      {err && <div className="alert">{err}</div>}
      <section className="card stack"><h2>Novo objetivo</h2>
        <div className="row"><select value={tpl} onChange={(e) => setTpl(e.target.value)}>{tpls.map((t) => <option key={t.key} value={t.key}>{t.title}</option>)}</select>
          <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder={`alvo (padrão ${tpls.find((t) => t.key === tpl)?.default_target ?? ""})`} inputMode="decimal" />
          <button className="btn primary small" onClick={() => void add()}>Criar</button></div>
        <p className="muted small">Objetivos só são concluídos depois de mantidos por alguns meses seguidos: não dá para completá-los com uma ação isolada.</p></section>
      {(goals ?? []).length === 0 && <div className="card muted">Nenhum objetivo ainda.</div>}
      <div className="cols-2">{(goals ?? []).map((g) => (
        <section key={g.id} className="card stack"><div className="row between"><b>{g.title}</b><span className={`chip ${g.status === "DONE" ? "up" : ""}`}>{g.status === "DONE" ? "concluído" : g.origin === "SCENARIO" ? "cenário" : "seu"}</span></div>
          <p className="muted small">{g.description}</p>
          <Meter label={`${g.metric_label}: ${Number(g.current).toLocaleString("pt-BR")} / ${Number(g.target).toLocaleString("pt-BR")}`} value={g.progress * 100} />
          <span className="muted small">{g.streak} de {g.sustain_months} mês(es) seguidos</span></section>))}</div>
    </>
  );
}

function Achievements() {
  const [list, setList] = useState<Achievement[] | null>(null);
  useEffect(() => { sim.achievements().then(setList).catch(() => setList([])); }, []);
  return (
    <div className="badges">{(list ?? []).map((a) => (
      <div key={a.key} className={`badge${a.unlocked ? " on" : ""}`}><div className="badge-top"><b>{a.unlocked ? "🏆" : "🔒"} {a.name}</b></div>
        <p className="muted small">{a.description}</p>{a.unlocked_month && <span className="muted small">{fmtMonth(a.unlocked_month)}</span>}</div>))}</div>
  );
}
