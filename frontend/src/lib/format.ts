/** Formatação apenas para EXIBIÇÃO. Nenhum cálculo financeiro acontece no frontend. */
const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const pct = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "exceptZero" });
const dt = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

export const fmtBRL = (v: string | null | undefined) => (v == null ? "—" : brl.format(Number(v)));
export const fmtPct = (v: string | null | undefined) => (v == null ? "—" : `${pct.format(Number(v))}%`);
export const fmtDate = (iso: string) => dt.format(new Date(iso));
export const fmtQty = (v: string | null) => (v == null ? "—" : v.replace(/\.?0+$/, "").replace(".", ","));

export function trend(v: string | null | undefined): "up" | "down" | "flat" {
  if (v == null) return "flat";
  const n = Number(v);
  return n > 0 ? "up" : n < 0 ? "down" : "flat";
}

export const TX_LABEL: Record<string, string> = {
  DEPOSIT: "Depósito",
  WITHDRAWAL: "Retirada",
  BUY: "Compra",
  SELL: "Venda",
  DIVIDEND: "Provento",
  FIXED_INCOME_APPLY: "Aplicação RF",
  FIXED_INCOME_REDEEM: "Resgate RF",
  FIXED_INCOME_COUPON: "Cupom RF",
  FIXED_INCOME_MATURITY: "Vencimento RF",
};
