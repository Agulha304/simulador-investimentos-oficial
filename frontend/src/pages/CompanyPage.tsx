import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { HireModal, LeaseModal, LoanModal, MoneyModal } from "../components/CompanyModals";
import { StatCard } from "../components/StatCard";
import { api, type CompanyDetail, type Good, type Listing } from "../services/api";
import { CATEGORY_LABEL, CO_COST_LABEL, CO_EVENT_LABEL, LEDGER_LINE_LABEL, LEVEL_LABEL, fmtBRL, fmtMonth, fmtPct, parseMoneyInput, trend } from "../lib/format";

const RevenueCostChart = lazy(() => import("../components/charts/CompanyCharts").then((m) => ({ default: m.RevenueCostChart })));
const NetResultChart = lazy(() => import("../components/charts/CompanyCharts").then((m) => ({ default: m.NetResultChart })));
const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
type Modal = "contribute" | "distribute" | "hire" | "loan" | "lease" | null;
const EXPANSIONS: [string, string, string][] = [
  ["CAPACITY", "Ampliar capacidade", "+25% de capacidade de atendimento/produção."],
  ["NEW_UNIT", "Abrir nova unidade", "Dobra a escala (demanda e capacidade), mas também aluguel e custos fixos."],
  ["LARGER_PREMISES", "Instalações maiores", "Passa para o próximo porte: mais demanda, mais aluguel e custos."],
  ["MARKETING", "Campanha de publicidade", "+12% de demanda por 3 meses."],
];

export function CompanyPage() {
  const id = Number(useParams().id);
  const [d, setD] = useState<CompanyDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [modal, setModal] = useState<Modal>(null);
  const [personalGoods, setPersonalGoods] = useState<Good[]>([]);
  const [market, setMarket] = useState<Listing[]>([]);

  const reload = useCallback(() => api.company(id).then((x) => { setD(x); setError(null); }).catch((e) => setError(errMsg(e))), [id]);
  useEffect(() => { void reload(); api.myGoods().then(setPersonalGoods).catch(() => undefined); api.market().then(setMarket).catch(() => undefined); }, [reload]);

  if (error && !d) return <div className="page"><Link to="/empresas" className="link-btn" style={{ marginLeft: 0 }}>← Empresas</Link><div className="alert">{error}</div></div>;
  if (!d) return <div className="muted">Carregando empresa…</div>;
  const c = d.company;
  const last = d.months[0];
  const done = (next: CompanyDetail, msg: string) => { setD(next); setModal(null); setNotice(msg); setError(null); };
  async function act(fn: () => Promise<CompanyDetail>, msg: string) {
    try { done(await fn(), msg); } catch (e) { setError(errMsg(e)); setNotice(null); }
  }
  const lowRunway = d.runway_months != null && Number(d.runway_months) < 2;

  return (
    <div className="page">
      <Link to="/empresas" className="link-btn" style={{ marginLeft: 0 }}>← Empresas</Link>
      <header className="page-head">
        <div>
          <h1>{c.name}</h1>
          <p className="muted">{c.segment_label} · {c.location_label} · porte {c.size === "SMALL" ? "pequeno" : c.size === "MEDIUM" ? "médio" : "grande"} · {c.units} unidade(s) · sua participação {c.owner_share_pct}%</p>
        </div>
        <div className="row-gap" style={{ flexWrap: "wrap" }}>
          <button className="btn small ghost" onClick={() => setModal("contribute")}>Aportar capital</button>
          <button className="btn small ghost" onClick={() => setModal("loan")}>Empréstimo</button>
          <button className="btn small primary" onClick={() => setModal("distribute")}>Distribuir lucros</button>
        </div>
      </header>
      {error && <div className="alert">{error}</div>}
      {notice && <div className="ok">{notice}</div>}
      {lowRunway && <div className="alert">Atenção: o caixa cobre apenas {Number(d.runway_months).toFixed(1).replace(".", ",")} mês(es) de custos fixos e folha. Aporte capital, ajuste custos ou reduza a equipe.</div>}

      <section className="stats-grid">
        <StatCard label="Caixa" value={fmtBRL(c.cash)} emphasis tone={Number(c.cash) < 0 ? "down" : "neutral"} sub={d.runway_months != null ? `cobre ${Number(d.runway_months).toFixed(1).replace(".", ",")} mês(es)` : undefined} />
        <StatCard label="Patrimônio da empresa" value={fmtBRL(c.equity)} sub="caixa + estoque + bens − dívidas" />
        <StatCard label="Dívidas" value={fmtBRL(c.debts)} />
        <StatCard label="Lucro distribuível" value={fmtBRL(d.distributable_profit)} sub="acumulado ainda não distribuído" />
        <StatCard label="Reputação" value={`${c.reputation}/100`} sub={c.marketing_until ? `campanha até ${fmtMonth(c.marketing_until)}` : undefined} />
        <StatCard label="Custos fixos + folha / mês" value={fmtBRL(d.monthly_obligations)} />
      </section>

      <section className="card">
        <h2>Indicadores operacionais</h2>
        <dl className="facts">
          <div><dt>Demanda esperada (sem sazonalidade)</dt><dd className="num">{d.expected_demand} {c.segment_label.toLowerCase() === "" ? "" : "un."}/mês</dd></div>
          <div><dt>Capacidade operacional</dt><dd className="num">{d.expected_capacity} /mês{d.expected_capacity < d.expected_demand ? " — abaixo da demanda: você perde vendas" : ""}</dd></div>
          <div><dt>Preço de venda</dt><dd className="num">{fmtBRL(c.price)}</dd></div>
          <div><dt>Pró-labore mensal</dt><dd className="num">{fmtBRL(c.owner_salary)}</dd></div>
        </dl>
        <SettingsForm d={d} onSave={(body) => act(() => api.coSettings(c.id, body), "Ajustes salvos.")} />
      </section>

      <section className="card">
        <h2>Demonstrativo do último mês fechado{last ? ` (${fmtMonth(last.ref_month)})` : ""}</h2>
        {!last ? <div className="empty">Feche o mês do simulador (aba Orçamento) para a empresa operar e gerar o primeiro demonstrativo.</div> : (
          <>
            <dl className="facts">
              <div><dt>Vendas</dt><dd className="num">{last.units_sold} un. de {last.demand_units} de demanda{last.stockout ? " — faltou estoque" : ""}</dd></div>
              <div><dt>Receita bruta</dt><dd className="num tone-up">{fmtBRL(last.revenue)}</dd></div>
              <div><dt>(−) Custos variáveis (mercadorias e outros)</dt><dd className="num">{fmtBRL(last.variable_costs)}</dd></div>
              <div><dt>(−) Custos fixos (aluguel, energia, estrutura)</dt><dd className="num">{fmtBRL(last.fixed_costs)}</dd></div>
              <div><dt>(−) Folha de pagamento e pró-labore</dt><dd className="num">{fmtBRL(last.payroll)}</dd></div>
              <div><dt>= Resultado operacional</dt><dd className={`num tone-${trend(last.operating_result)}`}>{fmtBRL(last.operating_result)}</dd></div>
              <div><dt>(−) Impostos</dt><dd className="num">{fmtBRL(last.taxes)}</dd></div>
              <div><dt>(−) Juros</dt><dd className="num">{fmtBRL(last.interest)}</dd></div>
              <div><dt>= Resultado líquido</dt><dd className={`num tone-${trend(last.net_result)}`}><b>{Number(last.net_result) >= 0 ? "▲ " : "▼ "}{fmtBRL(last.net_result)}</b></dd></div>
              <div><dt>Saldo de caixa / dívidas / patrimônio</dt><dd className="num">{fmtBRL(last.cash_end)} / {fmtBRL(last.debts_end)} / {fmtBRL(last.equity_end)}</dd></div>
            </dl>
          </>
        )}
      </section>
      <Suspense fallback={<div className="card muted">Carregando gráficos…</div>}>
        <div className="grid-2"><RevenueCostChart months={d.months} /><NetResultChart months={d.months} /></div>
      </Suspense>

      <section className="card">
        <div className="row"><h2>Funcionários</h2><button className="btn small ghost" onClick={() => setModal("hire")}>+ Contratar</button></div>
        <div className="table-wrap"><table>
          <thead><tr><th>Cargo</th><th>Nível</th><th className="r">Salário</th><th className="r">Custo total</th><th>Situação</th><th /></tr></thead>
          <tbody>{d.employees.map((e) => (
            <tr key={e.id} className={e.status === "ACTIVE" ? "" : "muted"}>
              <td>{e.role_label}</td><td>{LEVEL_LABEL[e.level]}</td><td className="r num">{fmtBRL(e.salary)}</td><td className="r num">{fmtBRL(e.total_cost)}</td>
              <td>{e.status === "ACTIVE" ? `desde ${fmtMonth(e.hired_on)}` : `desligado em ${e.terminated_on ? fmtMonth(e.terminated_on) : ""}`}</td>
              <td className="r">{e.status === "ACTIVE" && <button className="link-btn" onClick={() => window.confirm(`Desligar ${e.role_label}? A rescisão custa um salário.`) && act(() => api.coFire(c.id, e.id), "Funcionário desligado.")}>desligar</button>}</td>
            </tr>
          ))}</tbody>
        </table></div>
      </section>

      {d.inventory.length > 0 && (
        <section className="card">
          <h2>Estoque</h2>
          <div className="table-wrap"><table>
            <thead><tr><th>Item</th><th>Fornecedor</th><th className="r">Quantidade</th><th className="r">Custo médio</th><th className="r">Mínimo</th><th className="r">Consumo estimado/mês</th><th /></tr></thead>
            <tbody>{d.inventory.map((i) => (
              <tr key={i.id}>
                <td><b>{i.name}</b> {i.low && <span className="tag tone-warn">baixo</span>}</td><td className="muted">{i.supplier}</td>
                <td className="r num">{i.quantity} {i.unit}</td><td className="r num">{fmtBRL(i.unit_cost)}</td><td className="r num">{i.min_quantity}</td><td className="r num">{i.monthly_consumption_est}</td>
                <td className="r"><button className="link-btn" onClick={() => { const q = window.prompt(`Quantidade de ${i.name} a comprar (${i.unit})`); if (q) void act(() => api.coStock(c.id, i.id, parseMoneyInput(q)), "Estoque comprado."); }}>comprar</button></td>
              </tr>
            ))}</tbody>
          </table></div>
          <p className="muted small">Reposição automática {c.auto_restock ? "ligada" : "desligada"}: no fechamento, a empresa compra o que falta (se houver caixa). Sem estoque, as vendas param.</p>
        </section>
      )}

      <section className="card">
        <div className="row"><h2>Instalações e custos</h2><button className="btn small ghost" onClick={() => setModal("lease")}>Alterar instalações</button></div>
        <dl className="facts">
          <div><dt>Instalações</dt><dd>{d.lease ? `${d.lease.name} — ${fmtBRL(d.lease.monthly_rent)}/mês (${d.lease.kind === "EXTERNAL" ? "alugado de terceiros" : d.lease.kind === "OWN_GOOD" ? "imóvel seu, alugado à empresa" : "imóvel da empresa"})` : "nenhuma"}</dd></div>
          {d.costs.map((x) => <div key={x.id}><dt>{CO_COST_LABEL[x.kind] ?? x.kind}</dt><dd className="num">{fmtBRL(x.amount)}/mês{x.active ? "" : " (inativo)"}</dd></div>)}
        </dl>
      </section>

      <section className="card">
        <h2>Expansão</h2>
        <div className="goods-grid">{EXPANSIONS.map(([k, label, text]) => (
          <div key={k} className="card good-card"><b>{label}</b><span className="muted small">{text}</span>
            <span className="num good-value">{fmtBRL(d.expansion_costs[k])}</span>
            <button className="btn small ghost" onClick={() => window.confirm(`${label} por ${fmtBRL(d.expansion_costs[k])}? Não há garantia de mais lucro.`) && act(() => api.coExpand(c.id, k), `${label}: concluído.`)}>Contratar</button></div>
        ))}</div>
      </section>

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
            <thead><tr><th>Mês</th><th className="r">Vendas</th><th className="r">Receita</th><th className="r">Resultado líquido</th><th className="r">Caixa</th><th className="r">Patrimônio</th></tr></thead>
            <tbody>{d.months.map((m) => <tr key={m.ref_month}><td>{fmtMonth(m.ref_month)}</td><td className="r num">{m.units_sold}{m.stockout ? " ⚠" : ""}</td><td className="r num">{fmtBRL(m.revenue)}</td>
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
      {modal === "hire" && <HireModal d={d} onClose={() => setModal(null)} onDone={(x) => done(x, "Funcionário contratado.")} />}
      {modal === "loan" && <LoanModal d={d} onClose={() => setModal(null)} onDone={(x) => done(x, "Empréstimo contratado.")} />}
      {modal === "lease" && <LeaseModal d={d} goods={personalGoods} onClose={() => setModal(null)} onDone={(x) => done(x, "Instalações atualizadas.")} />}
    </div>
  );
}

function SettingsForm({ d, onSave }: { d: CompanyDetail; onSave: (b: { price?: string; owner_salary?: string; auto_restock?: boolean }) => void }) {
  const [price, setPrice] = useState(d.company.price);
  const [salary, setSalary] = useState(d.company.owner_salary);
  const [restock, setRestock] = useState(d.company.auto_restock);
  useEffect(() => { setPrice(d.company.price); setSalary(d.company.owner_salary); setRestock(d.company.auto_restock); }, [d.company.price, d.company.owner_salary, d.company.auto_restock]);
  return (
    <form className="row-gap" style={{ maxWidth: "none", flexWrap: "wrap", marginTop: 12 }} onSubmit={(e) => { e.preventDefault(); onSave({ price: parseMoneyInput(price), owner_salary: parseMoneyInput(salary), auto_restock: restock }); }}>
      <label>Preço de venda (R$)<input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} /></label>
      <label>Pró-labore (R$/mês)<input inputMode="decimal" value={salary} onChange={(e) => setSalary(e.target.value)} /></label>
      <label className="check"><input type="checkbox" checked={restock} onChange={(e) => setRestock(e.target.checked)} />Reposição automática de estoque</label>
      <button className="btn small ghost">Salvar</button>
    </form>
  );
}
