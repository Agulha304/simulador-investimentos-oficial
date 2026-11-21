import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { QuoteStamp, quoteIsOld } from "../components/QuoteStamp";
import { type Asset, type QuoteBrief } from "../services/api";
import { useApi } from "../services/dataCache";
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
  // lista de ativos (cache de 5 min por grupo) e, assim que chega, as cotações; voltar a um grupo já visto é instantâneo
  const q = new URLSearchParams(Object.entries({ ...group.params, limit: 40 }).map(([k, v]) => [k, String(v)]));
  const { data: assets, error } = useApi<Asset[]>(`/assets?${q}`);
  const quotesPath = assets && assets.length > 0 ? `/assets/quotes?ids=${assets.map((a) => a.id).join(",")}` : null;
  const { data: quoteList, loading: loadingQuotes } = useApi<QuoteBrief[]>(quotesPath);
  const quotes = useMemo<Record<number, QuoteBrief>>(() => Object.fromEntries((quoteList ?? []).map((x) => [x.asset_id, x])), [quoteList]);
  const oldest = (quoteList ?? []).map((x) => x.fetched_at).filter((t): t is string => !!t).sort()[0];

  return (
    <div className="page">
      <header className="page-head"><div><h1>Mercado</h1><p className="muted">Explore os ativos disponíveis por classe.</p></div></header>
      <div className="chart-toolbar">
        {GROUPS.map((g) => <button key={g.id} className={`tool${group.id === g.id ? " on" : ""}`} onClick={() => setGroup(g)}>{g.label}</button>)}
      </div>
      {error && !assets && <div className="alert">{error}</div>}
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
                  <td className="r num">{q ? fmtMoney(q.price, q.currency) : loadingQuotes ? "…" : <span className="muted">indisp.</span>}{q && quoteIsOld(q.fetched_at, q.stale) && <><br /><QuoteStamp fetchedAt={q.fetched_at} stale={q.stale} /></>}</td>
                  <td className="r num">{q ? fmtBRL(q.price_brl) : "—"}</td>
                  <td className={`r num tone-${trend(q?.change_pct)}`}>{q ? fmtPct(q.change_pct) : "—"}</td>
                </tr>
              );
            })}</tbody>
          </table></div>
        )}
        {oldest && <p className="small" style={{ marginTop: 8 }}><QuoteStamp fetchedAt={oldest} stale={(quoteList ?? []).some((x) => x.stale === true)} /></p>}
        {assets && !loadingQuotes && assets.length > 0 && Object.keys(quotes).length === 0 && (
          <p className="muted small">Cotações indisponíveis no momento (a fonte pode estar limitando requisições). Tente novamente em instantes.</p>
        )}
      </section>
    </div>
  );
}
