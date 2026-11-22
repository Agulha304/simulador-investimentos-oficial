import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { EXPANSION_KINDS, ExpansionModal, HireModal, LeaseModal, LoanModal, MoneyModal, RelocateModal, SupplierModal } from "../components/CompanyModals";
import { RecruiterCard, ReportPanel, SupplierLimitsModal, TeamModal } from "../components/CompanyRecruiter";
import { StatCard } from "../components/StatCard";
import { api, type CoRecruiterReport, type CoSupplierContract, type CompanyDetail, type Good, type Listing } from "../services/api";
import { cachedGet } from "../services/dataCache";
import { CATEGORY_LABEL, CO_COST_LABEL, CO_EVENT_LABEL, EDUCATION_LABEL, LEDGER_LINE_LABEL, LEVEL_LABEL, fmtBRL, fmtMonth, fmtPct, parseMoneyInput, trend } from "../lib/format";

const RevenueCostChart = lazy(() => import("../components/charts/CompanyCharts").then((m) => ({ default: m.RevenueCostChart })));
const NetResultChart = lazy(() => import("../components/charts/CompanyCharts").then((m) => ({ default: m.NetResultChart })));
const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
type Modal = "contribute" | "distribute" | "hire" | "loan" | "lease" | "relocate" | "supplier" | "expansion" | "team" | "limits" | null;
// rótulos por tipo de empresa (metrics_kind): produção/varejo têm estoque e produção; serviços têm capacidade de atendimento própria
const CAP_LABEL: Record<string, string> = {
  "atendimento": "Capacidade de atendimento (clientes/mês)", "serviço": "Capacidade de atendimento (serviços/mês)", "contrato": "Projetos/mês",
  "conta atendida": "Contas atendidas/mês", "negócio fechado": "Negócios fechados/mês", "viagem": "Viagens/mês", "pedido": "Pedidos/mês",
};
const capLabel = (kind: string, unit: string) => kind === "SERVICE" ? (CAP_LABEL[unit] ?? `Capacidade de atendimento (${unit}s/mês)`) : `Capacidade de produção (${unit}s/mês)`;
const demandLabel = (kind: string, unit: string) => kind === "SERVICE" ? `Demanda esperada (${CAP_LABEL[unit]?.split(" (")[0].toLowerCase() ?? unit})` : `Demanda esperada (${unit}s/mês)`;
const SCHEDULE_HELP = "6x1 = seis dias de trabalho e uma folga; 5x2 = segunda a sexta; 12x36 = 12 h de trabalho e 36 h de folga; 4x3 = quatro dias de trabalho e três de folga";
const TAX_REGIME_LABEL: Record<string, string> = { MEI: "MEI (DAS-MEI)", SIMPLES: "Simples Nacional (DAS)", LUCRO_PRESUMIDO: "Lucro Presumido" };

export function CompanyPage() {
  const id = Number(useParams().id);
  const [d, setD] = useState<CompanyDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [modal, setModal] = useState<Modal>(null);
  const [hireRole, setHireRole] = useState<string | undefined>(undefined);
  const [supCat, setSupCat] = useState<string>("");
  const [report, setReport] = useState<CoRecruiterReport | null>(null);
  const [limitsCt, setLimitsCt] = useState<CoSupplierContract | null>(null);
  const [personalGoods, setPersonalGoods] = useState<Good[]>([]);
  const [market, setMarket] = useState<Listing[]>([]);

  const reload = useCallback(() => api.company(id).then((x) => { setD(x); setError(null); }).catch((e) => setError(errMsg(e))), [id]);
  useEffect(() => { void reload(); cachedGet<Good[]>("/goods?").then(setPersonalGoods).catch(() => undefined); cachedGet<Listing[]>("/goods/market?").then(setMarket).catch(() => undefined); }, [reload]);

  if (error && !d) return <div className="page"><Link to="/empresas" className="link-btn" style={{ marginLeft: 0 }}>← Empresas</Link><div className="alert">{error}</div></div>;
  if (!d) return <div className="muted">Carregando empresa…</div>;
  const c = d.company;
  const last = d.months[0];
  const done = (next: CompanyDetail, msg: string) => { setD(next); setModal(null); setNotice(msg); setError(null); };
  async function act(fn: () => Promise<CompanyDetail>, msg: string) {
    try { done(await fn(), msg); } catch (e) { setError(errMsg(e)); setNotice(null); }
  }
  async function runReport(fn: () => Promise<CoRecruiterReport>) {
    try { const r = await fn(); setD(r.company); setReport(r); setModal(null); setError(null); setNotice(null); } catch (e) { setError(errMsg(e)); setNotice(null); setModal(null); }
  }
  const hasRecruiter = d.recruiter?.status === "ACTIVE";
  const recruiterHint = "Contrate um contratador (cartão \"Contratador\") para usar esta opção.";
  const lowRunway = d.runway_months != null && Number(d.runway_months) < 2;

  return (
    <div className="page">
      <Link to="/empresas" className="link-btn" style={{ marginLeft: 0 }}>← Empresas</Link>
      <header className="page-head">
        <div>
          <h1>{c.name}</h1>
          <p className="muted">{c.segment_label} · {c.channel === "ONLINE" ? "operação online" : `${c.location_label} (${c.site_mode === "BUY" ? "terreno próprio" : "alugado"})`} · porte {c.size === "SMALL" ? "pequeno" : c.size === "MEDIUM" ? "médio" : "grande"} · {c.units} unidade(s) · sua participação {c.owner_share_pct}%</p>
        </div>
        <div className="row-gap" style={{ flexWrap: "wrap" }}>
          <button className="btn small ghost" onClick={() => setModal("contribute")}>Aportar capital</button>
          <button className="btn small ghost" onClick={() => setModal("loan")}>Empréstimo</button>
          <button className="btn small primary" onClick={() => setModal("distribute")}>Distribuir lucros</button>
        </div>
      </header>
      {error && <div className="alert">{error}</div>}
      {notice && <div className="ok">{notice}</div>}
      {d.compliance && !d.compliance.regular && !(d.compliance.grace_months ?? 0) && (
        <div className="alert" role="alert">
          <b>Empresa irregular.</b> Faltam: {d.compliance.missing_labels.join(", ")}. Sem isso a empresa não vende e paga multa (estimada em {fmtBRL(d.compliance.estimated_fine)}) no fechamento do mês. Contrate antes de fechar o mês.
        </div>
      )}
      {d.supply?.required && d.supply.warning && (
        <div className="alert" role="alert"><b>Fornecedores pendentes.</b> {d.supply.warning} Veja a seção "Fornecedores e orçamento" abaixo.</div>
      )}
      {d.market?.crisis.active && (
        <div className="alert" role="alert">
          <b>Crise econômica afetando o seu setor.</b> {d.market.crisis.crises.map((x) => `${x.label} (${x.phase === "ONSET" ? "início" : x.phase === "PEAK" ? "auge" : "recuperação"})`).join("; ") || "Demanda geral em queda"}:
          vendas do mês esperadas com <b>{fmtPct(String((d.market.crisis.sales_mult - 1) * 100))}</b> de variação na demanda (efeito do setor {String(d.market.crisis.sector_pct).replace(".", ",")}%; índice de demanda do país {String(d.market.crisis.demand_index).replace(".", ",")}). Segure custos e caixa até a recuperação.
        </div>
      )}
      {c.suspended_until && <div className="alert">Despejo: a empresa está sem ponto e não vende até {fmtMonth(c.suspended_until)} (ou até você mudar de endereço).</div>}
      {lowRunway && <div className="alert">Atenção: o caixa cobre apenas {Number(d.runway_months).toFixed(1).replace(".", ",")} mês(es) de custos fixos e folha. Aporte capital, ajuste custos ou reduza a equipe.</div>}

      <section className="stats-grid">
        <StatCard label="Caixa" value={fmtBRL(c.cash)} emphasis tone={Number(c.cash) < 0 ? "down" : "neutral"} sub={d.runway_months != null ? `cobre ${Number(d.runway_months).toFixed(1).replace(".", ",")} mês(es)` : undefined} />
        <StatCard label="Patrimônio da empresa" value={fmtBRL(c.equity)} sub={c.site_mode === "BUY" ? "caixa + estoque + bens + terreno − dívidas" : "caixa + estoque + bens − dívidas"} />
        <StatCard label="Dívidas" value={fmtBRL(c.debts)} />
        <StatCard label="Lucro distribuível" value={fmtBRL(d.distributable_profit)} sub="acumulado ainda não distribuído" />
        <StatCard label="Reputação" value={`${c.reputation}/100`} sub={c.marketing_until ? `campanha até ${fmtMonth(c.marketing_until)}` : undefined} />
        <StatCard label="Relevância" value={`${c.relevance.toFixed(1).replace(".", ",")}/100`} sub={`demanda em ${d.market ? Math.round(d.market.demand_factor * 100) : "—"}% do potencial`} />
        <StatCard label="Custos fixos + folha / mês" value={fmtBRL(d.monthly_obligations)} />
        {d.supply?.required && <StatCard label="Fornecedores — gasto previsto / mês" value={fmtBRL(c.supplier_budget ?? "0")} sub={d.supply.ready ? "preço contratado × consumo esperado" : "faltam contratos de fornecedores"} />}
      </section>

      <section className="card">
        <h2>Indicadores operacionais</h2>
        <dl className="facts">
          <div><dt>{demandLabel(c.metrics_kind, c.unit_label)}</dt><dd className="num">≈ {d.expected_demand}/mês — estimativa, sem sazonalidade; o mês real varia (sazonalidade, economia, sorte){d.market && d.market.zero_month_prob > 0.02 ? ` e há ${Math.round(d.market.zero_month_prob * 100)}% de chance de o próximo mês fechar sem nenhuma venda` : ""}</dd></div>
          <div><dt>{capLabel(c.metrics_kind, c.unit_label)}</dt><dd className="num">{d.expected_capacity}/mês{d.market ? ` (teto do porte: ${d.market.production_cap})` : ""}{d.expected_capacity < d.expected_demand ? " — abaixo da demanda: você perde vendas" : ""}</dd></div>
          {d.market && c.metrics_kind !== "SERVICE" && <div><dt>Teto de estoque (armazenagem)</dt><dd className="num">{d.market.storage_cap_units} {c.unit_label}(s) vendáveis</dd></div>}
          {d.market && <div><dt>Funcionários</dt><dd className="num">{d.market.staff_count} de {d.market.max_staff} (teto do porte)</dd></div>}
          <div><dt>Preço de venda</dt><dd className="num">{fmtBRL(c.price)}</dd></div>
          <div><dt>Pró-labore mensal</dt><dd className="num">{fmtBRL(c.owner_salary)}</dd></div>
        </dl>
        <SettingsForm d={d} showRestock={c.metrics_kind !== "SERVICE"} onSave={(body) => act(() => api.coSettings(c.id, body), "Ajustes salvos.")} />
      </section>

      {d.market && (
        <section className="card" aria-label="Relevância">
          <h2>Relevância no mercado</h2>
          <div className="meter" style={{ height: 10, background: "var(--line, #ddd)", borderRadius: 6, overflow: "hidden" }} role="progressbar" aria-valuenow={Math.round(c.relevance)} aria-valuemin={0} aria-valuemax={100}>
            <div style={{ width: `${Math.max(2, c.relevance)}%`, height: "100%", background: "var(--accent, #2b6cb0)" }} />
          </div>
          <p className="muted small" style={{ margin: "6px 0 0" }}>
            <b>{c.relevance.toFixed(1).replace(".", ",")}/100</b> — a demanda do ponto é multiplicada por {d.market.demand_factor.toFixed(2).replace(".", ",")} (de 0,25 com relevância 0 a 1,00 com 100).
            Preço do mercado: {Math.round(d.market.price_ratio * 100)}% ({d.market.price_ratio > 1.25 ? "caro demais: derruba as vendas e aumenta a chance de mês sem vendas" : d.market.price_ratio < 0.9 ? "barato: vende um pouco mais, mas o ganho é limitado" : "dentro do mercado"}).
          </p>
          <p className="muted small" style={{ margin: 0 }}>
            A relevância sobe devagar (cerca de 1 ponto por mês quando tudo vai bem; chegar a 50 leva mais de 2 anos) com clientes atendidos (vendas ≥ 60% da demanda), boa reputação, campanha de marketing ativa, estoque em dia e preço justo. Cai em meses sem vendas ou irregulares.
            No começo é normal ter prejuízo e até meses sem nenhuma venda: o capital mínimo já traz uma reserva para isso.
          </p>
        </section>)}

      <section className="card">
        <h2>Demonstrativo do último mês fechado{last ? ` (${fmtMonth(last.ref_month)})` : ""}</h2>
        {!last ? <div className="empty">Feche o mês do simulador (aba Orçamento) para a empresa operar e gerar o primeiro demonstrativo.</div> : (
          <>
            <dl className="facts">
              <div><dt>Vendas</dt><dd className="num">{last.units_sold} {c.unit_label}(s) de {last.demand_units} de demanda{last.stockout && c.metrics_kind !== "SERVICE" ? " — faltou estoque" : ""}{last.zero_sales ? " — mês sem nenhuma venda (relevância baixa ou preço fora do mercado)" : ""}</dd></div>
              <div><dt>Receita bruta</dt><dd className="num tone-up">{fmtBRL(last.revenue)}</dd></div>
              <div><dt>(−) Custos variáveis ({c.metrics_kind === "SERVICE" ? "insumos diretos, taxas e comissões" : "mercadorias e outros"})</dt><dd className="num">{fmtBRL(last.variable_costs)}</dd></div>
              <div><dt>(−) Custos fixos ({c.channel === "ONLINE" || c.site_mode === "BUY" ? "energia, estrutura" : "aluguel, energia, estrutura"})</dt><dd className="num">{fmtBRL(last.fixed_costs)}</dd></div>
              {last.irregular && <div><dt className="tone-down">Mês irregular</dt><dd className="tone-down">sem cargos obrigatórios: vendas zeradas e multa de {fmtBRL(last.fines ?? "0")} (dentro dos custos fixos)</dd></div>}
              <div><dt>(−) Folha de pagamento (CLT 2×, PJ 1×) e pró-labore</dt><dd className="num">{fmtBRL(last.payroll)}</dd></div>
              <div><dt>= Resultado operacional</dt><dd className={`num tone-${trend(last.operating_result)}`}>{fmtBRL(last.operating_result)}</dd></div>
              <div><dt>(−) Impostos{last.tax_regime ? ` — ${TAX_REGIME_LABEL[last.tax_regime] ?? last.tax_regime}` : ""}</dt><dd className="num">{fmtBRL(last.taxes)}</dd></div>
              {(last.tax_breakdown ?? []).map((t) => (
                <div key={t.name}><dt className="muted small">&nbsp;&nbsp;↳ {t.name} ({t.rate_pct}% sobre {fmtBRL(t.base)})</dt><dd className="num muted small">{fmtBRL(t.amount)}</dd></div>))}
              <div><dt>(−) Juros</dt><dd className="num">{fmtBRL(last.interest)}</dd></div>
              <div><dt>= Resultado líquido</dt><dd className={`num tone-${trend(last.net_result)}`}><b>{Number(last.net_result) >= 0 ? "▲ " : "▼ "}{fmtBRL(last.net_result)}</b></dd></div>
              <div><dt>Saldo de caixa / dívidas / patrimônio</dt><dd className="num">{fmtBRL(last.cash_end)} / {fmtBRL(last.debts_end)} / {fmtBRL(last.equity_end)}</dd></div>
            </dl>
          </>
        )}
      </section>
      {last && (
        <p className="muted small" style={{ margin: "0 0 .75rem" }}>
          <b>Como o imposto é calculado:</b> o regime é escolhido automaticamente todo mês pelo faturamento dos últimos 12 meses (RBT12; com menos de 12 meses, usa-se a média mensal × 12):
          MEI (até R$ 81 mil/ano, 1 empregado CLT e atividade permitida, valor fixo — nunca se volta ao MEI depois de sair), Simples Nacional (DAS, alíquota efetiva = (RBT12 × alíquota − parcela a deduzir) ÷ RBT12; no Fator R, folha ≥ 28% do faturamento paga o Anexo III em vez do V)
          e Lucro Presumido acima de R$ 4,8 mi/ano (IRPJ, CSLL, PIS, COFINS e ISS, ICMS ou IPI conforme a atividade). Encargos já incluídos no custo CLT de 2× (INSS patronal, FGTS, 13º e férias não são cobrados de novo).
          <i> Simplificações: ICMS fixo de 18% (varia por estado), IPI fixo de 10%, ISS típico por atividade, sem sublimite do Simples, apuração mensal; pró-labore, IRPF do dono e retenção sobre dividendos não são calculados.</i>
        </p>)}
      <Suspense fallback={<div className="card muted">Carregando gráficos…</div>}>
        <div className="grid-2"><RevenueCostChart months={d.months} /><NetResultChart months={d.months} /></div>
      </Suspense>

      {d.partners && d.partners.length > 0 && (
        <section className="card stack"><h2>🤝 Sócios</h2>
          <p className="muted small" style={{ margin: 0 }}>Sua participação: <b>{d.company.owner_share_pct}%</b>. Os lucros distribuídos são divididos pelas participações. Sociedade tem riscos: um sócio pode dar calote.</p>
          <ul className="list-plain">{d.partners.map((p) => (
            <li key={p.person_id}><span><b>{p.name}</b> <span className="muted small">· situação {p.finance} · entrou com {fmtBRL(p.contribution)}</span></span>
              <span className={`chip ${p.status === "ACTIVE" ? "up" : "down"}`}>{p.share_pct}% · {p.status === "ACTIVE" ? "sócio(a)" : "deu calote"}</span></li>))}</ul>
        </section>)}
      <RecruiterCard d={d} act={act} onReport={runReport} onTeam={() => setModal("team")} />
      {d.compliance && (
        <section className="card" aria-label="Cargos obrigatórios">
          <div className="row"><h2>Obrigatórios</h2>
            <button type="button" className="btn small ghost" disabled={!hasRecruiter || d.compliance.regular} title={!hasRecruiter ? recruiterHint : d.compliance.regular ? "Nada a contratar" : "O contratador contrata todos os que faltam"}
              onClick={() => void runReport(() => api.coRecruiterMandatory(c.id))}>Contratar via contratador</button></div>
          {(d.compliance.grace_months ?? 0) > 0 && !d.compliance.regular && (
            <p className="muted small" role="status"><b>Período de adaptação: {d.compliance.grace_months} {d.compliance.grace_months === 1 ? "mês restante" : "meses restantes"}</b> — contrate os cargos obrigatórios antes que acabe.</p>)}
          <ul className="list-plain">{d.compliance.required.map((q) => (
            <li key={q.role}>
              <span className={q.present ? "tone-up" : "tone-down"}>{q.present ? "✓" : "✗"} <b>{q.label}</b></span>
              {q.present ? <span className="muted small">contratado</span> : <button className="link-btn" onClick={() => { setHireRole(q.role); setModal("hire"); }}>contratar</button>}
            </li>))}</ul>
          <p className="muted small" style={{ margin: 0 }}>Basta o cargo estar preenchido com jornada de pelo menos 20 h/semana (meio período vale; no porte pequeno o salário é bem menor e proporcional às horas). Contador e Advogado são obrigatórios{c.channel === "PHYSICAL" ? "; empresa física também precisa de Auxiliar de limpeza" : " (empresa online não precisa de limpeza)"}. Sem todos no fechamento do mês a empresa fica irregular: não vende e paga multa de 1 salário-base de cada cargo faltante. Não há tolerância no mês da abertura (empresas anteriores à atualização têm um período de adaptação).</p>
        </section>
      )}

      {d.supply?.required && (
        <section className="card" aria-label="Fornecedores e orçamento">
          <h2>Fornecedores e orçamento</h2>
          <ul className="list-plain">{d.supply.checklist.map((q) => (
            <li key={q.category}>
              <span className={q.present ? "tone-up" : "tone-down"}>{q.present ? "✓" : "✗"} <b>{q.label}</b></span>
              {q.present ? <span className="muted small">{q.supplier}</span> : <span className="muted small">sem contrato — {c.metrics_kind === "SERVICE" ? "operação bloqueada" : "sem reposição"}</span>}
            </li>))}</ul>
          <div className="table-wrap"><table>
            <thead><tr><th>Categoria</th><th>Fornecedor</th><th className="r">Preço contratado</th><th className="r">Volume previsto/mês</th><th className="r">Gasto previsto</th><th className="r">Gasto realizado (último mês)</th><th /></tr></thead>
            <tbody>{d.supply.budget.rows.map((r) => {
              const ct = d.supply!.contracts.find((x) => x.category === r.category);
              return (
                <tr key={r.category}>
                  <td><b>{r.label}</b><br /><span className="muted small">{Math.round(Number(r.weight) * 100)}% do custo</span></td>
                  <td>{r.supplier ?? <span className="tone-down">sem contrato</span>}{ct && <><br /><span className="muted small">mín. {ct.min_monthly_order} · até {ct.effective_volume ?? ct.max_units_month} {ct.unit}/mês · confiab. {Math.round(ct.reliability * 100)}% · prazo {ct.lead_days} d{ct.is_default ? " · contrato padrão" : ""}</span>
                    {(ct.max_monthly_spend != null || ct.volume_cap != null || ct.min_reliability != null || ct.max_lead_days != null) && <><br /><span className="muted small">limites: {[ct.max_monthly_spend != null ? `gasto até ${fmtBRL(ct.max_monthly_spend)}/mês (gasto no mês: ${fmtBRL(ct.spend_used ?? "0")})` : "", ct.volume_cap != null ? `volume até ${ct.volume_cap}` : "", ct.min_reliability != null ? `confiab. mín. ${Math.round(ct.min_reliability * 100)}%` : "", ct.max_lead_days != null ? `prazo até ${ct.max_lead_days} d` : ""].filter(Boolean).join(" · ")}</span></>}</>}</td>
                  <td className="r num">{fmtBRL(r.unit_price)}{r.estimated ? <span className="muted small"> (ref.)</span> : ""}<br /><span className="muted small">/{r.unit}</span></td>
                  <td className="r num">{r.planned_volume} {r.unit}</td>
                  <td className="r num">{r.estimated ? <span className="muted">{fmtBRL(r.planned_spend)} (estimativa)</span> : fmtBRL(r.planned_spend)}{r.max_monthly_spend != null && <><br /><span className={`small ${r.over_limit ? "tone-down" : "muted"}`}>limite {fmtBRL(r.max_monthly_spend)}{r.over_limit ? " — previsto acima do limite: a reposição trava" : ""}</span></>}</td>
                  <td className="r num">{d.supply!.budget.last_month ? fmtBRL(r.last_actual) : "—"}</td>
                  <td className="r">
                    {!ct && <button className="btn small ghost" onClick={() => { setSupCat(r.category); setModal("supplier"); }}>Procurar fornecedores</button>}
                    {ct && <button className="link-btn" onClick={() => { setLimitsCt(ct); setModal("limits"); }}>limites</button>}
                    {ct && <button className="link-btn" onClick={() => window.confirm(`Encerrar o contrato com ${ct.name}?${Number(ct.early_end_fine) > 0 ? `\nMulta por encerrar antes de 3 meses: ${fmtBRL(ct.early_end_fine)}.` : "\nSem multa."}\nSem contrato a categoria não é reposta${c.metrics_kind === "SERVICE" ? " e a operação fica bloqueada" : ""}.`) && act(() => api.coSupplierEnd(c.id, ct.id), "Contrato encerrado.")}>encerrar</button>}
                  </td>
                </tr>);
            })}</tbody>
            <tfoot><tr><td colSpan={4}><b>Total de insumos</b> (categorias contratadas)</td><td className="r num"><b>{fmtBRL(d.supply.budget.total_planned)}</b></td><td className="r num"><b>{d.supply.budget.last_month ? fmtBRL(d.supply.budget.total_last_actual) : "—"}</b></td><td /></tr>
              {d.supply.budget.total_limit != null && <tr><td colSpan={4}>Gasto máximo total (briefing do contratador)</td><td className={`r num ${d.supply.budget.over_total ? "tone-down" : ""}`}>{fmtBRL(d.supply.budget.total_limit)}{d.supply.budget.over_total ? " — previsto acima" : ""}</td><td colSpan={2} /></tr>}</tfoot>
          </table></div>
          <p className="muted small" style={{ margin: 0 }}>
            Previsto = vendas esperadas do mês ({d.expected_demand} de demanda, limitadas pela equipe e pelos fornecedores) × consumo por venda × preço contratado.
            {d.supply.effective_capacity != null && <> Capacidade efetiva pelos fornecedores: <b>{d.supply.effective_capacity}</b> {c.unit_label}(s)/mês (o menor volume contratado entre as categorias).</>}
            {" "}Fornecedor menos confiável pode falhar num mês (entrega parcial{c.metrics_kind === "SERVICE" ? ", reduzindo a capacidade do mês" : ""}). Para mais volume, encerre o contrato e contrate outro fornecedor.
          </p>
        </section>
      )}

      <section className="card">
        <div className="row"><h2>Funcionários</h2><span className="row-gap">
          <button className="btn small ghost" onClick={() => { setHireRole(undefined); setModal("hire"); }}>+ Contratar</button>
          <button className="btn small ghost" disabled={!hasRecruiter} title={hasRecruiter ? "Escolha quantos de cada área" : recruiterHint} onClick={() => setModal("team")}>Contratar via contratador</button></span></div>
        {d.employees.length === 0 && <div className="empty">Nenhum funcionário. A empresa nasce sem equipe: sem funcionários produtivos só o dono produz ({d.expected_capacity} /mês).</div>}
        {d.employees.length > 0 && (
          <div className="table-wrap"><table>
            <thead><tr><th>Funcionário</th><th>Regime</th><th title={SCHEDULE_HELP}>Escala</th><th>Escolaridade</th><th>Nível</th><th className="r">Salário negociado</th><th className="r">Custo real/mês</th><th>Situação</th><th /></tr></thead>
            <tbody>{d.employees.map((e) => (
              <tr key={e.id} className={e.status === "ACTIVE" ? "" : "muted"}>
                <td><b>{e.name || e.role_label}</b><br /><span className="muted small">{e.role_label} · {e.experience_years} ano(s) exp.{(e.lawsuit_history ?? 0) > 0 ? ` · histórico: ${e.lawsuit_history} processo${(e.lawsuit_history ?? 0) > 1 ? "s" : ""} anterior${(e.lawsuit_history ?? 0) > 1 ? "es" : ""}` : ""}</span></td>
                <td><span className={`chip ${e.regime === "CLT" ? "up" : "down"}`}>{e.regime}</span></td>
                <td>{e.schedule} <span className="muted small">{e.hours_week} h</span></td><td>{EDUCATION_LABEL[e.education] ?? e.education_label}</td><td>{LEVEL_LABEL[e.level]}</td>
                <td className="r num">{fmtBRL(e.salary)}</td><td className="r num">{fmtBRL(e.total_cost)}<br /><span className="muted small">{e.regime === "CLT" ? "2× o salário" : "1× o salário"}</span></td>
                <td>{e.status === "ACTIVE" ? `desde ${fmtMonth(e.hired_on)}` : `desligado em ${e.terminated_on ? fmtMonth(e.terminated_on) : ""}`}</td>
                <td className="r">{e.status === "ACTIVE" && <button className="link-btn" onClick={() => window.confirm(
                  `Desligar ${e.name || e.role_label}?\nRescisão: ${e.regime === "CLT" ? `${fmtBRL(e.severance_estimate)} (1 salário + aviso prévio)` : "nenhuma (PJ)"}.\nRisco de processo trabalhista: ${String(e.lawsuit_risk_pct).replace(".", ",")}%${e.regime === "PJ" ? " — PJ costuma alegar vínculo empregatício e processar com muito mais frequência que CLT" : ""}${e.hours_week > 44 || e.schedule === "6x1" ? ". Jornada acima de 44 h/semana e escala 6x1 aumentam o risco" : ""}.`) && act(() => api.coFire(c.id, e.id), "Funcionário desligado.")}>desligar</button>}</td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
        <p className="muted small" style={{ margin: 0 }}>Custo real: CLT = 2× o salário negociado; PJ = 1× (sem encargos, mas com risco alto de processo ao demitir). {SCHEDULE_HELP}.</p>
      </section>

      {d.inventory.length > 0 && (
        <section className="card">
          <h2>Estoque</h2>
          <div className="table-wrap"><table>
            <thead><tr><th>Item</th><th>Fornecedor</th><th className="r">Quantidade</th><th className="r">Custo médio</th><th className="r">Mínimo</th><th className="r">Teto</th><th className="r">Consumo estimado/mês</th><th /></tr></thead>
            <tbody>{d.inventory.map((i) => (
              <tr key={i.id}>
                <td><b>{i.name}</b> {i.low && <span className="tag tone-warn">baixo</span>}{i.contracted === false && <span className="tag tone-warn">sem fornecedor</span>}</td><td className="muted">{i.supplier}</td>
                <td className="r num">{i.quantity} {i.unit}</td><td className="r num">{fmtBRL(i.unit_cost)}</td><td className="r num">{i.min_quantity}</td><td className="r num">{i.max_quantity ?? "—"}</td><td className="r num">{i.monthly_consumption_est}</td>
                <td className="r"><button className="link-btn" onClick={() => { const q = window.prompt(`Quantidade de ${i.name} a comprar (${i.unit})`); if (q) void act(() => api.coStock(c.id, i.id, parseMoneyInput(q)), "Estoque comprado."); }}>comprar</button></td>
              </tr>
            ))}</tbody>
          </table></div>
          <p className="muted small">Reposição automática {c.auto_restock ? "ligada" : "desligada"}: no fechamento, a empresa compra o que falta (se houver caixa). Sem estoque, as vendas param; sem contrato de fornecedor da categoria, o item não é reposto.</p>
        </section>
      )}

      <section className="card">
        <div className="row"><h2>Instalações e custos</h2><span className="row-gap">{c.channel === "PHYSICAL" && <button className="btn small ghost" onClick={() => setModal("relocate")}>Mudar de endereço</button>}{c.channel === "PHYSICAL" && c.site_mode !== "BUY" && <button className="btn small ghost" onClick={() => setModal("lease")}>Alterar instalações</button>}</span></div>
        <dl className="facts">
          <div><dt>Instalações</dt><dd>{c.channel === "ONLINE" ? "operação online — sem ponto físico nem aluguel" : c.site_mode === "BUY" ? `terreno próprio (${fmtBRL(c.site_value)}) — sem aluguel` : d.lease ? `${d.lease.name} — ${fmtBRL(d.lease.monthly_rent)}/mês (${d.lease.kind === "EXTERNAL" ? "alugado de terceiros" : d.lease.kind === "OWN_GOOD" ? "imóvel seu, alugado à empresa" : "imóvel da empresa"})` : "nenhuma"}</dd></div>
          {d.costs.map((x) => <div key={x.id}><dt>{CO_COST_LABEL[x.kind] ?? x.kind}</dt><dd className="num">{fmtBRL(x.amount)}/mês{x.active ? "" : " (inativo)"}</dd></div>)}
        </dl>
      </section>

      <section className="card">
        <h2>Expansão</h2>
        <p className="muted small" style={{ margin: 0 }}>Cada aporte tem 3 níveis (barato, médio, caro) e 3 opções sorteadas por mês. Nível maior aumenta a chance e o efeito, mas o resultado nunca é garantido.</p>
        <div className="goods-grid">{EXPANSION_KINDS.map((k) => (
          <div key={k.key} className="card good-card"><b>{k.label}</b><span className="muted small">{k.text}</span>
            <span className="num small">{fmtBRL(d.expansion_costs[k.key]?.BARATO ?? "0")} a {fmtBRL(d.expansion_costs[k.key]?.CARO ?? "0")}</span>
            <button className="btn small ghost" onClick={() => setModal("expansion")}>Escolher…</button></div>
        ))}</div>
        <dl className="facts" style={{ marginTop: 12 }}>
          <div><dt>Qualidade dos produtos</dt><dd className="num">{(c.quality ?? 50).toFixed(1).replace(".", ",")}/100 — mais qualidade: mais relevância e tolerância a preço, insumos mais caros</dd></div>
          <div><dt>Capacidade ampliada</dt><dd className="num">+{Math.round((c.capacity_boost ?? 0) * 25)}%{(c.storage_boost ?? 0) > 0 ? ` · estoque +${Math.round((c.storage_boost ?? 0) * 100)}%` : ""}</dd></div>
        </dl>
      </section>

      {d.units_list && d.units_list.length > 1 && (
        <section className="card">
          <h2>Unidades (matriz e filiais)</h2>
          <div className="table-wrap"><table>
            <thead><tr><th>Unidade</th><th>Local</th><th>Situação</th><th className="r">Relevância</th><th className="r">Aluguel/mês</th><th className="r">Resultado acumulado</th></tr></thead>
            <tbody>{d.units_list.map((u) => (
              <tr key={u.id ?? "hq"}><td>{u.name}</td><td>{u.channel === "ONLINE" ? "online" : u.location_label}{u.site_mode === "BUY" ? " (terreno próprio)" : ""}</td>
                <td>{u.status === "OPEN" ? <span className="tag">aberta</span> : <span className="tag tone-down" title={u.closed_reason ?? ""}>fechada {u.closed_month ? fmtMonth(u.closed_month) : ""}</span>}</td>
                <td className="r num">{u.relevance.toFixed(1).replace(".", ",")}</td><td className="r num">{fmtBRL(u.monthly_rent)}</td>
                <td className="r num">{u.cumulative_result != null ? fmtBRL(u.cumulative_result) : "—"}</td></tr>))}</tbody>
          </table></div>
          <p className="muted small" style={{ margin: "8px 0 0" }}>A filial começa com parte da relevância da marca e vende, em média, menos que a matriz (pode surpreender). Fecha se o prejuízo acumulado passar de 60% do investimento ou se o caixa da empresa não cobrir. Os funcionários produtivos são distribuídos entre as unidades conforme a demanda de cada uma.</p>
          {last?.units_detail && last.units_detail.length > 1 && (
            <div className="table-wrap" style={{ marginTop: 8 }}><table>
              <thead><tr><th>Último mês</th><th className="r">Vendas</th><th className="r">Receita</th><th className="r">Resultado da unidade</th></tr></thead>
              <tbody>{last.units_detail.map((u) => <tr key={u.name}><td>{u.name}</td><td className="r num">{u.sold}</td><td className="r num">{fmtBRL(u.revenue)}</td><td className={`r num tone-${trend(u.result)}`}>{fmtBRL(u.result)}</td></tr>)}</tbody>
            </table></div>
          )}
        </section>
      )}

      <section className="card">
        <h2>Bens da empresa</h2>
        {d.goods.length === 0 ? <div className="empty">A empresa não possui bens. Equipamentos e veículos aumentam a capacidade.</div> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Bem</th><th>Categoria</th><th className="r">Valor atual</th></tr></thead>
            <tbody>{d.goods.map((g) => <tr key={g.id}><td>{g.name}</td><td>{CATEGORY_LABEL[g.category] ?? g.category}</td><td className="r num">{fmtBRL(g.current_value)}</td></tr>)}</tbody>
          </table></div>
        )}
        <div className="row-gap" style={{ marginTop: 12, maxWidth: "none" }}>
          <select id="co-good" defaultValue="" aria-label="Comprar bem para a empresa">
            <option value="">Comprar bem para a empresa…</option>
            {market.filter((l) => !l.owned && l.category !== "LAND").map((l) => <option key={l.key} value={l.key}>{l.name} — {fmtBRL(l.price)}</option>)}
          </select>
          <button className="btn small ghost" onClick={() => { const v = (document.getElementById("co-good") as HTMLSelectElement).value; if (v) void act(() => api.coBuyGood(c.id, v), "Bem comprado pela empresa."); }}>Comprar</button>
        </div>
      </section>

      {d.loans.length > 0 && (
        <section className="card">
          <h2>Empréstimos</h2>
          <div className="table-wrap"><table>
            <thead><tr><th>Contratado em</th><th className="r">Valor</th><th className="r">Taxa</th><th className="r">Prazo</th><th className="r">Saldo devedor</th><th>Situação</th></tr></thead>
            <tbody>{d.loans.map((l) => <tr key={l.id}><td>{fmtMonth(l.start_month)}</td><td className="r num">{fmtBRL(l.principal)}</td><td className="r num">{fmtPct(l.annual_rate_pct)} a.a.</td><td className="r num">{l.term_months}x</td><td className="r num">{fmtBRL(l.balance)}</td><td><span className="tag">{l.status === "ACTIVE" ? "ativo" : "quitado"}</span></td></tr>)}</tbody>
          </table></div>
        </section>
      )}

      <section className="card">
        <h2>Histórico mensal</h2>
        {d.months.length === 0 ? <div className="empty">Nenhum mês processado ainda.</div> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Mês</th><th className="r" style={{ textTransform: "capitalize" }}>{c.unit_label}s</th><th className="r">Receita</th><th className="r">Resultado líquido</th><th className="r">Caixa</th><th className="r">Patrimônio</th></tr></thead>
            <tbody>{d.months.map((m) => <tr key={m.ref_month}><td>{fmtMonth(m.ref_month)}</td><td className="r num">{m.units_sold}{m.stockout && c.metrics_kind !== "SERVICE" ? " ⚠" : ""}</td><td className="r num">{fmtBRL(m.revenue)}</td>
              <td className={`r num tone-${trend(m.net_result)}`}>{Number(m.net_result) >= 0 ? "▲ " : "▼ "}{fmtBRL(m.net_result)}</td><td className="r num">{fmtBRL(m.cash_end)}</td><td className="r num">{fmtBRL(m.equity_end)}</td></tr>)}</tbody>
          </table></div>
        )}
        <h2 style={{ marginTop: 18 }}>Movimentações da conta empresarial</h2>
        <div className="table-wrap" style={{ maxHeight: 300, overflowY: "auto" }}><table>
          <thead><tr><th>Mês</th><th>Descrição</th><th>Natureza</th><th className="r">Valor</th></tr></thead>
          <tbody>{d.ledger.map((e) => <tr key={e.id}><td>{fmtMonth(e.ref_month)}</td><td>{e.description}</td>
            <td><span className="tag">{e.capital ? "capital" : (e.line && LEDGER_LINE_LABEL[e.line]) || "resultado"}</span></td>
            <td className={`r num ${e.kind === "INCOME" ? "tone-up" : ""}`}>{e.kind === "INCOME" ? "+ " : "− "}{fmtBRL(e.amount)}</td></tr>)}</tbody>
        </table></div>
        <h2 style={{ marginTop: 18 }}>Linha do tempo</h2>
        <div className="table-wrap"><table><tbody>{d.events.map((e, i) => <tr key={i}><td>{fmtMonth(e.ref_month)}</td><td><span className="tag">{CO_EVENT_LABEL[e.type] ?? e.type}</span></td><td>{e.description}</td></tr>)}</tbody></table></div>
      </section>

      {modal === "contribute" && <MoneyModal title="Aportar capital" label="Valor (R$)" cta="Aportar" hint="O dinheiro sai da sua conta pessoal e entra no caixa da empresa. Não é despesa nem perda de patrimônio."
        run={(a) => api.coContribute(c.id, a)} onClose={() => setModal(null)} onDone={(x) => done(x, "Aporte realizado.")} />}
      {modal === "distribute" && <MoneyModal title="Distribuir lucros" label="Valor (R$)" cta="Distribuir"
        hint={`Lucro distribuível: ${fmtBRL(d.distributable_profit)} (limitado também ao caixa). Sua parte (${c.owner_share_pct}%) entra na conta pessoal e a empresa registra a saída. Não é receita operacional.`}
        run={(a) => api.coDistribute(c.id, a)} onClose={() => setModal(null)} onDone={(x) => done(x, "Lucros distribuídos.")} />}
      {modal === "hire" && <HireModal d={d} initialRole={hireRole} onClose={() => setModal(null)} onDone={(x, m) => done(x, m)} />}
      {modal === "team" && <TeamModal d={d} onClose={() => setModal(null)} onReport={runReport} />}
      {modal === "limits" && limitsCt && <SupplierLimitsModal d={d} ct={limitsCt} onClose={() => setModal(null)} onDone={(x) => done(x, "Limites do contrato salvos.")} />}
      {report && <ReportPanel r={report} onClose={() => setReport(null)} />}
      {modal === "supplier" && <SupplierModal d={d} category={supCat} onClose={() => setModal(null)} onDone={(x, m) => done(x, m)} />}
      {modal === "expansion" && <ExpansionModal d={d} onClose={() => setModal(null)} onDone={(x, m) => done(x, m)} />}
      {modal === "loan" && <LoanModal d={d} onClose={() => setModal(null)} onDone={(x) => done(x, "Empréstimo contratado.")} />}
      {modal === "relocate" && <RelocateModal d={d} onClose={() => setModal(null)} onDone={(x) => done(x, "Mudança de endereço concluída: a empresa vende menos neste mês e perdeu parte da relevância.")} />}
      {modal === "lease" && <LeaseModal d={d} goods={personalGoods} onClose={() => setModal(null)} onDone={(x) => done(x, "Instalações atualizadas.")} />}
    </div>
  );
}

function SettingsForm({ d, showRestock, onSave }: { d: CompanyDetail; showRestock: boolean; onSave: (b: { price?: string; owner_salary?: string; auto_restock?: boolean }) => void }) {
  const [price, setPrice] = useState(d.company.price);
  const [salary, setSalary] = useState(d.company.owner_salary);
  const [restock, setRestock] = useState(d.company.auto_restock);
  useEffect(() => { setPrice(d.company.price); setSalary(d.company.owner_salary); setRestock(d.company.auto_restock); }, [d.company.price, d.company.owner_salary, d.company.auto_restock]);
  return (
    <form className="row-gap" style={{ maxWidth: "none", flexWrap: "wrap", marginTop: 12 }} onSubmit={(e) => { e.preventDefault(); onSave({ price: parseMoneyInput(price), owner_salary: parseMoneyInput(salary), auto_restock: restock }); }}>
      <label>Preço de venda (R$)<input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} /></label>
      <label>Pró-labore (R$/mês)<input inputMode="decimal" value={salary} onChange={(e) => setSalary(e.target.value)} /></label>
      {showRestock && <label className="check"><input type="checkbox" checked={restock} onChange={(e) => setRestock(e.target.checked)} />Reposição automática de estoque</label>}
      <button className="btn small ghost">Salvar</button>
    </form>
  );
}
