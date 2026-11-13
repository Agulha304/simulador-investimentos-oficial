import {
  CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, LineSeries, LineStyle, createChart,
  type IChartApi, type ISeriesApi, type SeriesType, type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { ChartData } from "../services/api";

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
  onReady?: (chart: IChartApi, price: ISeriesApi<SeriesType>) => void;
}

/** Desenha candles + indicadores. A lib trata zoom, pan e escala de tempo/preço. */
export function PriceChart({ data, type, onReady }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<SeriesType>[]>([]);

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
    return () => { chart.remove(); chartRef.current = null; seriesRef.current = []; };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !data) return;
    seriesRef.current.forEach((s) => chart.removeSeries(s));
    seriesRef.current = [];
    const up = css("--up"), down = css("--down"), accent = css("--accent");

    // tempos estritamente crescentes e únicos (exigência da biblioteca)
    const seen = new Set<number>();
    const idx: number[] = [];
    data.candles.forEach((c, i) => { if (!seen.has(c.time)) { seen.add(c.time); idx.push(i); } });
    const candles = idx.map((i) => data.candles[i]);
    const times = candles.map((c) => c.time);
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
    onReady?.(chart, price);
  }, [data, type, onReady]);

  return <div ref={host} className="price-chart" style={{ height: BASE_HEIGHT + paneCount(data) * (PANE_HEIGHT + 8) }} />;
}
