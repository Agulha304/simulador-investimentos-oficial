import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { StatCard } from "../components/StatCard";
import { AllocationChart, CumulativeChart, DrawdownChart, EquityChart, MonthlyChart, ReturnVsCdiChart } from "../components/charts/PerfCharts";
import { api, type Performance } from "../services/api";
import { fmtBRL, fmtPct, trend } from "../lib/format";
import { fmtNum } from "../lib/viz";

const RANGES = [{ id: "1d", label: "24 h" }, { id: "7d", label: "7 dias" }, { id: "30d", label: "30 dias" }, { id: "90d", label: "90 dias" }, { id: "all", label: "Tudo" }];
const glyph = (v: string | null) => (v == null ? "" : Number(v) > 0 ? "▲ " : Number(v) < 0 ? "▼ " : "");
const TONE_ICON = { good: "✓", warn: "!", info: "i" } as const;

export function PerformancePage() {
  const [range, setRange] = useState("30d");
  const [data, setData] = useState<Performance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(null);
    api.performance(range)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [range]);

  if (!data) return error ? <div className="alert">{error}</div> : <div className="muted">Carregando seu desempenho…</div>;
  const { summary: s, series_stats: st, trades: t } = data;

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Desempenho</h1><p className="muted">Como seu patrimônio evoluiu e como você está investindo.</p></div>
      </header>
      {error && <div className="alert">{error}</div>}

      <div className="chart-toolbar" role="group" aria-label="Período">
        {RANGES.map((r) => <button key={r.id} className={`tool${range === r.id ? " on" : ""}`} onClick={() => setRange(r.id)}>{r.label}</button>)}
        <span className="muted small">{s.days_tracked <= 1 ? "Registramos seu patrimônio a cada hora; o histórico cresce a cada dia." : `${s.days_tracked} dias registrados.`}</span>
      </div>

      <div className={loading ? "dim" : ""}>
        <section className="stats-grid">
          <StatCard label="Patrimônio" value={fmtBRL(s.wealth_brl)} sub={`ponto de partida ${fmtBRL(s.initial_brl)}`} emphasis />
          <StatCard label="Resultado total" value={`${glyph(s.pnl_brl)}${fmtBRL(s.pnl_brl)}`} sub={fmtPct(s.total_return_pct)} tone={trend(s.pnl_brl)} />
          <StatCard label="Você vs CDI (período)"
            value={st.vs_cdi_pp == null ? "—" : `${glyph(st.vs_cdi_pp)}${fmtNum(Math.abs(Number(st.vs_cdi_pp)))} p.p.`}
            sub={st.vs_cdi_pp == null ? "precisa de 2 registros" : `você ${fmtPct(st.period_return_pct)} · CDI ${fmtPct(st.cdi_pct)}`} tone={trend(st.vs_cdi_pp)} />
          <StatCard label="Maior queda desde o pico" value={st.max_drawdown_pct == null ? "—" : `${glyph(st.max_drawdown_pct)}${fmtPct(st.max_drawdown_pct)}`} sub="no período" tone={trend(st.max_drawdown_pct)} />
          <StatCard label="Diversificação" value={s.diversification_score == null ? "—" : `${s.diversification_score}/100`}
            sub={s.top_position ? `maior posição: ${s.top_position.name} (${fmtNum(Number(s.top_position.pct), 1)}%)` : "sem posições"} />
          <StatCard label="Disciplina" value={s.discipline_pct == null ? "—" : `${fmtNum(Number(s.discipline_pct), 0)}%`} sub="posições com Stop Loss ou Take Profit" />
        </section>

        {data.insights.length > 0 && (
          <section className="card insights">
            <h2>O que seus números dizem</h2>
            <ul>{data.insights.map((i, k) => (
              <li key={k} className={`ins ${i.tone}`}>
                <span className="ins-icon" aria-hidden>{TONE_ICON[i.tone as keyof typeof TONE_ICON]}</span>
                <span>{i.text}{i.lesson_id && <> <Link to={`/aulas/${i.lesson_id}`}>Aprender mais →</Link></>}</span>
              </li>))}
            </ul>
          </section>
        )}

        {data.recommended_lessons?.length > 0 && (
          <section className="card tips">
            <h2>📚 Aulas para você melhorar</h2>
            <p className="muted small">Escolhidas pelo que o seu desempenho mostrou:</p>
            <div className="tip-grid">{data.recommended_lessons.map((l) => (
              <Link key={l.lesson_id} to={`/aulas/${l.lesson_id}`} className="tip-card">
                <b>{l.title}</b><span className="small">{l.reason}</span><span className="chip">{l.review ? "🔁 revisar" : "▶ assistir"}</span></Link>))}</div>
          </section>
        )}

        <div className="viz-grid">
          <div className="wide"><EquityChart points={data.series} /></div>
          <ReturnVsCdiChart points={data.series} />
          <DrawdownChart points={data.series} />
          <AllocationChart items={data.allocation} />
          <MonthlyChart items={data.monthly} />
          <div className="wide"><CumulativeChart items={data.realized_cumulative} /></div>
        </div>

        <section className="card">
          <h2>Suas operações</h2>
          <dl className="facts grid3">
            <div><dt>Operações encerradas</dt><dd>{t.closed_trades} ({t.wins} ganhos, {t.losses} perdas)</dd></div>
            <div><dt>Taxa de acerto</dt><dd>{t.win_rate_pct == null ? "—" : `${fmtNum(Number(t.win_rate_pct), 1)}%`}</dd></div>
            <div><dt>Ganho médio</dt><dd>{t.avg_win_brl == null ? "—" : fmtBRL(t.avg_win_brl)}</dd></div>
            <div><dt>Perda média</dt><dd>{t.avg_loss_brl == null ? "—" : fmtBRL(t.avg_loss_brl)}</dd></div>
            <div><dt>Relação ganho/perda</dt><dd>{t.payoff_ratio == null ? "—" : `${fmtNum(Number(t.payoff_ratio))}×`}</dd></div>
            <div><dt>Fator de lucro</dt><dd>{t.profit_factor == null ? "—" : fmtNum(Number(t.profit_factor))}</dd></div>
            <div><dt>Melhor operação</dt><dd>{t.best_trade_brl == null ? "—" : `${t.best_trade_label}: ▲ ${fmtBRL(t.best_trade_brl)}`}</dd></div>
            <div><dt>Pior operação</dt><dd>{t.worst_trade_brl == null ? "—" : `${t.worst_trade_label}: ▼ ${fmtBRL(t.worst_trade_brl)}`}</dd></div>
            <div><dt>Proventos e juros recebidos</dt><dd>{fmtBRL(t.income_total_brl)}</dd></div>
            <div><dt>Compras · vendas · aplicações RF</dt><dd>{t.buys} · {t.sells} · {t.fixed_income_applications}</dd></div>
          </dl>
          <p className="muted small">Taxa de acerto = ganhos ÷ (ganhos + perdas). Relação ganho/perda = ganho médio ÷ perda média. Fator de lucro = soma dos ganhos ÷ soma das perdas.</p>
        </section>

        <section className="card">
          <h2>Conquistas <span className="muted small">{data.achievements.filter((a) => a.unlocked).length}/{data.achievements.length}</span></h2>
          <div className="badges">{data.achievements.map((a) => (
            <div key={a.id} className={`badge${a.unlocked ? " on" : ""}`}>
              <div className="badge-top"><b>{a.title}</b>{a.unlocked ? <span className="tag paid">conquistada ✓</span> : <span className="muted small">{a.detail}</span>}</div>
              <p className="muted small">{a.description}</p>
              <div className="bar" role="progressbar" aria-valuenow={a.current} aria-valuemin={0} aria-valuemax={a.target}><span style={{ width: `${(100 * a.current) / a.target}%` }} /></div>
            </div>))}
          </div>
        </section>
      </div>
    </div>
  );
}
