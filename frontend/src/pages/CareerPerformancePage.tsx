import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { StatCard } from "../components/StatCard";
import { fmtBRL, fmtMonth, trend } from "../lib/format";
import { sim, type CareerPerf } from "../services/sim";

const COLORS = ["#ffd23f", "#3ee59a", "#ff6482", "#4cc9f0"];
const ICON = { good: "✅", warn: "⚠️", info: "💡" } as const;
const n = (v: number | null | undefined) => (v == null ? "—" : fmtBRL(String(v)));

/** Desempenho da CARREIRA (partida de vida completa): a vida financeira inteira, não só a carteira de investimentos. */
export function CareerPerformancePage() {
  const [d, setD] = useState<CareerPerf | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { sim.careerPerformance().then(setD).catch((e) => setErr(e instanceof Error ? e.message : "Erro")); }, []);
  const data = useMemo(() => (d?.series ?? []).map((s) => ({ ...s, m: fmtMonth(s.month).replace(" de ", "/") })), [d]);
  if (err) return <div className="alert">{err}</div>;
  if (!d) return <div className="muted">Carregando desempenho…</div>;
  const s = d.summary;
  const Chart = ({ title, hint, keys }: { title: string; hint: string; keys: [string, string][] }) => (
    <section className="card stack"><h2>{title}</h2><p className="muted small" style={{ margin: 0 }}>{hint}</p>
      <div style={{ height: 210 }}><ResponsiveContainer><LineChart data={data}><CartesianGrid stroke="#4d40a855" strokeDasharray="3 3" />
        <XAxis dataKey="m" tick={{ fill: "#c3bcf0", fontSize: 11 }} minTickGap={24} /><YAxis tick={{ fill: "#c3bcf0", fontSize: 11 }} domain={["auto", "auto"]} />
        <Tooltip contentStyle={{ background: "#281e63", border: "2px solid #4d40a8", borderRadius: 12 }} /><Legend />
        {keys.map(([k, name], i) => <Line key={k} type="monotone" dataKey={k} name={name} stroke={COLORS[i % COLORS.length]} dot={false} strokeWidth={2.5} connectNulls />)}
      </LineChart></ResponsiveContainer></div></section>
  );
  return (
    <div className="page">
      <header className="page-head"><div><h1>🏅 Desempenho da carreira</h1><p className="muted">Como a sua vida financeira está indo, mês a mês. {d.ended && "(partida encerrada)"}</p></div>
        <Link className="btn ghost small" to="/desempenho/investimentos">📈 Desempenho dos investimentos</Link></header>
      <section className="stats-grid">
        <StatCard label="Patrimônio" value={n(s.net_worth)} sub={s.net_worth_change != null ? `${s.net_worth_change >= 0 ? "+" : ""}${n(s.net_worth_change)} desde o início` : undefined} tone={s.net_worth_change != null ? trend(String(s.net_worth_change)) : "neutral"} emphasis />
        <StatCard label="Poupança (média 12 meses)" value={s.avg_savings_rate_12m != null ? `${s.avg_savings_rate_12m}%` : "—"} sub="parte da renda que sobra" tone={s.avg_savings_rate_12m != null && s.avg_savings_rate_12m >= 20 ? "up" : "neutral"} />
        <StatCard label="Reserva de emergência" value={`${s.emergency_months.toFixed(1)} meses`} sub="meta: 3 a 6 meses" tone={s.emergency_months >= 3 ? "up" : "down"} />
        <StatCard label="Dívidas" value={n(s.debts)} tone={s.debts > 0 ? "down" : "neutral"} />
        <StatCard label="Meses no azul" value={`${s.positive_months} de ${s.months_played}`} />
        <StatCard label="Saúde · bem-estar · satisfação" value={`${s.health ?? "—"} · ${s.wellbeing ?? "—"} · ${s.satisfaction ?? "—"}`} sub={s.age != null ? `${s.age} anos` : undefined} />
      </section>
      {d.insights.length > 0 && (
        <section className="card insights"><h2>O que seus números dizem</h2>
          <ul>{d.insights.map((i, k) => <li key={k} className={`ins ${i.tone}`}><span className="ins-icon" aria-hidden>{ICON[i.tone]}</span><span>{i.text}{i.lesson_id && <> <Link to={`/aulas/${i.lesson_id}`}>Aprender mais →</Link></>}</span></li>)}</ul></section>)}
      {d.recommended_lessons.length > 0 && (
        <section className="card tips"><h2>📚 Aulas para você melhorar</h2>
          <div className="tip-grid">{d.recommended_lessons.map((l) => <Link key={l.lesson_id} to={`/aulas/${l.lesson_id}`} className="tip-card"><b>{l.title}</b><span className="small">{l.reason}</span><span className="chip">▶ assistir</span></Link>)}</div></section>)}
      <section className="card stack"><h2>💼 Carreira</h2>
        <p>{d.career.label ? <>Você atua em <b>{d.career.label}</b>.</> : "Sem área definida."} {d.career.degrees.length > 0 && `Formações: ${d.career.degrees.join(", ")}.`} {d.career.studying && "Cursando faculdade."}</p>
        {d.career.cost_of_living_change_pct != null && <p className="muted small">Desde o início, o custo de vida mudou <b>{d.career.cost_of_living_change_pct}%</b> e os salários do mercado, <b>{d.career.wage_index_change_pct}%</b>. Se os preços sobem mais que o seu salário, você perde poder de compra.</p>}</section>
      {data.length < 2 ? <div className="card muted">Feche alguns meses para ver os gráficos ganharem forma. 📈</div> : (
        <div className="cols-2">
          <Chart title="📦 Patrimônio" hint="Nominal (em reais da época) e real (corrigido pela inflação)." keys={[["net_worth", "Nominal"], ["net_worth_real", "Real"]]} />
          <Chart title="💰 Receitas e despesas" hint="O que entrou e o que saiu a cada mês." keys={[["income", "Receitas"], ["expense", "Despesas"]]} />
          <Chart title="🐷 Taxa de poupança (%)" hint="Quanto da renda sobrou no mês." keys={[["savings_rate", "Poupança %"]]} />
          <Chart title="❤️ Saúde e bem-estar" hint="O dinheiro não é tudo." keys={[["health", "Saúde"], ["wellbeing", "Bem-estar"], ["satisfaction", "Satisfação"]]} />
        </div>)}
    </div>
  );
}
