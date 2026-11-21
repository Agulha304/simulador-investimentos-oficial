import { Link } from "react-router-dom";
import { Meter } from "../components/Meter";
import { StatCard } from "../components/StatCard";
import { fmtBRL, fmtMonth, trend } from "../lib/format";
import { useApi } from "../services/dataCache";
import { type Overview } from "../services/sim";

const STAGE: Record<string, string> = { DATING: "Namorando", COHABITING: "União estável", MARRIED: "Casado(a)" };

export function OverviewPage() {
  const { data: o, error: err } = useApi<Overview>("/progress/overview");
  if (err && !o) return <div className="alert">Não foi possível carregar a visão geral: {err}</div>;
  if (!o) return <div className="muted">Carregando…</div>;
  const flow = Number(o.monthly_income) - Number(o.monthly_expense);
  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Vida financeira</h1><p className="muted">{fmtMonth(o.month)}{o.age != null ? ` · 🎂 ${o.age} anos` : ""} · {o.mode === "CAREER" ? "Modo carreira" : "Modo livre"}{!o.dynamic_economy && " · economia estável"}</p></div>
        <Link className="btn ghost small" to="/resumos">Resumos do mês e do ano</Link>
      </header>
      <section className="stats-grid">
        <StatCard label="Dinheiro disponível" value={fmtBRL(String(Number(o.cash) - Number(o.overdraft)))} sub={Number(o.overdraft) > 0 ? `cheque especial: ${fmtBRL(o.overdraft)}` : undefined} tone={Number(o.overdraft) > 0 ? "down" : "neutral"} emphasis />
        <StatCard label="Patrimônio total" value={fmtBRL(o.net_worth)} sub={`${fmtBRL(o.invested)} investidos`} />
        <StatCard label="Receitas do mês" value={fmtBRL(o.monthly_income)} tone="up" />
        <StatCard label="Despesas do mês" value={fmtBRL(o.monthly_expense)} sub={`saldo previsto ${fmtBRL(String(flow))}`} tone={trend(String(flow))} />
        <StatCard label="Dívidas" value={fmtBRL(o.debts)} tone={Number(o.debts) > 0 ? "down" : "neutral"} />
        <StatCard label="Renda passiva (mês)" value={fmtBRL(o.passive_income)} sub={`reserva: ${o.emergency_months.toFixed(1)} meses`} />
      </section>
      <div className="cols-2">
        <section className="card stack">
          <div className="row between"><h2>Empresas</h2><Link className="small" to="/empresas">abrir</Link></div>
          {o.companies.length === 0 ? <p className="muted small">Nenhuma empresa ativa.</p> :
            <ul className="list-plain">{o.companies.map((c) => <li key={c.id}><Link to={`/empresas/${c.id}`}>{c.name}</Link><span className="chip">{c.segment.toLowerCase()}</span></li>)}</ul>}
        </section>
        <section className="card stack">
          <div className="row between"><h2>Família e bem-estar</h2><Link className="small" to="/vida">abrir</Link></div>
          <p className="muted small">{o.family.partner ? STAGE[o.family.partner] ?? o.family.partner : "Sem parceiro(a)"} · {o.family.children} filho(s) · {o.family.members} pessoa(s) na família</p>
          {o.wellbeing ? (<><Meter label="Saúde" value={o.wellbeing.health} /><Meter label="Bem-estar" value={o.wellbeing.wellbeing} /><Meter label="Qualidade de vida" value={o.wellbeing.quality} /></>) : <p className="muted small">Abra “Vida pessoal” para criar seu personagem.</p>}
          {o.pending_life_decisions > 0 && <span className="chip warn">{o.pending_life_decisions} decisão(ões) pessoal(is)</span>}
        </section>
        <section className="card stack">
          <div className="row between"><h2>Economia agora</h2><Link className="small" to="/economia">abrir</Link></div>
          {o.economy ? (
            <ul className="list-plain">
              <li><span>Inflação (a.a.)</span><b className="num">{Number(o.economy.inflation).toFixed(2)}%</b></li>
              <li><span>Juros (a.a.)</span><b className="num">{Number(o.economy.interest).toFixed(2)}%</b></li>
              <li><span>Desemprego</span><b className="num">{Number(o.economy.unemployment).toFixed(1)}%</b></li>
              <li><span>Crescimento (a.a.)</span><b className="num">{Number(o.economy.growth).toFixed(2)}%</b></li>
              <li><span>Confiança do consumidor</span><b className="num">{Number(o.economy.confidence).toFixed(0)}</b></li>
            </ul>) : <p className="muted small">Economia estável (sem variação). Inicie uma partida para ativar a economia dinâmica.</p>}
          {o.pending_events > 0 && <span className="chip warn">{o.pending_events} decisão(ões) aguardando</span>}
        </section>
        <section className="card stack">
          <div className="row between"><h2>Objetivos</h2><Link className="small" to="/resumos">ver todos</Link></div>
          {o.goals.length === 0 ? <p className="muted small">Sem objetivos: o modo livre não impõe metas. Crie as suas em “Resumos”.</p> :
            o.goals.slice(0, 5).map((g) => <Meter key={g.id} label={`${g.title}${g.status === "DONE" ? " ✓" : ""}`} value={g.progress * 100} />)}
          <span className="muted small">{o.achievements_unlocked} conquista(s)</span>
        </section>
      </div>
    </div>
  );
}
