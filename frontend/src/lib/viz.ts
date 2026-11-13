/** Cores dos gráficos. Validadas com o validador de paleta contra o fundo do app (#102631):
 *  azul + laranja passam em todos os critérios (inclusive daltonismo). Verde/vermelho NÃO passam em
 *  daltonismo, por isso o sinal de ganho/perda nunca depende só da cor (direção da barra, ▲/▼, texto). */
export const VIZ = {
  s1: "#3987e5",        // série 1 (categórica, azul)
  s2: "#d95926",        // série 2 (categórica, laranja)
  critical: "#d03b3b",  // status: perda/queda (sempre com ícone e rótulo)
  grid: "#1f3d4c",      // hairline sólida, um tom acima do fundo
  axis: "#2b5163",
  text: "#8aa5b1",
  surface: "#102631",
};

const nf = (d: number) => new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });
export const fmtNum = (v: number, d = 2) => nf(d).format(v);
export const fmtSigned = (v: number, d = 2) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${nf(d).format(Math.abs(v))}`;
export const fmtCompactBRL = (v: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", notation: "compact", maximumFractionDigits: 1 }).format(v);
const dayFmt = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" });
const hourFmt = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
export const fmtTick = (iso: string, hourly: boolean) => (hourly ? hourFmt : dayFmt).format(new Date(iso));
