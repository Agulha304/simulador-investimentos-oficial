import {
  CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, LineSeries, LineStyle, createChart,
  type IChartApi, type ISeriesApi, type MouseEventParams, type SeriesType, type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import { TOOLS, logicalToTime, priceToString, type Drawing, type DrawingType } from "../lib/drawings";
import type { ChartData } from "../services/api";
import { DrawingsPrimitive } from "./DrawingsPrimitive";

const PALETTE = ["#f2a541", "#4da3ff", "#c58af9", "#ff7a90", "#5fd4c4", "#e8d44d"];
const PANE_HEIGHT = 130;
const BASE_HEIGHT = 380;

const num = (v: string | null): number | null => (v == null ? null : Number(v));
const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

type LinePoint = { time: UTCTimestamp; value: number };

function line(times: number[], values: (string | null)[]): LinePoint[] {
  const out: LinePoint[] = [];
  values.forEach((v, i) => { const n = num(v); if (n != null) out.push({ time: times[i] as UTCTimestamp, value: n }); });
  return out;
}

export function paneCount(data: ChartData | null): number {
  return data ? Object.values(data.indicators).filter((i) => i.kind === "pane").length : 0;
}

interface Props {
  data: ChartData | null;
  type: "candles" | "line";
  drawings: Drawing[];
  tool: DrawingType | null;
  selectedId: string | null;
  onDrawingsChange: (d: Drawing[]) => void;
  onSelect: (id: string | null) => void;
  onToolDone: () => void;
}

/** Desenha candles + indicadores + marcações. A lib trata zoom, pan e escala de tempo/preço. */
export function PriceChart(props: Props) {
  const { data, type, drawings, tool, selectedId } = props;
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<SeriesType>[]>([]);
  const priceRef = useRef<ISeriesApi<SeriesType> | null>(null);
  const primRef = useRef<DrawingsPrimitive | null>(null);
  const timesRef = useRef<number[]>([]);
  const pending = useRef<{ type: DrawingType; first: Drawing["points"][0] } | null>(null);
  const preview = useRef<Drawing | null>(null);
  const live = useRef(props);   // últimos props, lidos pelos handlers do gráfico
  live.current = props;

  const sync = () => primRef.current?.set({
    drawings: live.current.drawings, preview: preview.current, selectedId: live.current.selectedId, times: timesRef.current,
  });

  useEffect(() => {
    if (!host.current) return;
    const chart = createChart(host.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: css("--text-muted"), fontFamily: css("--font"), panes: { separatorColor: css("--border") } },
      grid: { vertLines: { color: "rgba(138,165,177,0.08)" }, horzLines: { color: "rgba(138,165,177,0.08)" } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: css("--border") },
      timeScale: { borderColor: css("--border"), timeVisible: true, secondsVisible: false },
    });
    chartRef.current = chart;

    const pointFrom = (param: MouseEventParams): Drawing["points"][0] | null => {
      const series = priceRef.current;
      if (!param.point || !series || timesRef.current.length < 2) return null;
      const logical = chart.timeScale().coordinateToLogical(param.point.x);
      const price = series.coordinateToPrice(param.point.y);
      if (logical == null || price == null || Number(price) <= 0) return null;
      return { time: logicalToTime(timesRef.current, logical), price: priceToString(Number(price)) };
    };
    const onClick = (param: MouseEventParams) => {
      const { tool: t, drawings: ds } = live.current;
      if (!param.point) return;
      if (!t) { live.current.onSelect(primRef.current?.findAt(param.point) ?? null); return; }
      const pt = pointFrom(param);
      if (!pt) return;
      const need = TOOLS.find((x) => x.type === t)?.points ?? 1;
      if (need === 2 && !pending.current) { pending.current = { type: t, first: pt }; return; }
      const points = need === 2 ? [pending.current!.first, pt] : [pt];
      if (need === 2 && points[0].time === pt.time && points[0].price === pt.price) return;   // dois cliques no mesmo ponto
      let text: string | undefined;
      if (t === "marker") { const v = window.prompt("Anotação (até 80 caracteres):", ""); if (v === null) return; text = v.trim().slice(0, 80); }
      const d: Drawing = { id: crypto.randomUUID(), type: t, points, ...(text ? { text } : {}) };
      pending.current = null; preview.current = null;
      live.current.onDrawingsChange([...ds, d]);
      live.current.onSelect(d.id);
      live.current.onToolDone();
    };
    const onMove = (param: MouseEventParams) => {
      if (!pending.current) return;
      const pt = pointFrom(param);
      preview.current = pt ? { id: "preview", type: pending.current.type, points: [pending.current.first, pt] } : null;
      sync();
    };
    chart.subscribeClick(onClick);
    chart.subscribeCrosshairMove(onMove);
    return () => {
      chart.unsubscribeClick(onClick); chart.unsubscribeCrosshairMove(onMove);
      chart.remove(); chartRef.current = null; seriesRef.current = []; priceRef.current = null; primRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !data) return;
    seriesRef.current.forEach((s) => chart.removeSeries(s));
    seriesRef.current = [];
    priceRef.current = null; primRef.current = null;
    const up = css("--up"), down = css("--down"), accent = css("--accent");

    // tempos estritamente crescentes e únicos (exigência da biblioteca)
    const seen = new Set<number>();
    const idx: number[] = [];
    data.candles.forEach((c, i) => { if (!seen.has(c.time)) { seen.add(c.time); idx.push(i); } });
    const candles = idx.map((i) => data.candles[i]);
    const times = candles.map((c) => c.time);
    timesRef.current = times;
    const pick = (arr: (string | null)[]) => idx.map((i) => arr[i]);

    const add = <T extends SeriesType>(def: Parameters<IChartApi["addSeries"]>[0], opts: object, pane = 0) => {
      const s = chart.addSeries(def, opts, pane) as ISeriesApi<T>;
      seriesRef.current.push(s as ISeriesApi<SeriesType>);
      return s;
    };

    // --- preço
    let price: ISeriesApi<SeriesType>;
    if (type === "candles") {
      const s = add<"Candlestick">(CandlestickSeries, { upColor: up, downColor: down, borderVisible: false, wickUpColor: up, wickDownColor: down });
      s.setData(candles.map((c) => ({ time: c.time as UTCTimestamp, open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close) })));
      price = s;
    } else {
      const s = add<"Line">(LineSeries, { color: accent, lineWidth: 2 });
      s.setData(candles.map((c) => ({ time: c.time as UTCTimestamp, value: Number(c.close) })));
      price = s;
    }

    // --- indicadores
    let colorIdx = 0;
    const nextColor = () => PALETTE[colorIdx++ % PALETTE.length];
    let pane = 0;
    for (const [spec, ind] of Object.entries(data.indicators)) {
      const sd = ind.series;
      if (ind.kind === "overlay") {
        if (spec.startsWith("bbands")) {
          const c = nextColor();
          add<"Line">(LineSeries, { color: c, lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false }).setData(line(times, pick(sd.upper)));
          add<"Line">(LineSeries, { color: c, lineWidth: 1, priceLineVisible: false, lastValueVisible: false }).setData(line(times, pick(sd.middle)));
          add<"Line">(LineSeries, { color: c, lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false }).setData(line(times, pick(sd.lower)));
        } else {
          const values = Object.values(sd)[0];
          add<"Line">(LineSeries, { color: nextColor(), lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: spec.toUpperCase() }).setData(line(times, pick(values)));
        }
        continue;
      }
      pane += 1;
      if (spec === "volume") {
        const s = add<"Histogram">(HistogramSeries, { priceFormat: { type: "volume" }, priceLineVisible: false }, pane);
        s.setData(candles.map((c) => ({ time: c.time as UTCTimestamp, value: Number(c.volume), color: Number(c.close) >= Number(c.open) ? up + "99" : down + "99" })));
      } else if (spec.startsWith("rsi")) {
        const s = add<"Line">(LineSeries, { color: PALETTE[3], lineWidth: 2, priceLineVisible: false, title: "RSI" }, pane);
        s.setData(line(times, pick(sd.rsi)));
        for (const lvl of [30, 70]) s.createPriceLine({ price: lvl, color: css("--text-muted"), lineStyle: LineStyle.Dotted, lineWidth: 1, axisLabelVisible: true, title: "" });
      } else if (spec.startsWith("macd")) {
        const h = add<"Histogram">(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, pane);
        h.setData(line(times, pick(sd.histogram)).map((p) => ({ ...p, color: p.value >= 0 ? up + "99" : down + "99" })));
        add<"Line">(LineSeries, { color: PALETTE[1], lineWidth: 2, priceLineVisible: false, title: "MACD" }, pane).setData(line(times, pick(sd.macd)));
        add<"Line">(LineSeries, { color: PALETTE[0], lineWidth: 1, priceLineVisible: false, title: "Sinal" }, pane).setData(line(times, pick(sd.signal)));
      } else if (spec.startsWith("stoch")) {
        const k = add<"Line">(LineSeries, { color: PALETTE[1], lineWidth: 2, priceLineVisible: false, title: "%K" }, pane);
        k.setData(line(times, pick(sd.k)));
        add<"Line">(LineSeries, { color: PALETTE[0], lineWidth: 1, priceLineVisible: false, title: "%D" }, pane).setData(line(times, pick(sd.d)));
        for (const lvl of [20, 80]) k.createPriceLine({ price: lvl, color: css("--text-muted"), lineStyle: LineStyle.Dotted, lineWidth: 1, axisLabelVisible: true, title: "" });
      } else if (spec.startsWith("adx")) {
        add<"Line">(LineSeries, { color: PALETTE[4], lineWidth: 2, priceLineVisible: false, title: "ADX" }, pane).setData(line(times, pick(sd.adx)));
        add<"Line">(LineSeries, { color: up, lineWidth: 1, priceLineVisible: false, title: "+DI" }, pane).setData(line(times, pick(sd.plus_di)));
        add<"Line">(LineSeries, { color: down, lineWidth: 1, priceLineVisible: false, title: "-DI" }, pane).setData(line(times, pick(sd.minus_di)));
      } else {
        add<"Line">(LineSeries, { color: PALETTE[5], lineWidth: 2, priceLineVisible: false, title: spec.split(":")[0].toUpperCase() }, pane).setData(line(times, pick(Object.values(sd)[0])));
      }
    }

    // alturas: painel de preço grande, painéis de indicador menores
    const panes = chart.panes();
    panes.forEach((p, i) => { if (i > 0) p.setHeight(PANE_HEIGHT); });
    chart.timeScale().fitContent();

    priceRef.current = price;
    const prim = new DrawingsPrimitive();
    price.attachPrimitive(prim);
    primRef.current = prim;
    sync();
  }, [data, type]);

  // desenhos / seleção mudaram: só redesenha a primitiva
  useEffect(sync, [drawings, selectedId]);
  // trocou de ferramenta (ou cancelou): descarta clique pendente e pré-visualização
  useEffect(() => { pending.current = null; preview.current = null; sync(); }, [tool]);

  return <div ref={host} className={`price-chart${tool ? " drawing" : ""}`} style={{ height: BASE_HEIGHT + paneCount(data) * (PANE_HEIGHT + 8) }} />;
}
