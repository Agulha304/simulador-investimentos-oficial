import { useState, type FormEvent } from "react";
import {
  api, type BudgetCategory, type BudgetItem, type ClosePreview, type FlowKind, type Frequency, type MonthSummary,
} from "../services/api";
import { FREQUENCY_LABEL, fmtBRL, fmtMonth, parseMoneyInput, trend } from "../lib/format";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");

function Modal({ title, onClose, onSubmit, children }: {
  title: string; onClose: () => void; onSubmit: (e: FormEvent) => void; children: React.ReactNode;
}) {
  return (
    <div className="modal-back" onMouseDown={onClose}>
      <form className="card modal" onMouseDown={(e) => e.stopPropagation()} onSubmit={onSubmit}>
        <div className="row"><h2>{title}</h2><button type="button" className="link-btn" onClick={onClose}>fechar ✕</button></div>
        {children}
      </form>
    </div>
  );
}

/** Criar ou editar um item planejado (opcionalmente recorrente). */
export function ItemModal({ item, categories, onClose, onSaved }: {
  item: BudgetItem | null; categories: BudgetCategory[]; onClose: () => void; onSaved: (m: MonthSummary) => void;
}) {
  const editing = item != null;
  const [kind, setKind] = useState<FlowKind>(item?.kind ?? "EXPENSE");
  const usable = categories.filter((c) => c.kind === kind && (c.active || c.id === item?.category_id));
  const [name, setName] = useState(item?.name ?? "");
  const [categoryId, setCategoryId] = useState<number | "">(item?.category_id ?? "");
  const [amount, setAmount] = useState(item ? item.planned_amount : "");
  const [recurring, setRecurring] = useState(item?.recurring ?? true);
  const [frequency, setFrequency] = useState<Frequency>(item?.frequency ?? "MONTHLY");
  const [endMonth, setEndMonth] = useState(item?.end_month?.slice(0, 7) ?? "");
  const [future, setFuture] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const catId: number | "" = categoryId === "" || !usable.some((c) => c.id === categoryId) ? (usable[0]?.id ?? "") : categoryId;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (catId === "") return setMsg("Escolha uma categoria.");
    setBusy(true); setMsg(null);
    try {
      const planned = parseMoneyInput(amount);
      const m = editing
        ? await api.budgetUpdateItem(item.id, {
            name, category_id: catId, planned_amount: planned, apply_to_future: future,
            ...(item.recurring ? { frequency, end_month: endMonth || null, clear_end_month: !endMonth } : {}),
          })
        : await api.budgetAddItem({ name, kind, category_id: catId, planned_amount: planned, recurring, frequency, end_month: endMonth || null });
      onSaved(m);
    } catch (err) { setMsg(errMsg(err)); } finally { setBusy(false); }
  }

  return (
    <Modal title={editing ? "Editar item" : "Novo item do orçamento"} onClose={onClose} onSubmit={submit}>
      {!editing && (
        <div className="seg" role="group" aria-label="Tipo">
          <button type="button" className={kind === "EXPENSE" ? "on sell" : ""} onClick={() => { setKind("EXPENSE"); setCategoryId(""); }}>Despesa</button>
          <button type="button" className={kind === "INCOME" ? "on buy" : ""} onClick={() => { setKind("INCOME"); setCategoryId(""); }}>Receita</button>
        </div>
      )}
      <label>Nome<input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required /></label>
      <label>Categoria
        <select value={catId} onChange={(e) => setCategoryId(Number(e.target.value))}>
          {usable.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </label>
      <label>Valor previsto (R$)<input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required /></label>
      {!editing && (
        <label className="check"><input type="checkbox" checked={recurring} onChange={(e) => setRecurring(e.target.checked)} />
          Recorrente (entra automaticamente nos próximos meses)</label>
      )}
      {(editing ? item.recurring : recurring) && (
        <>
          <label>Frequência
            <select value={frequency} onChange={(e) => setFrequency(e.target.value as Frequency)}>
              {Object.entries(FREQUENCY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label>Último mês (opcional)<input type="month" value={endMonth} onChange={(e) => setEndMonth(e.target.value)} /></label>
        </>
      )}
      {editing && item.recurring && (
        <label className="check"><input type="checkbox" checked={future} onChange={(e) => setFuture(e.target.checked)} />
          Aplicar o novo valor aos próximos meses (os meses passados não mudam)</label>
      )}
      {msg && <div className="alert">{msg}</div>}
      <button className="btn primary" disabled={busy}>{busy ? "Salvando…" : "Salvar"}</button>
    </Modal>
  );
}

/** Registrar uma receita/despesa efetiva (é aqui que o saldo muda). */
export function EntryModal({ month, categories, preset, onClose, onSaved }: {
  month: MonthSummary; categories: BudgetCategory[]; preset: BudgetItem | null; onClose: () => void; onSaved: () => void;
}) {
  const [kind, setKind] = useState<FlowKind>(preset?.kind ?? "EXPENSE");
  const [itemId, setItemId] = useState<number | "">(preset?.id ?? "");
  const items = month.items.filter((i) => i.kind === kind);
  const usable = categories.filter((c) => c.kind === kind && c.active);
  const [categoryId, setCategoryId] = useState<number | "">(preset?.category_id ?? "");
  const [description, setDescription] = useState(preset?.name ?? "");
  const [amount, setAmount] = useState(preset ? preset.remaining.replace(/^-.*/, "") : "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const item = items.find((i) => i.id === itemId);
  const catId: number | "" = item ? item.category_id : categoryId === "" || !usable.some((c) => c.id === categoryId) ? (usable[0]?.id ?? "") : categoryId;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try {
      await api.budgetCreateEntry({
        kind, amount: parseMoneyInput(amount), description,
        ...(item ? { budget_item_id: item.id } : { category_id: catId === "" ? undefined : catId }),
      });
      onSaved();
    } catch (err) { setMsg(errMsg(err)); } finally { setBusy(false); }
  }

  return (
    <Modal title="Registrar movimentação" onClose={onClose} onSubmit={submit}>
      <p className="muted small" style={{ margin: 0 }}>
        Isto muda o saldo agora. Valores apenas previstos no orçamento não descontam nada até serem registrados ou lançados no fechamento do mês.
      </p>
      <div className="seg" role="group" aria-label="Tipo">
        <button type="button" className={kind === "EXPENSE" ? "on sell" : ""} onClick={() => { setKind("EXPENSE"); setItemId(""); setCategoryId(""); }}>Despesa</button>
        <button type="button" className={kind === "INCOME" ? "on buy" : ""} onClick={() => { setKind("INCOME"); setItemId(""); setCategoryId(""); }}>Receita</button>
      </div>
      <label>Item do orçamento (opcional)
        <select value={itemId} onChange={(e) => { const v = e.target.value; setItemId(v ? Number(v) : ""); const it = items.find((i) => i.id === Number(v)); if (it) setDescription(it.name); }}>
          <option value="">Sem item (movimentação avulsa)</option>
          {items.map((i) => <option key={i.id} value={i.id}>{i.name} — previsto {fmtBRL(i.planned_amount)}</option>)}
        </select>
      </label>
      {!item && (
        <label>Categoria
          <select value={catId} onChange={(e) => setCategoryId(Number(e.target.value))}>
            {usable.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
      )}
      <label>Descrição<input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={200} /></label>
      <label>Valor (R$)<input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required /></label>
      {msg && <div className="alert">{msg}</div>}
      <button className="btn primary" disabled={busy}>{busy ? "Registrando…" : "Registrar"}</button>
    </Modal>
  );
}

/** Resumo e confirmação do fechamento. Nada acontece antes do clique em "Confirmar". */
export function CloseModal({ preview, onClose, onClosed }: { preview: ClosePreview; onClose: () => void; onClosed: () => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try { await api.budgetClose(preview.ref_month.slice(0, 7)); onClosed(); }
    catch (err) { setMsg(errMsg(err)); setBusy(false); }
  }

  return (
    <Modal title={`Fechar ${fmtMonth(preview.ref_month)}`} onClose={onClose} onSubmit={submit}>
      <dl className="facts">
        <div><dt>Receitas totais</dt><dd className="num tone-up">{fmtBRL(preview.income)}</dd></div>
        <div><dt>Despesas totais</dt><dd className="num">{fmtBRL(preview.expense)}</dd></div>
        <div><dt>Investimentos realizados</dt><dd className="num">{fmtBRL(preview.invested)}</dd></div>
        <div><dt>Resultado financeiro</dt><dd className={`num tone-${trend(preview.result)}`}>{fmtBRL(preview.result)}</dd></div>
        <div><dt>Saldo que será transportado</dt><dd className="num"><b>{fmtBRL(preview.carried_balance)}</b></dd></div>
      </dl>
      {preview.pending.length > 0 && (
        <p className="muted small" style={{ margin: 0 }}>
          Serão lançados agora (recorrentes ainda não registrados): {preview.pending.join(", ")}.
        </p>
      )}
      <p className="muted small" style={{ margin: 0 }}>
        Depois de confirmar, {fmtMonth(preview.ref_month)} fica registrado no histórico e não pode mais ser alterado.
        O próximo mês será {fmtMonth(preview.next_month)}.
      </p>
      {!preview.can_close && (
        <div className="alert">Saldo insuficiente para as despesas recorrentes: faltam {fmtBRL(preview.shortfall)}. Ajuste o orçamento ou adicione saldo antes de fechar.</div>
      )}
      {preview.can_close && Number(preview.overdraft_needed ?? 0) > 0 && (
        <div className={preview.bankruptcy_risk ? "alert" : "notice"}>
          {preview.bankruptcy_risk ? "🚨 " : "💳 "}<b>Você vai fechar o mês no negativo.</b> Faltam {fmtBRL(preview.shortfall)} para pagar as contas: o <b>cheque especial</b> cobre a diferença, com juros altos.
          {preview.bankruptcy_risk ? <> Isso passa do limite de {fmtBRL(preview.overdraft_limit ?? "100000")} de saldo negativo e leva à <b>FALÊNCIA</b> (fim de jogo).</> : <> Se o saldo negativo passar de {fmtBRL(preview.overdraft_limit ?? "100000")}, você vai à falência. O dinheiro que sobrar nos próximos meses paga o cheque especial primeiro.</>}
        </div>
      )}
      {msg && <div className="alert">{msg}</div>}
      <div className="row-gap">
        <button type="button" className="btn ghost" onClick={onClose}>Cancelar</button>
        <button className={`btn ${preview.bankruptcy_risk ? "danger" : "primary"}`} disabled={busy || !preview.can_close}>{busy ? "Fechando…" : Number(preview.overdraft_needed ?? 0) > 0 ? (preview.bankruptcy_risk ? "Avançar mesmo assim (falência)" : "Avançar no negativo") : "Confirmar e avançar o mês"}</button>
      </div>
    </Modal>
  );
}
