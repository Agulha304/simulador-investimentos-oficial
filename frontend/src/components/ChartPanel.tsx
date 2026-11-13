import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ChartData } from "../services/api";
import { INDICATOR_OPTIONS, PERIODS, labelOf } from "../lib/indicatorCatalog";
import { PriceChart } from "./PriceChart";

export function ChartPanel({ assetId }: { assetId: number }) {
  const [period, setPeriod] = useState("6mo");
  const [type, setType] = useState<"candles" | "line">("candles");
  const [indicators, setIndicators] = useState<string[]>([]);
  const [layoutLoaded, setLayoutLoaded] = useState(false);
  const [data, setData] = useState<ChartData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [menu, setMenu] = useState(false);
  const drawings = useRef<Record<string, unknown>[]>([]);   // Fase 4: desenhos compartilham o mesmo layout salvo

  // layout salvo (indicadores escolhidos) por usuário e ativo
  useEffect(() => {
    setLayoutLoaded(false); setData(null);
    api.layout(assetId)
      .then((l) => { setIndicators(l.indicators); drawings.current = l.drawings; })
      .catch(() => setIndicators([]))
      .finally(() => setLayoutLoaded(true));
  }, [assetId]);

  const saveTimer = useRef<ReturnType<typeof setTimeout>>();
  const persist = useCallback((next: string[]) => {
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => { api.saveLayout(assetId, { indicators: next, drawings: drawings.current }).catch(() => undefined); }, 500);
  }, [assetId]);

  const toggle = (spec: string) => {
    const next = indicators.includes(spec) ? indicators.filter((s) => s !== spec) : [...indicators, spec];
    setIndicators(next); persist(next); setMenu(false);
  };

  useEffect(() => {
    if (!layoutLoaded) return;
    let cancelled = false;
    setLoading(true); setError(null);
    api.chart(assetId, period, indicators)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e: Error) => { if (!cancelled) { setError(e.message); setData(null); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [assetId, period, indicators, layoutLoaded]);

  return (
    <section className="card chart-card">
      <div className="chart-toolbar">
        <div className="seg compact">
          {PERIODS.map((p) => <button key={p.id} type="button" className={period === p.id ? "on" : ""} onClick={() => setPeriod(p.id)}>{p.label}</button>)}
        </div>
        <div className="seg compact">
          <button type="button" className={type === "candles" ? "on" : ""} onClick={() => setType("candles")}>Candles</button>
          <button type="button" className={type === "line" ? "on" : ""} onClick={() => setType("line")}>Linha</button>
        </div>
        <div className="menu-wrap">
          <button type="button" className="btn ghost small" onClick={() => setMenu(!menu)}>Indicadores ▾</button>
          {menu && (
            <div className="menu" onMouseLeave={() => setMenu(false)}>
              {(["overlay", "pane"] as const).map((g) => (
                <div key={g}>
                  <div className="menu-title">{g === "overlay" ? "Sobre o gráfico" : "Painéis separados"}</div>
                  {INDICATOR_OPTIONS.filter((o) => o.group === g).map((o) => (
                    <button key={o.spec} type="button" className="menu-item" onClick={() => toggle(o.spec)}>
                      <span>{indicators.includes(o.spec) ? "✓" : ""}</span>{o.label}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      {indicators.length > 0 && (
        <div className="chips">
          {indicators.map((s) => <button key={s} type="button" className="chip" onClick={() => toggle(s)}>{labelOf(s)} ✕</button>)}
        </div>
      )}
      <div className="chart-body">
        {error && <div className="alert">{error}</div>}
        {loading && <div className="chart-loading muted small">Carregando…</div>}
        <PriceChart data={data} type={type} />
      </div>
      {data && <p className="muted small">Valores em {data.currency}. Use a roda do mouse para zoom e arraste para mover.</p>}
    </section>
  );
}
