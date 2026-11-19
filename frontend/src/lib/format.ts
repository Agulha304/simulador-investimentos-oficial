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
  FIXED_INCOME_COUPON: "Juros RF",
  FIXED_INCOME_MATURITY: "Vencimento RF",
  BUDGET_INCOME: "Receita (orçamento)",
  BUDGET_EXPENSE: "Despesa (orçamento)",
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

export const FI_TYPE_LABEL: Record<string, string> = {
  TESOURO_SELIC: "Tesouro Selic", TESOURO_PREFIXADO: "Tesouro Prefixado", TESOURO_PREFIXADO_JUROS: "Tesouro Prefixado c/ juros",
  TESOURO_IPCA: "Tesouro IPCA+", TESOURO_IPCA_JUROS: "Tesouro IPCA+ c/ juros", TESOURO_IGPM_JUROS: "Tesouro IGPM+ c/ juros",
  TESOURO_RENDA_MAIS: "Tesouro Renda+", TESOURO_EDUCA_MAIS: "Tesouro Educa+",
  CDB: "CDB", LCI: "LCI", LCA: "LCA", CRI: "CRI", CRA: "CRA", DEBENTURE: "Debênture",
};
export const LIQUIDITY_LABEL: Record<string, string> = { DAILY: "Diária", AT_MATURITY: "No vencimento", SPECIFIC_DATES: "Em janelas" };
export const FREQ_LABEL: Record<string, string> = { AT_MATURITY: "No vencimento", MONTHLY: "Mensal", SEMIANNUAL: "Semestral", ANNUAL: "Anual" };
export const RISK_LABEL: Record<string, string> = { LOW: "Baixo", MEDIUM: "Médio", HIGH: "Alto" };
export const FI_STATUS_LABEL: Record<string, string> = { ACTIVE: "Ativa", REDEEMED: "Resgatada", MATURED: "Vencida" };

/** 192 -> "3 min 12 s"; 3600+ -> "1 h 05 min". */
export function fmtDuration(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600), m = Math.floor((totalSeconds % 3600) / 60), sec = totalSeconds % 60;
  if (h) return `${h} h ${String(m).padStart(2, "0")} min`;
  return m ? `${m} min${sec ? ` ${String(sec).padStart(2, "0")} s` : ""}` : `${sec} s`;
}

/** "2026-11-01" -> "novembro de 2026". */
export const fmtMonth = (iso: string) =>
  new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" }).format(new Date(`${iso.slice(0, 7)}-01T12:00:00`));
export const fmtMonthShort = (iso: string) =>
  new Intl.DateTimeFormat("pt-BR", { month: "short", year: "2-digit" }).format(new Date(`${iso.slice(0, 7)}-01T12:00:00`));
export const FREQUENCY_LABEL: Record<string, string> = { MONTHLY: "Mensal", QUARTERLY: "Trimestral", SEMIANNUAL: "Semestral", ANNUAL: "Anual" };
export const ORIGIN_LABEL: Record<string, string> = { MANUAL: "Manual", RECURRING: "Recorrente", INVESTMENT: "Investimento", SYSTEM: "Sistema", REVERSAL: "Estorno" };

/** Aceita "1.500,50" ou "1500.50" e devolve "1500.50" (a validação de verdade é do servidor). */
export const parseMoneyInput = (s: string) => {
  const t = s.trim().replace(/\s|R\$/g, "");
  return t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t;
};

export const CATEGORY_LABEL: Record<string, string> = {
  RESIDENTIAL: "Imóvel residencial", COMMERCIAL: "Imóvel comercial", LAND: "Terreno", CAR: "Automóvel", MOTORCYCLE: "Motocicleta",
  INSTRUMENT: "Instrumento musical", EQUIPMENT: "Equipamento", ANTIQUE: "Antiguidade", COLLECTIBLE: "Colecionável", OTHER: "Outros",
};
export const OCCUPANCY_LABEL: Record<string, string> = {
  OWNER_OCCUPIED: "Moradia própria", VACANT: "Desocupado", LISTED_FOR_RENT: "Anunciado para alugar (vago)", RENTED: "Alugado",
};
export const GOOD_STATUS_LABEL: Record<string, string> = { ACTIVE: "Ativo", SOLD: "Vendido", LOST: "Baixado" };
export const COST_LABEL: Record<string, string> = {
  IPTU: "IPTU", CONDO: "Condomínio", MAINTENANCE: "Manutenção", FUEL: "Combustível", INSURANCE: "Seguro", IPVA: "IPVA",
  LICENSING: "Licenciamento", PARKING: "Estacionamento", OTHER: "Outros",
};
export const CONDITION_LABEL: Record<string, string> = { NEW: "Novo", EXCELLENT: "Excelente", GOOD: "Bom", FAIR: "Regular", POOR: "Ruim" };
export const EVENT_LABEL: Record<string, string> = {
  PURCHASE: "Compra", SALE: "Venda", OCCUPANCY: "Ocupação", RENTED: "Alugado", VACATED: "Vacância", MAINTENANCE: "Manutenção",
  COST_CHANGE: "Custos", WRITE_OFF: "Baixa",
};
export const REAL_ESTATE_CATS = ["RESIDENTIAL", "COMMERCIAL", "LAND"];
