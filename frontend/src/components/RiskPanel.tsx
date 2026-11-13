import { useEffect, useState, type FormEvent } from "react";
import { api, type Asset, type Holding, type Quote } from "../services/api";
import { fmtMoney } from "../lib/format";

/** Stop Loss / Take Profit da posição. Os níveis são na MOEDA DO ATIVO (ex.: US$ para AAPL). */
export function RiskPanel({ asset, quote, holding, onSaved }: {
  asset: Asset; quote: Quote | null; holding: Holding; onSaved: () => void;
}) {
  const [stop, setStop] = useState("");
  const [take, setTake] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    setStop(holding.stop_loss ? String(Number(holding.stop_loss)) : "");
    setTake(holding.take_profit ? String(Number(holding.take_profit)) : "");
  }, [holding.stop_loss, holding.take_profit, asset.id]);

  const norm = (v: string) => (v.trim() === "" ? null : v.trim().replace(",", "."));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try {
      await api.setRisk(asset.id, norm(stop), norm(take));
      setMsg({ ok: true, text: norm(stop) || norm(take) ? "Níveis salvos. A checagem roda a cada 2 minutos." : "Stop Loss e Take Profit removidos." });
      onSaved();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : "Erro inesperado" });
    } finally { setBusy(false); }
  }

  return (
    <form className="card trade" onSubmit={submit}>
      <h2>Stop Loss e Take Profit</h2>
      <p className="muted small" style={{ margin: 0 }}>
        Vende toda a posição a mercado quando o preço atingir o nível. Valores em {asset.currency}
        {quote ? ` — preço atual ${fmtMoney(quote.price, quote.currency)}` : ""}.
      </p>
      <label>Stop Loss ({asset.currency}) — abaixo do preço atual
        <input inputMode="decimal" value={stop} onChange={(e) => setStop(e.target.value)} placeholder="sem stop" />
      </label>
      <label>Take Profit ({asset.currency}) — acima do preço atual
        <input inputMode="decimal" value={take} onChange={(e) => setTake(e.target.value)} placeholder="sem take profit" />
      </label>
      {msg && <div className={msg.ok ? "ok" : "alert"}>{msg.text}</div>}
      <button className="btn primary" disabled={busy}>{busy ? "Salvando…" : "Salvar níveis"}</button>
      <p className="muted small" style={{ margin: 0 }}>
        Em saltos de preço (gap), a venda pode sair pior que o nível definido.
      </p>
    </form>
  );
}
