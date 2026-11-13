/** Modelo e geometria dos desenhos. Âncoras são (tempo unix, preço), nunca pixels. */
export type DrawingType = "trend" | "ray" | "hline" | "support" | "resistance" | "marker";

export interface DrawingPoint { time: number; price: string }
export interface Drawing { id: string; type: DrawingType; points: DrawingPoint[]; text?: string | null; color?: string | null }

export const TOOLS: { type: DrawingType; label: string; hint: string; points: 1 | 2 }[] = [
  { type: "trend", label: "Linha de tendência", hint: "Clique em dois pontos", points: 2 },
  { type: "ray", label: "Raio", hint: "Clique em dois pontos; a linha segue para a direita", points: 2 },
  { type: "hline", label: "Linha horizontal", hint: "Clique no preço desejado", points: 1 },
  { type: "support", label: "Suporte", hint: "Clique no preço do suporte", points: 1 },
  { type: "resistance", label: "Resistência", hint: "Clique no preço da resistência", points: 1 },
  { type: "marker", label: "Marcação", hint: "Clique no ponto e digite uma anotação", points: 1 },
];

export const DEFAULT_COLOR: Record<DrawingType, string> = {
  trend: "#4da3ff", ray: "#c58af9", hline: "#f2a541", support: "#2ecc8f", resistance: "#f2545b", marker: "#e8d44d",
};

export const LABEL: Record<DrawingType, string> = {
  trend: "Tendência", ray: "Raio", hline: "Horizontal", support: "Suporte", resistance: "Resistência", marker: "Marcação",
};

/**
 * Tempo -> posição lógica (índice de candle, fracionário). Interpola entre candles e
 * extrapola além das pontas usando o passo local, então o desenho continua válido
 * ao trocar de período ou quando se estende para o futuro (raio).
 */
export function timeToLogical(times: number[], t: number): number {
  const n = times.length;
  if (n === 0) return 0;
  if (n === 1) return 0;
  if (t <= times[0]) return (t - times[0]) / (times[1] - times[0]);
  if (t >= times[n - 1]) return n - 1 + (t - times[n - 1]) / (times[n - 1] - times[n - 2]);
  let lo = 0, hi = n - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (times[mid] <= t) lo = mid; else hi = mid; }
  return lo + (t - times[lo]) / (times[lo + 1] - times[lo]);
}

/** Posição lógica -> tempo. Dentro dos dados encaixa no candle mais próximo (snap). */
export function logicalToTime(times: number[], l: number): number {
  const n = times.length;
  if (n < 2) return times[0] ?? 0;
  if (l <= 0) return Math.round(times[0] + l * (times[1] - times[0]));
  if (l >= n - 1) return Math.round(times[n - 1] + (l - (n - 1)) * (times[n - 1] - times[n - 2]));
  return times[Math.round(l)];
}

export interface Px { x: number; y: number }

/** Distância de um ponto a um segmento; `infinite` estende o segmento além de b (raio). */
export function distToSegment(p: Px, a: Px, b: Px, infinite = false): number {
  const dx = b.x - a.x, dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  if (len2 === 0) return Math.hypot(p.x - a.x, p.y - a.y);
  let t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
  t = infinite ? Math.max(0, t) : Math.max(0, Math.min(1, t));
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

export const formatPrice = (price: string | number) => {
  const n = Number(price);
  return n >= 1 ? n.toFixed(2) : n.toFixed(6);
};

/** Preço do clique -> string com a precisão certa (a API guarda Decimal exato). */
export const priceToString = (price: number) => (price >= 1 ? price.toFixed(4) : price.toFixed(8));
