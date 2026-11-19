import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { CloseModal, EntryModal, ItemModal } from "../components/BudgetModals";
import { StatCard } from "../components/StatCard";
import {
  api, type BudgetCategory, type BudgetItem, type BudgetOverview, type FlowKind, type LedgerEntryOut, type MonthRow, type MonthSummary,
} from "../services/api";
import { FREQUENCY_LABEL, ORIGIN_LABEL, fmtBRL, fmtDay, fmtMonth, fmtMonthShort, parseMoneyInput, trend } from "../lib/format";

const charts = import("../components/charts/BudgetCharts");
const PlannedVsActualChart = lazy(() => charts.then((m) => ({ default: m.PlannedVsActualChart })));
const IncomeExpenseChart = lazy(() => charts.then((m) => ({ default: m.IncomeExpenseChart })));
const BalanceChart = lazy(() => charts.then((m) => ({ default: m.BalanceChart })));

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");
type Tab = "month" | "history";

export function BudgetPage() {
  const [tab, setTab] = useState<Tab>("month");
  const [ov, setOv] = useState<BudgetOverview | null>(null);
  const [cats, setCats] = useState<BudgetCategory[]>([]);
  const [entries, setEntries] = useState<LedgerEntryOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [itemModal, setItemModal] = useState<{ item: BudgetItem | null } | null>(null);
  const [entryModal, setEntryModal] = useState<{ preset: BudgetItem | null } | null>(null);
  const [closing, setClosing] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [o, c, e] = await Promise.all([api.budgetOverview(), api.budgetCategories(), api.budgetEntries()]);
      setOv(o); setCats(c); setEntries(e); setError(null);
    } catch (err) { setError(errMsg(err)); }
  }, []);
  useEffect(() => { void reload(); }, [reload]);

  if (error && !ov) return <div className="alert">Não foi possível carregar o orçamento: {error}</div>;
  if (!ov) return <div className="muted">Carregando orçamento…</div>;
  const m = ov.month;

  async function act(fn: () => Promise<unknown>, okMsg?: string) {
    try { await fn(); setNotice(okMsg ?? null); setError(null); await reload(); }
    catch (err) { setError(errMsg(err)); }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Orçamento</h1>
          <p className="muted">{ov.account.name} · mês do simulador: <b>{fmtMonth(m.ref_month)}</b></p>
        </div>
        <button className="btn primary" onClick={() => setClosing(true)}>Fechar mês e avançar ▸</button>
      </header>

      {error && <div className="alert">{error}</div>}
      {notice && <div className="ok">{notice}</div>}

      <div className="seg compact tabs">
        <button className={tab === "month" ? "on" : ""} onClick={() => setTab("month")}>Mês atual</button>
        <button className={tab === "history" ? "on" : ""} onClick={() => setTab("history")}>Histórico</button>
      </div>

      {tab === "month" && (
        <>
          <section className="stats-grid">
            <StatCard label="Saldo disponível" value={fmtBRL(ov.account.balance)} emphasis />
            <StatCard label="Receitas do mês" value={fmtBRL(m.realized_income)} sub={`previsto ${fmtBRL(m.forecast_income)}`} tone="up" />
            <StatCard label="Despesas do mês" value={fmtBRL(m.realized_expense)} sub={`previsto ${fmtBRL(m.forecast_expense)}`} />
            <StatCard label="Investimentos" value={fmtBRL(m.invested)} sub={`planejado ${fmtBRL(m.planned_investment)}`} />
            <StatCard label="Saldo restante (projeção)" value={fmtBRL(m.projected_closing_balance)}
              sub={`após investir: ${fmtBRL(m.free_after_investment)}`} tone={trend(m.free_after_investment) === "down" ? "down" : "neutral"} />
          </section>

          <InvestmentPlan month={m} onSave={(v) => act(() => api.budgetSetInvestment(v), "Investimento planejado atualizado.")} />

          <BudgetTable
            month={m}
            onAdd={() => setItemModal({ item: null })}
            onEdit={(item) => setItemModal({ item })}
            onRegister={(item) => setEntryModal({ preset: item })}
            onRemove={(item) => {
              const stop = item.recurring ? window.confirm("Este item é recorrente. OK = remover também dos próximos meses. Cancelar = remover só deste mês.") : false;
              void act(() => api.budgetDeleteItem(item.id, stop), "Item removido.");
            }}
            onExample={() => act(() => api.budgetExample(), "Modelo de exemplo adicionado. Edite os valores como quiser.")}
          />

          <Suspense fallback={<div className="card muted">Carregando gráfico…</div>}>
            <PlannedVsActualChart rows={m.by_category} />
          </Suspense>

          <section className="card">
            <div className="row"><h2>Movimentações de {fmtMonth(m.ref_month)}</h2>
              <button className="btn small primary" onClick={() => setEntryModal({ preset: null })}>+ Registrar movimentação</button>
            </div>
            <EntriesTable entries={entries} canReverse onReverse={(e) => act(() => api.budgetReverseEntry(e.id), "Estorno registrado.")} />
          </section>

          <CategoriesCard cats={cats} onChange={reload} onError={setError} />
        </>
      )}

      {tab === "history" && <HistoryTab key={m.ref_month} />}

      {itemModal && <ItemModal item={itemModal.item} categories={cats} onClose={() => setItemModal(null)}
        onSaved={() => { setItemModal(null); setNotice("Orçamento atualizado."); void reload(); }} />}
      {entryModal && <EntryModal month={m} categories={cats} preset={entryModal.preset} onClose={() => setEntryModal(null)}
        onSaved={() => { setEntryModal(null); setNotice("Movimentação registrada."); void reload(); }} />}
      {closing && <CloseModal preview={ov.close} onClose={() => setClosing(false)}
        onClosed={() => { setClosing(false); setNotice(`${fmtMonth(m.ref_month)} fechado. Bem-vindo a ${fmtMonth(ov.close.next_month)}!`); void reload(); }} />}
    </div>
  );
}

function InvestmentPlan({ month, onSave }: { month: MonthSummary; onSave: (v: string) => void }) {
  const [v, setV] = useState(month.planned_investment);
  useEffect(() => setV(month.planned_investment), [month.planned_investment]);
  return (
    <form className="card inline-form" onSubmit={(e) => { e.preventDefault(); onSave(parseMoneyInput(v)); }}>
      <p className="muted small">Quanto pretende investir neste mês (apenas um plano: os investimentos reais continuam sendo feitos em Mercado e Renda Fixa).</p>
      <div className="row-gap">
        <input inputMode="decimal" value={v} onChange={(e) => setV(e.target.value)} aria-label="Investimento planejado (R$)" />
        <button className="btn small ghost">Salvar plano</button>
      </div>
    </form>
  );
}

function BudgetTable({ month, onAdd, onEdit, onRegister, onRemove, onExample }: {
  month: MonthSummary; onAdd: () => void; onEdit: (i: BudgetItem) => void; onRegister: (i: BudgetItem) => void;
  onRemove: (i: BudgetItem) => void; onExample: () => void;
}) {
  const groups: { kind: FlowKind; title: string }[] = [{ kind: "INCOME", title: "Receitas" }, { kind: "EXPENSE", title: "Despesas" }];
  return (
    <section className="card">
      <div className="row">
        <h2>Orçamento de {fmtMonth(month.ref_month)}</h2>
        <button className="btn small primary" onClick={onAdd}>+ Adicionar item</button>
      </div>
      {month.items.length === 0 ? (
        <div className="empty">
          Seu orçamento está vazio. Adicione receitas e despesas ou comece com um modelo de exemplo (você pode alterar tudo depois).
          <div style={{ marginTop: 12 }}><button className="btn small ghost" onClick={onExample}>Começar com modelo de exemplo</button></div>
        </div>
      ) : groups.map(({ kind, title }) => {
        const rows = month.items.filter((i) => i.kind === kind);
        if (!rows.length) return null;
        return (
          <div className="table-wrap" key={kind} style={{ marginBottom: 14 }}>
            <table>
              <thead><tr>
                <th>{title}</th><th>Categoria</th><th>Frequência</th>
                <th className="r">Previsto</th><th className="r">Realizado</th><th className="r">Restante</th><th />
              </tr></thead>
              <tbody>{rows.map((i) => (
                <tr key={i.id}>
                  <td><b>{i.name}</b></td>
                  <td className="muted">{i.category_name}</td>
                  <td>{i.recurring ? <span className="tag">{FREQUENCY_LABEL[i.frequency ?? "MONTHLY"]}</span> : <span className="muted small">este mês</span>}</td>
                  <td className="r num">{fmtBRL(i.planned_amount)}</td>
                  <td className="r num">{fmtBRL(i.realized)}</td>
                  <td className={`r num ${Number(i.remaining) < 0 ? "tone-warn" : ""}`}>{fmtBRL(i.remaining)}</td>
                  <td className="r">
                    <button className="link-btn" onClick={() => onRegister(i)}>registrar</button>{" · "}
                    <button className="link-btn" onClick={() => onEdit(i)}>editar</button>
                    {i.entry_count === 0 && <>{" · "}<button className="link-btn" onClick={() => onRemove(i)}>remover</button></>}
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        );
      })}
      {month.items.length > 0 && (
        <div className="muted small row">
          <span>Previsto: receitas {fmtBRL(month.planned_income)} · despesas {fmtBRL(month.planned_expense)}</span>
          <span>Itens recorrentes ainda não registrados serão lançados no fechamento do mês.</span>
        </div>
      )}
    </section>
  );
}

function EntriesTable({ entries, canReverse, onReverse }: { entries: LedgerEntryOut[]; canReverse: boolean; onReverse?: (e: LedgerEntryOut) => void }) {
  if (!entries.length) return <div className="empty">Nenhuma movimentação registrada neste mês.</div>;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Data</th><th>Descrição</th><th>Categoria</th><th>Origem</th><th className="r">Valor</th><th /></tr></thead>
        <tbody>{entries.map((e) => {
          const sign = (e.kind === "INCOME") !== (e.origin === "REVERSAL");
          return (
            <tr key={e.id} className={e.reversed ? "muted" : ""}>
              <td>{fmtDay(e.entry_date)}</td>
              <td>{e.description}{e.reversed && <span className="tag" style={{ marginLeft: 8 }}>estornada</span>}</td>
              <td className="muted">{e.category_name ?? "—"}</td>
              <td><span className="tag">{ORIGIN_LABEL[e.origin] ?? e.origin}</span></td>
              <td className={`r num ${sign ? "tone-up" : ""}`}>{sign ? "+ " : "− "}{fmtBRL(e.amount)}</td>
              <td className="r">{canReverse && onReverse && e.origin !== "REVERSAL" && !e.reversed && <button className="link-btn" onClick={() => onReverse(e)}>estornar</button>}</td>
            </tr>
          );
        })}</tbody>
      </table>
    </div>
  );
}

function CategoriesCard({ cats, onChange, onError }: { cats: BudgetCategory[]; onChange: () => void; onError: (m: string | null) => void }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<FlowKind>("EXPENSE");
  async function run(fn: () => Promise<unknown>) {
    try { await fn(); onError(null); onChange(); } catch (e) { onError(errMsg(e)); }
  }
  return (
    <section className="card">
      <h2>Categorias</h2>
      <p className="muted small">Renomeie, desative ou crie categorias. Categorias desativadas não aparecem em novos itens, mas o histórico é preservado.</p>
      {(["EXPENSE", "INCOME"] as FlowKind[]).map((k) => (
        <div key={k} style={{ marginBottom: 10 }}>
          <div className="stat-label" style={{ marginBottom: 6 }}>{k === "EXPENSE" ? "Despesas" : "Receitas"}</div>
          <div className="chips">
            {cats.filter((c) => c.kind === k).map((c) => (
              <span key={c.id} className={`chip${c.active ? "" : " off"}`}>
                <input defaultValue={c.name} aria-label={`Nome da categoria ${c.name}`} maxLength={60}
                  onBlur={(e) => { const v = e.target.value.trim(); if (v && v !== c.name) void run(() => api.budgetUpdateCategory(c.id, { name: v })); else e.target.value = c.name; }} />
                <button type="button" className="link-btn" title={c.active ? "Desativar" : "Reativar"}
                  onClick={() => run(() => api.budgetUpdateCategory(c.id, { active: !c.active }))}>{c.active ? "desativar" : "reativar"}</button>
              </span>
            ))}
          </div>
        </div>
      ))}
      <form className="row-gap" onSubmit={(e) => { e.preventDefault(); if (name.trim()) void run(async () => { await api.budgetCreateCategory(name.trim(), kind); setName(""); }); }}>
        <input placeholder="Nova categoria" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
        <select value={kind} onChange={(e) => setKind(e.target.value as FlowKind)} aria-label="Tipo da categoria">
          <option value="EXPENSE">Despesa</option><option value="INCOME">Receita</option>
        </select>
        <button className="btn small ghost">Adicionar</button>
      </form>
    </section>
  );
}

function HistoryTab() {
  const [months, setMonths] = useState<MonthRow[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ summary: MonthSummary; entries: LedgerEntryOut[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.budgetMonths().then(setMonths).catch((e) => setError(errMsg(e))); }, []);
  useEffect(() => {
    if (!open) { setDetail(null); return; }
    const ref = open.slice(0, 7);
    Promise.all([api.budgetMonth(ref), api.budgetEntries(ref)])
      .then(([summary, entries]) => setDetail({ summary, entries })).catch((e) => setError(errMsg(e)));
  }, [open]);

  if (error) return <div className="alert">{error}</div>;
  if (!months) return <div className="muted">Carregando histórico…</div>;

  return (
    <>
      <Suspense fallback={<div className="card muted">Carregando gráficos…</div>}>
        <div className="grid-2"><IncomeExpenseChart months={months} /><BalanceChart months={months} /></div>
      </Suspense>
      <section className="card">
        <h2>Meses</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Mês</th><th>Situação</th><th className="r">Receitas</th><th className="r">Despesas</th><th className="r">Resultado</th>
              <th className="r">Investido</th><th className="r">Saldo final</th><th /></tr></thead>
            <tbody>{months.map((r) => (
              <tr key={r.ref_month}>
                <td><b>{fmtMonthShort(r.ref_month)}</b></td>
                <td><span className="tag">{r.status === "OPEN" ? "Em andamento" : "Fechado"}</span></td>
                <td className="r num">{fmtBRL(r.income)}</td>
                <td className="r num">{fmtBRL(r.expense)}</td>
                <td className={`r num tone-${trend(r.result)}`}>{fmtBRL(r.result)}</td>
                <td className="r num">{fmtBRL(r.invested)}</td>
                <td className="r num">{r.closing_balance ? fmtBRL(r.closing_balance) : "—"}</td>
                <td className="r"><button className="link-btn" onClick={() => setOpen(open === r.ref_month ? null : r.ref_month)}>{open === r.ref_month ? "ocultar" : "detalhes"}</button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>
      {open && detail && (
        <section className="card">
          <h2>{fmtMonth(open)}</h2>
          <div className="table-wrap" style={{ marginBottom: 14 }}>
            <table>
              <thead><tr><th>Categoria</th><th>Tipo</th><th className="r">Previsto</th><th className="r">Realizado</th></tr></thead>
              <tbody>{detail.summary.by_category.map((c, i) => (
                <tr key={i}><td>{c.category_name}</td><td className="muted">{c.kind === "INCOME" ? "Receita" : "Despesa"}</td>
                  <td className="r num">{fmtBRL(c.planned)}</td><td className="r num">{fmtBRL(c.realized)}</td></tr>
              ))}</tbody>
            </table>
          </div>
          <EntriesTable entries={detail.entries} canReverse={false} />
        </section>
      )}
    </>
  );
}
