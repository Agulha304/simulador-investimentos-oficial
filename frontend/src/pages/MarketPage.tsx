import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Asset, type QuoteBrief } from "../services/api";
import { fmtBRL, fmtMoney, fmtPct, trend } from "../lib/format";

const GROUPS = [
  { id: "stock-br", label: "Ações Brasil", params: { asset_class: "STOCK", country: "BR" } },
  { id: "stock-us", label: "Ações EUA", params: { asset_class: "STOCK", country: "US" } },
  { id: "etf-br", label: "ETFs Brasil", params: { asset_class: "ETF", country: "BR" } },
  { id: "etf-us", label: "ETFs EUA", params: { asset_class: "ETF", country: "US" } },
  { id: "fii", label: "FIIs", params: { asset_class: "FII" } },
  { id: "reit", label: "REITs", params: { asset_class: "REIT" } },
  { id: "crypto", label: "Criptomoedas", params: { asset_class: "CRYPTO" } },
];

export function MarketPage() {
  const [group, setGroup] = useState(GROUPS[0]);
  const [assets, setAssets] = useState<Asset[] | null>(null);
  const [quotes, setQuotes] = useState<Record<number, QuoteBrief>>({});
  const [loadingQuotes, setLoadingQuotes] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setAssets(null); setQuotes({}); setError(null);
    api.assets({ ...group.params, limit: 40 })
      .then(async (list) => {
        if (cancelled) return;
        setAssets(list);
        setLoadingQuotes(true);
        try {
          const q = await api.quotes(list.map((a) => a.id));
          if (!cancelled) setQuotes(Object.fromEntries(q.map((x) => [x.asset_id, x])));
        } finally { if (!cancelled) setLoadingQuotes(false); }
      })
      .catch((e: Error) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [group]);

  return (
    <div className="page">
      <header className="page-head"><div><h1>Mercado</h1><p className="muted">Explore os ativos disponíveis por classe.</p></div></header>
      <div className="chart-toolbar">
        {GROUPS.map((g) => <button key={g.id} className={`tool${group.id === g.id ? " on" : ""}`} onClick={() => setGroup(g)}>{g.label}</button>)}
      </div>
      {error && <div className="alert">{error}</div>}
      <section className="card">
        {!assets ? <div className="muted">Carregando…</div> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Ativo</th><th>Nome</th><th className="r">Preço</th><th className="r">Em reais</th><th className="r">Dia</th></tr></thead>
            <tbody>{assets.map((a) => {
              const q = quotes[a.id];
              return (
                <tr key={a.id}>
                  <td><Link to={`/ativo/${a.id}`}><b>{a.symbol}</b></Link></td>
                  <td className="muted">{a.name}</td>
                  <td className="r num">{q ? fmtMoney(q.price, q.currency) : loadingQuotes ? "…" : <span className="muted">indisp.</span>}</td>
                  <td className="r num">{q ? fmtBRL(q.price_brl) : "—"}</td>
                  <td className={`r num tone-${trend(q?.change_pct)}`}>{q ? fmtPct(q.change_pct) : "—"}</td>
                </tr>
              );
            })}</tbody>
          </table></div>
        )}
        {assets && !loadingQuotes && assets.length > 0 && Object.keys(quotes).length === 0 && (
          <p className="muted small">Cotações indisponíveis no momento (a fonte pode estar limitando requisições). Tente novamente em instantes.</p>
        )}
      </section>
    </div>
  );
}
