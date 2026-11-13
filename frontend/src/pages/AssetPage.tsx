import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { RiskPanel } from "../components/RiskPanel";
import { ChartPanel } from "../components/ChartPanel";
import { StatCard } from "../components/StatCard";
import { api, type Asset, type PortfolioSummary, type Quote } from "../services/api";
import { CLASS_LABEL, fmtBRL, fmtDate, fmtMoney, fmtPct, fmtQty, trend } from "../lib/format";

export function AssetPage() {
  const id = Number(useParams().id);
  const [asset, setAsset] = useState<Asset | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoteError, setQuoteError] = useState<string | null>(null);
  const [pf, setPf] = useState<PortfolioSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadQuote = useCallback(() => {
    api.quote(id).then((q) => { setQuote(q); setQuoteError(null); }).catch((e: Error) => setQuoteError(e.message));
  }, [id]);
  const loadPortfolio = useCallback(() => { api.portfolio().then(setPf).catch(() => undefined); }, []);

  useEffect(() => {
    setAsset(null); setQuote(null); setError(null);
    api.asset(id).then(setAsset).catch((e: Error) => setError(e.message));
    loadQuote(); loadPortfolio();
    const t = setInterval(loadQuote, 30_000);
    return () => clearInterval(t);
  }, [id, loadQuote, loadPortfolio]);

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
      {quote && <p className="muted small">Cotação de {fmtDate(quote.as_of)} (pode ter atraso).</p>}
      {quoteError && <div className="alert">{quoteError}</div>}

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
    ? side === "buy" && mode === "amount" ? `≈ ${(num / Number(quote.price_brl)).toFixed(8)} ${asset.symbol}` : fmtBRL(String(num * Number(quote.price_brl)))
    : null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    const v = value.replace(",", ".");
    try {
      const tx = side === "buy"
        ? await api.buy(asset.id, mode === "amount" ? { amount_brl: v } : { quantity: v })
        : await api.sell(asset.id, v);
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
      {side === "buy" && asset.allows_fractional && (
        <div className="seg small">
          <button type="button" className={mode === "amount" ? "on" : ""} onClick={() => setMode("amount")}>Em reais</button>
          <button type="button" className={mode === "qty" ? "on" : ""} onClick={() => setMode("qty")}>Em quantidade</button>
        </div>
      )}
      <label>
        {side === "buy" && mode === "amount" ? "Valor que desejo investir (R$)" : "Quantidade"}
        <input inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder="0" required />
      </label>
      <div className="muted small row"><span>Estimativa</span><span className="num">{estimate ?? "—"}</span></div>
      <div className="muted small row"><span>Saldo disponível</span><span className="num">{fmtBRL(cash)}</span></div>
      {side === "sell" && <div className="muted small row"><span>Disponível para venda</span><span className="num">{fmtQty(owned ?? "0")}</span></div>}
      {msg && <div className={msg.ok ? "ok" : "alert"}>{msg.text}</div>}
      <button className={`btn ${side === "buy" ? "primary" : "danger"}`} disabled={busy || !quote}>
        {busy ? "Enviando…" : side === "buy" ? `Comprar ${asset.symbol}` : `Vender ${asset.symbol}`}
      </button>
      <p className="muted small">Simulação: execução ao preço atual, sem corretagem.</p>
    </form>
  );
}
