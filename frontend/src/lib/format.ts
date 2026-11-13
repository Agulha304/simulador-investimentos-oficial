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

export const CLASS_LABEL: Record<string, string> = {
  STOCK: "Ação", ETF: "ETF", FII: "FII", REIT: "REIT", CRYPTO: "Criptomoeda", BDR: "BDR",
};

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 4 });
export const fmtMoney = (v: string, currency: string) => (currency === "USD" ? usd.format(Number(v)) : fmtBRL(v));

export const SOURCE_LABEL: Record<string, string> = {
  USER: "Manual", SYSTEM: "Sistema", STOP_LOSS: "Stop Loss", TAKE_PROFIT: "Take Profit",
  DISTRIBUTION_WORKER: "Automático", FIXED_INCOME_WORKER: "Automático",
};
export const KIND_LABEL: Record<string, string> = { DIVIDEND: "Dividendo", JCP: "JCP", RENDIMENTO: "Rendimento" };
export const STATUS_LABEL: Record<string, string> = { PENDING: "A receber", PAID: "Pago", CANCELLED: "Cancelado" };
export const fmtDay = (iso: string) => new Intl.DateTimeFormat("pt-BR").format(new Date(`${iso}T12:00:00`));

/** Quantidade exata para preencher um campo (ponto decimal, sem zeros à direita). */
export const fmtQtyRaw = (v: string) => (v.includes(".") ? v.replace(/0+$/, "").replace(/\.$/, "") : v);
export const COUNTRY_LABEL: Record<string, string> = { BR: "Brasil", US: "EUA" };
