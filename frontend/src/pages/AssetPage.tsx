import { useEffect, useRef, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { RiskPanel } from "../components/RiskPanel";
import { ChartPanel } from "../components/ChartPanel";
import { QuoteStamp, quoteIsOld } from "../components/QuoteStamp";
import { StatCard } from "../components/StatCard";
import { api, type Asset, type PortfolioSummary, type Quote } from "../services/api";
import { useApi } from "../services/dataCache";
import { CLASS_LABEL, fmtBRL, fmtDate, fmtMoney, fmtPct, fmtQty, fmtQtyRaw, trend } from "../lib/format";

const QUOTE_POLL_MS = 45_000;

export function AssetPage() {
  const id = Number(useParams().id);
  // ativo, cotação e carteira disparam em paralelo (e são servidos do cache quando frescos)
  const { data: asset, error } = useApi<Asset>(`/assets/${id}`);
  const { data: quoteData, error: quoteError, reload: reloadQuote } = useApi<Quote>(`/assets/${id}/quote`);
  const { data: pf, reload: loadPortfolio } = useApi<PortfolioSummary>("/portfolio");
  const quote = quoteData ?? null;

  // atualização periódica da cotação: pausa com a aba oculta e retoma (com refetch) ao voltar
  const reloadRef = useRef(reloadQuote);
  reloadRef.current = reloadQuote;
  useEffect(() => {
    let t: ReturnType<typeof setInterval> | null = null;
    const stop = () => { if (t) { clearInterval(t); t = null; } };
    const start = () => { stop(); t = setInterval(() => { if (!document.hidden) void reloadRef.current(); }, QUOTE_POLL_MS); };
    const onVis = () => { if (document.hidden) stop(); else { void reloadRef.current(); start(); } };
    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVis);
    return () => { stop(); document.removeEventListener("visibilitychange", onVis); };
  }, [id]);

  if (error) return <div className="alert">{error}</div>;
  if (!asset) return <div className="muted">Carregando…</div>;

  const holding = pf?.holdings.find((h) => h.asset.id === asset.id);
  const tone = trend(quote?.change_pct);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>{asset.symbol} <span className="tag">{CLASS_LABEL[asset.asset_class]}</span></h1>
          <p className="muted">{asset.name} · {asset.exchange}{asset.country ? ` · ${asset.country}` : ""}</p>
        </div>
      </header>

      <section className="stats-grid">
        <StatCard label={`Preço (${asset.currency})`} emphasis
          value={quote ? fmtMoney(quote.price, quote.currency) : quoteError ? "Indisponível" : "…"}
          sub={quote?.change_pct != null ? `${fmtPct(quote.change_pct)} no dia` : undefined} tone={tone} />
        <StatCard label="Preço em reais" value={quote ? fmtBRL(quote.price_brl) : "—"}
          sub={quote && quote.currency !== "BRL" ? `câmbio ${Number(quote.fx_rate).toFixed(4)}` : undefined} />
        <StatCard label="Sua posição" value={holding ? fmtQty(holding.quantity) : "0"}
          sub={holding ? `PM ${fmtBRL(holding.avg_price_brl)}` : undefined} />
        <StatCard label="Resultado da posição" value={holding ? fmtBRL(holding.pnl_brl) : "—"}
          sub={holding ? fmtPct(holding.pnl_pct) : undefined} tone={trend(holding?.pnl_brl)} />
      </section>
      {quote && <p className="muted small">Cotação de {fmtDate(quote.as_of)} (pode ter atraso). <QuoteStamp fetchedAt={quote.fetched_at} stale={quote.stale} /></p>}
      {quoteError && !quote && <div className="alert">{quoteError}</div>}

      <div className="trade-grid">
        <ChartPanel assetId={asset.id} />
        <div className="side-stack">
          <TradePanel asset={asset} quote={quote} cash={pf?.cash_balance} owned={holding?.quantity} onDone={loadPortfolio} />
          {holding && <RiskPanel asset={asset} quote={quote} holding={holding} onSaved={loadPortfolio} />}
        </div>
      </div>
    </div>
  );
}

function TradePanel({ asset, quote, cash, owned, onDone }: {
  asset: Asset; quote: Quote | null; cash?: string; owned?: string; onDone: () => void;
}) {
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [mode, setMode] = useState<"qty" | "amount">(asset.allows_fractional ? "amount" : "qty");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => { setMode(asset.allows_fractional ? "amount" : "qty"); setValue(""); setMsg(null); }, [asset]);

  const num = Number(value.replace(",", "."));
  const estimate = quote && num > 0
    ? mode === "amount" ? `≈ ${(num / Number(quote.price_brl)).toFixed(8)} ${asset.symbol}` : fmtBRL(String(num * Number(quote.price_brl)))
    : null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    const v = value.replace(",", ".");
    try {
      const body = mode === "amount" ? { amount_brl: v } : { quantity: v };
      const tx = side === "buy" ? await api.buy(asset.id, body) : await api.sell(asset.id, body);
      setMsg({ ok: true, text: `${side === "buy" ? "Compra" : "Venda"} realizada: ${fmtQty(tx.quantity)} ${asset.symbol} por ${fmtBRL(tx.gross_amount_brl)}.` });
      setValue(""); onDone();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : "Erro inesperado" });
    } finally { setBusy(false); }
  }

  return (
    <form className="card trade" onSubmit={submit}>
      <div className="seg">
        <button type="button" className={side === "buy" ? "on buy" : ""} onClick={() => setSide("buy")}>Comprar</button>
        <button type="button" className={side === "sell" ? "on sell" : ""} onClick={() => setSide("sell")}>Vender</button>
      </div>
      {asset.allows_fractional && (
        <div className="seg small">
          <button type="button" className={mode === "amount" ? "on" : ""} onClick={() => setMode("amount")}>Em reais</button>
          <button type="button" className={mode === "qty" ? "on" : ""} onClick={() => setMode("qty")}>Em quantidade</button>
        </div>
      )}
      <label>
        {mode === "amount" ? (side === "buy" ? "Valor que desejo investir (R$)" : "Valor que desejo resgatar (R$)") : "Quantidade"}
        <input inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder="0" required />
      </label>
      <div className="muted small row"><span>Estimativa</span><span className="num">{estimate ?? "—"}</span></div>
      <div className="muted small row"><span>Saldo disponível</span><span className="num">{fmtBRL(cash)}</span></div>
      {side === "sell" && (
        <div className="muted small row">
          <span>Disponível para venda</span>
          <span className="num">
            {fmtQty(owned ?? "0")}
            {owned && Number(owned) > 0 && <button type="button" className="link-btn" onClick={() => { setMode("qty"); setValue(fmtQtyRaw(owned)); }}>vender tudo</button>}
          </span>
        </div>
      )}
      {quote && quoteIsOld(quote.fetched_at, quote.stale) && <div className="muted small"><QuoteStamp fetchedAt={quote.fetched_at} stale={quote.stale} /> A execução usa o preço atual do servidor.</div>}
      {msg && <div className={msg.ok ? "ok" : "alert"}>{msg.text}</div>}
      <button className={`btn ${side === "buy" ? "primary" : "danger"}`} disabled={busy || !quote}>
        {busy ? "Enviando…" : side === "buy" ? `Comprar ${asset.symbol}` : `Vender ${asset.symbol}`}
      </button>
      <p className="muted small">Simulação: execução ao preço atual, sem corretagem.</p>
    </form>
  );
}
