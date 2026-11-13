/** Catálogo de indicadores oferecidos na interface. O cálculo acontece no backend. */
export interface IndicatorOption { spec: string; label: string; group: "overlay" | "pane" }

export const INDICATOR_OPTIONS: IndicatorOption[] = [
  { spec: "sma:9", label: "SMA 9", group: "overlay" },
  { spec: "sma:20", label: "SMA 20", group: "overlay" },
  { spec: "sma:50", label: "SMA 50", group: "overlay" },
  { spec: "sma:200", label: "SMA 200", group: "overlay" },
  { spec: "ema:9", label: "EMA 9", group: "overlay" },
  { spec: "ema:21", label: "EMA 21", group: "overlay" },
  { spec: "ema:50", label: "EMA 50", group: "overlay" },
  { spec: "bbands:20:2", label: "Bandas de Bollinger (20, 2)", group: "overlay" },
  { spec: "vwap", label: "VWAP", group: "overlay" },
  { spec: "volume", label: "Volume", group: "pane" },
  { spec: "rsi:14", label: "RSI (14)", group: "pane" },
  { spec: "macd:12:26:9", label: "MACD (12, 26, 9)", group: "pane" },
  { spec: "stoch:14:3:3", label: "Estocástico (14, 3, 3)", group: "pane" },
  { spec: "adx:14", label: "ADX (14)", group: "pane" },
  { spec: "atr:14", label: "ATR (14)", group: "pane" },
];

export const labelOf = (spec: string) => INDICATOR_OPTIONS.find((o) => o.spec === spec)?.label ?? spec.toUpperCase();

export const PERIODS = [
  { id: "1d", label: "1D" }, { id: "5d", label: "5D" }, { id: "1mo", label: "1M" },
  { id: "6mo", label: "6M" }, { id: "1y", label: "1A" }, { id: "5y", label: "5A" }, { id: "max", label: "Máx" },
];
