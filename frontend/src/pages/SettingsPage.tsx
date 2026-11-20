import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { sim, type AccountCategory } from "../services/sim";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");

/** Configurações da conta: valem para todas as partidas (atuais e futuras). */
export function SettingsPage() {
  const [cats, setCats] = useState<AccountCategory[] | null>(null);
  const [kind, setKind] = useState<"EXPENSE" | "INCOME">("EXPENSE");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const load = () => sim.accountCategories().then(setCats).catch((e) => setErr(errMsg(e)));
  useEffect(() => { void load(); }, []);
  const run = async (fn: () => Promise<unknown>) => { setErr(null); try { await fn(); await load(); } catch (e) { setErr(errMsg(e)); } };
  if (!cats) return err ? <div className="alert">{err}</div> : <div className="muted">Carregando…</div>;
  const Block = ({ k, title, hint }: { k: "EXPENSE" | "INCOME"; title: string; hint: string }) => (
    <section className="panel stack"><h2>{title}</h2><p className="muted small" style={{ margin: 0 }}>{hint}</p>
      <ul className="list-plain">{cats.filter((c) => c.kind === k).map((c) => (
        <li key={c.id}>
          <input defaultValue={c.name} aria-label={`Nome da categoria ${c.name}`} maxLength={60} style={{ maxWidth: 260 }}
            onBlur={(e) => { const v = e.target.value.trim(); if (v && v !== c.name) void run(() => sim.patchAccountCategory(c.id, { name: v })); }} />
          <button className={`btn small ${c.active ? "primary" : "ghost"}`} onClick={() => void run(() => sim.patchAccountCategory(c.id, { active: !c.active }))}>{c.active ? "✅ Ativada" : "⏸ Desativada"}</button>
        </li>))}</ul></section>
  );
  return (
    <div className="hub">
      <Link to="/" className="back">⬅ Voltar</Link>
      <section className="hero"><div><h1>⚙ Configurações da conta</h1><p>As escolhas daqui valem para todas as suas partidas — as que você já tem e as próximas.</p></div></section>
      {err && <div className="alert">{err}</div>}
      <Block k="EXPENSE" title="🛒 Categorias de despesas" hint="Desative as que você não quer usar: elas deixam de aparecer ao lançar despesas. Dá para renomear também." />
      <Block k="INCOME" title="💼 Categorias de receitas" hint="Mesma ideia, para o dinheiro que entra." />
      <section className="panel stack"><h2>➕ Nova categoria</h2>
        <form className="row" onSubmit={(e) => { e.preventDefault(); if (name.trim()) void run(async () => { await sim.addAccountCategory(name.trim(), kind); setName(""); }); }}>
          <input placeholder="Nome (ex.: Pets)" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
          <select value={kind} onChange={(e) => setKind(e.target.value as "EXPENSE" | "INCOME")}><option value="EXPENSE">Despesa</option><option value="INCOME">Receita</option></select>
          <button className="btn primary" type="submit">Criar</button></form></section>
    </div>
  );
}
