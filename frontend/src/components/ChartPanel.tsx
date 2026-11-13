import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ChartData } from "../services/api";
import { INDICATOR_OPTIONS, PERIODS, labelOf } from "../lib/indicatorCatalog";
import { LABEL, TOOLS, type Drawing, type DrawingType } from "../lib/drawings";
import { PriceChart } from "./PriceChart";

export function ChartPanel({ assetId }: { assetId: number }) {
  const [period, setPeriod] = useState("6mo");
  const [type, setType] = useState<"candles" | "line">("candles");
  const [indicators, setIndicators] = useState<string[]>([]);
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [tool, setTool] = useState<DrawingType | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [layoutLoaded, setLayoutLoaded] = useState(false);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [data, setData] = useState<ChartData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [menu, setMenu] = useState(false);

  // layout salvo (indicadores e desenhos) por usuário e ativo
  useEffect(() => {
    setLayoutLoaded(false); setData(null); setTool(null); setSelectedId(null);
    api.layout(assetId)
      .then((l) => { setIndicators(l.indicators); setDrawings(l.drawings as unknown as Drawing[]); })
      .catch(() => { setIndicators([]); setDrawings([]); })
      .finally(() => setLayoutLoaded(true));
  }, [assetId]);

  const saveTimer = useRef<ReturnType<typeof setTimeout>>();
  const persist = useCallback((ind: string[], dr: Drawing[]) => {
    clearTimeout(saveTimer.current);
    setSaveState("saving");
    saveTimer.current = setTimeout(() => {
      api.saveLayout(assetId, { indicators: ind, drawings: dr as unknown as Record<string, unknown>[] })
        .then(() => setSaveState("saved")).catch(() => setSaveState("error"));
    }, 600);
  }, [assetId]);
  useEffect(() => () => clearTimeout(saveTimer.current), []);

  const changeDrawings = useCallback((next: Drawing[]) => { setDrawings(next); persist(indicators, next); }, [indicators, persist]);
  const toggle = (spec: string) => {
    const next = indicators.includes(spec) ? indicators.filter((s) => s !== spec) : [...indicators, spec];
    setIndicators(next); persist(next, drawings); setMenu(false);
  };

  const removeSelected = useCallback(() => {
    if (!selectedId) return;
    changeDrawings(drawings.filter((d) => d.id !== selectedId)); setSelectedId(null);
  }, [selectedId, drawings, changeDrawings]);

  // atalhos: Esc cancela a ferramenta, Delete remove o desenho selecionado
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") return;
      if (e.key === "Escape") { setTool(null); setSelectedId(null); }
      if ((e.key === "Delete" || e.key === "Backspace") && selectedId) { e.preventDefault(); removeSelected(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedId, removeSelected]);

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

  const activeTool = TOOLS.find((t) => t.type === tool);
  const selected = drawings.find((d) => d.id === selectedId);

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
        <span className={`save-state small muted ${saveState}`}>
          {saveState === "saving" ? "Salvando…" : saveState === "saved" ? "Salvo" : saveState === "error" ? "Erro ao salvar" : ""}
        </span>
      </div>

      <div className="chart-toolbar draw-tools" role="toolbar" aria-label="Ferramentas de desenho">
        <span className="muted small">Desenhar:</span>
        {TOOLS.map((t) => (
          <button key={t.type} type="button" className={`tool${tool === t.type ? " on" : ""}`} title={t.hint}
            onClick={() => { setTool(tool === t.type ? null : t.type); setSelectedId(null); }}>
            {t.label}
          </button>
        ))}
        <span className="grow" />
        <button type="button" className="btn ghost small" disabled={!selected} onClick={removeSelected}>
          {selected ? `Excluir ${LABEL[selected.type].toLowerCase()}` : "Excluir"}
        </button>
        <button type="button" className="btn ghost small" disabled={!drawings.length}
          onClick={() => { if (window.confirm(`Remover os ${drawings.length} desenhos deste ativo?`)) { changeDrawings([]); setSelectedId(null); } }}>
          Limpar tudo
        </button>
      </div>
      {activeTool && <div className="tool-hint small">{activeTool.hint}. <kbd>Esc</kbd> cancela.</div>}

      {indicators.length > 0 && (
        <div className="chips">
          {indicators.map((s) => <button key={s} type="button" className="chip" onClick={() => toggle(s)}>{labelOf(s)} ✕</button>)}
        </div>
      )}
      <div className="chart-body">
        {error && <div className="alert">{error}</div>}
        {loading && <div className="chart-loading muted small">Carregando…</div>}
        <PriceChart data={data} type={type} drawings={drawings} tool={tool} selectedId={selectedId}
          onDrawingsChange={changeDrawings} onSelect={setSelectedId} onToolDone={() => setTool(null)} />
      </div>
      {data && <p className="muted small">Valores em {data.currency}. Roda do mouse = zoom, arrastar = mover. Clique em um desenho para selecioná-lo.</p>}
    </section>
  );
}
