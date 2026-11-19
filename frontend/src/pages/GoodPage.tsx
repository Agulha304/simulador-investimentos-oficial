import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { CostModal, MaintenanceModal, OccupancyModal, SellModal } from "../components/GoodsModals";
import { StatCard } from "../components/StatCard";
import { api, type GoodDetail } from "../services/api";
import {
  CATEGORY_LABEL, CONDITION_LABEL, COST_LABEL, EVENT_LABEL, FREQUENCY_LABEL, GOOD_STATUS_LABEL, OCCUPANCY_LABEL,
  fmtBRL, fmtDay, fmtMonth, fmtPct, trend,
} from "../lib/format";
import { BackLink } from "./WealthPage";

const ValueHistoryChart = lazy(() => import("../components/charts/WealthCharts").then((m) => ({ default: m.ValueHistoryChart })));
const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
type Modal = "sell" | "occupancy" | "maintenance" | "cost" | null;

export function GoodPage() {
  const id = Number(useParams().id);
  const [d, setD] = useState<GoodDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [modal, setModal] = useState<Modal>(null);

  const reload = useCallback(() => api.good(id).then((g) => { setD(g); setError(null); }).catch((e) => setError(errMsg(e))), [id]);
  useEffect(() => { void reload(); }, [reload]);

  if (error && !d) return <div className="page"><BackLink /><div className="alert">{error}</div></div>;
  if (!d) return <div className="muted">Carregando bem…</div>;
  const g = d.good;
  const active = g.status === "ACTIVE";
  const done = (next: GoodDetail, msg: string) => { setD(next); setModal(null); setNotice(msg); setError(null); };

  async function toggleCost(costId: number, activeNow: boolean) {
    try { setD(await api.updateGoodCost(g.id, costId, { active: !activeNow })); } catch (e) { setError(errMsg(e)); }
  }
  async function writeOff() {
    if (!window.confirm("Dar baixa neste bem (perda total, sem receber nada)? Essa ação não pode ser desfeita.")) return;
    try { done(await api.writeOffGood(g.id, window.prompt("Motivo (opcional)") ?? ""), "Bem baixado."); } catch (e) { setError(errMsg(e)); }
  }

  return (
    <div className="page">
      <BackLink />
      <header className="page-head">
        <div>
          <h1>{g.name}</h1>
          <p className="muted">{CATEGORY_LABEL[g.category]}{g.location ? ` · ${g.location}` : ""} · <span className="tag">{GOOD_STATUS_LABEL[g.status]}</span>
            {g.condition && <> · conservação: {CONDITION_LABEL[g.condition]}</>}</p>
        </div>
        {active && (
          <div className="row-gap" style={{ flexWrap: "wrap" }}>
            {d.real_estate && g.category !== "LAND" && <button className="btn small ghost" onClick={() => setModal("occupancy")}>Uso do imóvel</button>}
            <button className="btn small ghost" onClick={() => setModal("maintenance")}>Registrar manutenção</button>
            <button className="btn small primary" onClick={() => setModal("sell")}>Vender</button>
          </div>
        )}
      </header>
      {error && <div className="alert">{error}</div>}
      {notice && <div className="ok">{notice}</div>}

      <section className="stats-grid">
        <StatCard label={active ? "Valor atual" : "Venda"} value={fmtBRL(active ? g.current_value : g.sale_result ?? "0")} emphasis
          sub={active ? `faixa de avaliação ${fmtBRL(d.appraisal.low)} – ${fmtBRL(d.appraisal.high)}` : "resultado sobre o custo"} tone={active ? "neutral" : trend(g.sale_result)} />
        <StatCard label="Custo de aquisição" value={fmtBRL(g.acquisition_cost)} sub={`preço ${fmtBRL(g.purchase_price)} em ${fmtDay(g.acquired_on)}`} />
        <StatCard label="Valorização" value={fmtBRL(g.unrealized_result)} tone={trend(g.unrealized_result)} sub="valor atual − custo" />
        <StatCard label="Receitas do bem" value={fmtBRL(d.income_total)} tone="up" />
        <StatCard label="Despesas do bem" value={fmtBRL(d.expense_total)} />
        {d.loan && <StatCard label="Saldo devedor" value={fmtBRL(d.loan.balance)} sub={`${d.loan.paid_installments}/${d.loan.term_months} parcelas pagas`} />}
      </section>

      {d.real_estate && (
        <section className="card">
          <h2>Imóvel</h2>
          <dl className="facts">
            <div><dt>Endereço</dt><dd>{d.real_estate.address}</dd></div>
            <div><dt>Área</dt><dd>{d.real_estate.area_m2} m²{d.real_estate.bedrooms ? ` · ${d.real_estate.bedrooms} quarto(s)` : ""}</dd></div>
            <div><dt>Situação</dt><dd>{OCCUPANCY_LABEL[d.real_estate.occupancy]}</dd></div>
            {Number(d.real_estate.monthly_rent) > 0 && <div><dt>Aluguel</dt><dd className="num">{fmtBRL(d.real_estate.monthly_rent)}/mês · referência de mercado {fmtBRL(d.real_estate.market_rent)}</dd></div>}
          </dl>
          {d.real_estate.occupancy === "LISTED_FOR_RENT" && <p className="muted small">Vago e anunciado: sem aluguel até aparecer um inquilino (simulado a cada mês).</p>}
        </section>
      )}

      <Suspense fallback={<div className="card muted">Carregando gráfico…</div>}><ValueHistoryChart values={d.values} /></Suspense>

      <section className="card">
        <div className="row"><h2>Custos do bem</h2>{active && <button className="btn small ghost" onClick={() => setModal("cost")}>+ Novo custo</button>}</div>
        {d.costs.length === 0 ? <div className="empty">Este bem não tem custos recorrentes.</div> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Custo</th><th>Frequência</th><th className="r">Valor</th><th /></tr></thead>
            <tbody>{d.costs.map((c) => (
              <tr key={c.id} className={c.active ? "" : "muted"}>
                <td>{COST_LABEL[c.kind] ?? c.kind}{!c.active && <span className="tag" style={{ marginLeft: 8 }}>inativo</span>}</td>
                <td>{FREQUENCY_LABEL[c.frequency]}</td><td className="r num">{fmtBRL(c.amount)}</td>
                <td className="r">{active && <button className="link-btn" onClick={() => toggleCost(c.id, c.active)}>{c.active ? "desativar" : "reativar"}</button>}</td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
        <p className="muted small">Os custos aparecem no Orçamento de cada mês devido e são lançados no fechamento do mês.</p>
      </section>

      {d.loan && (
        <section className="card">
          <h2>Financiamento ({d.loan.system === "PRICE" ? "Price" : "SAC"})</h2>
          <dl className="facts">
            <div><dt>Financiado</dt><dd className="num">{fmtBRL(d.loan.principal)} (entrada {fmtBRL(d.loan.down_payment)})</dd></div>
            <div><dt>Taxa efetiva</dt><dd className="num">{fmtPct(d.loan.annual_rate_pct)} ao ano · {d.loan.term_months} parcelas</dd></div>
            <div><dt>Início → fim previsto</dt><dd>{fmtMonth(d.loan.start_month)} → {fmtMonth(d.loan.end_month)}</dd></div>
            <div><dt>Próxima parcela</dt><dd className="num">{d.loan.next_payment ? fmtBRL(d.loan.next_payment) : "—"}</dd></div>
          </dl>
          <p className="muted small">Cada parcela é separada em juros (despesa) e amortização (reduz a dívida, sem reduzir seu patrimônio).</p>
          <div className="table-wrap" style={{ maxHeight: 280, overflowY: "auto" }}><table>
            <thead><tr><th>Nº</th><th>Mês</th><th className="r">Parcela</th><th className="r">Juros</th><th className="r">Amortização</th><th className="r">Saldo</th><th>Situação</th></tr></thead>
            <tbody>{d.loan.installments.map((i) => (
              <tr key={i.number}><td>{i.number}</td><td>{fmtMonth(i.due_month)}</td><td className="r num">{fmtBRL(i.payment)}</td>
                <td className="r num">{fmtBRL(i.interest)}</td><td className="r num">{fmtBRL(i.amortization)}</td><td className="r num">{fmtBRL(i.balance_after)}</td>
                <td><span className="tag">{i.status === "PAID" ? "paga" : i.status === "CANCELLED" ? "quitada" : "a vencer"}</span></td></tr>
            ))}</tbody>
          </table></div>
        </section>
      )}

      <section className="card">
        <h2>Histórico</h2>
        <div className="table-wrap"><table>
          <thead><tr><th>Mês</th><th>Evento</th><th>Detalhe</th></tr></thead>
          <tbody>{d.events.map((e, i) => <tr key={i}><td>{fmtMonth(e.ref_month)}</td><td><span className="tag">{EVENT_LABEL[e.type] ?? e.type}</span></td><td>{e.description}</td></tr>)}</tbody>
        </table></div>
        <h2 style={{ marginTop: 18 }}>Movimentações financeiras</h2>
        {d.entries.length === 0 ? <div className="empty">Nenhuma movimentação ainda.</div> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Mês</th><th>Descrição</th><th>Natureza</th><th className="r">Valor</th></tr></thead>
            <tbody>{d.entries.map((e) => (
              <tr key={e.id}><td>{fmtMonth(e.ref_month)}</td><td>{e.description}</td>
                <td><span className="tag">{e.capital ? "patrimonial" : e.kind === "INCOME" ? "receita" : "despesa"}</span></td>
                <td className={`r num ${e.kind === "INCOME" ? "tone-up" : ""}`}>{e.kind === "INCOME" ? "+ " : "− "}{fmtBRL(e.amount)}</td></tr>
            ))}</tbody>
          </table></div>
        )}
      </section>

      {active && !d.loan && <div><button className="link-btn" style={{ marginLeft: 0 }} onClick={writeOff}>Dar baixa neste bem (perda)</button></div>}

      {modal === "sell" && <SellModal good={d} onClose={() => setModal(null)} onSold={(n) => done(n, "Bem vendido.")} />}
      {modal === "occupancy" && <OccupancyModal good={d} onClose={() => setModal(null)} onDone={(n) => done(n, "Uso do imóvel atualizado.")} />}
      {modal === "maintenance" && <MaintenanceModal good={d} onClose={() => setModal(null)} onDone={(n) => done(n, "Manutenção registrada.")} />}
      {modal === "cost" && <CostModal good={d} onClose={() => setModal(null)} onDone={(n) => done(n, "Custo adicionado.")} />}
    </div>
  );
}
