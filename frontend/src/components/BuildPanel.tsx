import { useEffect, useState } from "react";
import { api, type BuildCatalog, type GoodDetail } from "../services/api";
import { fmtBRL } from "../lib/format";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Erro inesperado");

/** Construir um imóvel (terreno + obra à vista): 3 a 6 meses de obra; só depois dá para alugar, usar ou vender. */
export function BuildPanel({ onBuilt }: { onBuilt: (g: GoodDetail) => void }) {
  const [cat, setCat] = useState<BuildCatalog | null>(null);
  const [city, setCity] = useState("bh");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.buildCatalog().then(setCat).catch((e) => setError(errMsg(e))); }, []);
  if (!cat) return <div className="muted">{error ?? "Carregando projetos…"}</div>;
  async function build(plan: string) {
    if (!window.confirm("Contratar esta obra? O valor total é debitado agora e o imóvel só fica pronto no prazo.")) return;
    setBusy(plan); setError(null);
    try { onBuilt(await api.buildGood(plan, city)); } catch (e) { setError(errMsg(e)); } finally { setBusy(null); }
  }
  return (
    <section className="card">
      <h2>Construir</h2>
      <p className="muted small">Construir leva de 3 a 6 meses conforme o projeto (comprar um imóvel pronto leva {cat.closing_months.cash} mês à vista e {cat.closing_months.financed} financiado, para a escritura). Terreno e obra são pagos à vista.</p>
      <label>Cidade <select value={city} onChange={(e) => setCity(e.target.value)}>{cat.cities.map((c) => <option key={c.key} value={c.key}>{c.name}</option>)}</select></label>
      {error && <div className="alert">{error}</div>}
      <div className="goods-grid">{cat.plans.map((p) => {
        const q = p.quotes[city];
        return (
          <div key={p.key} className="card good-card">
            <b>{p.name}</b>
            <span className="num good-value">{fmtBRL(q.total)}</span>
            <span className="muted small">Terreno {fmtBRL(q.land)} + obra {fmtBRL(q.construction)} · {p.months} meses</span>
            <button className="btn small primary" disabled={busy === p.key} onClick={() => void build(p.key)}>{busy === p.key ? "Contratando…" : "Construir"}</button>
          </div>);
      })}</div>
    </section>
  );
}
