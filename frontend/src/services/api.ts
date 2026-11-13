/** Cliente HTTP da API. Valores Decimal chegam como string e assim são mantidos. */
export type Decimal = string;

export interface AssetBrief { id: number; symbol: string; name: string; asset_class: string; currency: string }

export interface Holding {
  asset: AssetBrief;
  quantity: Decimal;
  avg_price_brl: Decimal;
  total_cost_brl: Decimal;
  current_price_brl: Decimal | null;
  stop_loss: Decimal | null;      // na moeda do ativo
  take_profit: Decimal | null;
  market_value_brl: Decimal;
  pnl_brl: Decimal;
  pnl_pct: Decimal | null;
}

export interface PortfolioSummary {
  id: number;
  name: string;
  base_currency: string;
  cash_balance: Decimal;
  invested_brl: Decimal;
  market_value_brl: Decimal;
  total_equity_brl: Decimal;
  total_deposits_brl: Decimal;
  pnl_brl: Decimal;
  pnl_pct: Decimal | null;
  holdings: Holding[];
}

export interface Transaction {
  id: number;
  type: string;
  source: string;
  asset: AssetBrief | null;
  quantity: Decimal | null;
  unit_price_brl: Decimal | null;
  gross_amount_brl: Decimal;
  cash_amount_brl: Decimal;
  cash_balance_after: Decimal;
  note: string | null;
  created_at: string;
}

export interface Asset extends AssetBrief {
  exchange: string; country: string | null; allows_fractional: boolean;
}

export interface Quote {
  asset_id: number; price: Decimal; currency: string; fx_rate: Decimal; price_brl: Decimal;
  change_pct: Decimal | null; as_of: string;
}

export interface Candle { time: number; open: Decimal; high: Decimal; low: Decimal; close: Decimal; volume: Decimal }
export interface IndicatorData { kind: "overlay" | "pane"; series: Record<string, (Decimal | null)[]> }
export interface ChartData { asset_id: number; period: string; currency: string; candles: Candle[]; indicators: Record<string, IndicatorData> }
export interface ChartLayout { indicators: string[]; drawings: Record<string, unknown>[] }

export interface User { id: number; email: string; name: string; created_at: string }

const TOKEN_KEY = "sim.token";

export const tokenStore = {
  get(): string | null { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set(t: string) { try { localStorage.setItem(TOKEN_KEY, t); } catch { /* ignore */ } },
  clear() { try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ } },
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`/api${path}`, { ...init, headers });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : Array.isArray(body.detail) ? body.detail.map((d: { msg: string }) => d.msg).join("; ") : msg;
    } catch { /* corpo não-JSON */ }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  register: (email: string, name: string, password: string) =>
    request<{ access_token: string }>("/auth/register", { method: "POST", body: JSON.stringify({ email, name, password }) }),
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => request<User>("/auth/me"),
  searchAssets: (q: string) => request<Asset[]>(`/assets/search?q=${encodeURIComponent(q)}`),
  asset: (id: number) => request<Asset>(`/assets/${id}`),
  quote: (id: number) => request<Quote>(`/assets/${id}/quote`),
  chart: (id: number, period: string, indicators: string[]) =>
    request<ChartData>(`/assets/${id}/chart?period=${period}&indicators=${encodeURIComponent(indicators.join(","))}`),
  layout: (id: number) => request<ChartLayout>(`/assets/${id}/layout`),
  saveLayout: (id: number, layout: ChartLayout) => request<ChartLayout>(`/assets/${id}/layout`, { method: "PUT", body: JSON.stringify(layout) }),
  buy: (asset_id: number, body: { quantity?: string; amount_brl?: string }) =>
    request<Transaction>("/trades/buy", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ asset_id, ...body }) }),
  sell: (asset_id: number, quantity: string) =>
    request<Transaction>("/trades/sell", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ asset_id, quantity }) }),
  setRisk: (asset_id: number, stop_loss: string | null, take_profit: string | null) =>
    request<{ asset_id: number; currency: string; stop_loss: Decimal | null; take_profit: Decimal | null }>(
      `/trades/risk/${asset_id}`, { method: "PUT", body: JSON.stringify({ stop_loss, take_profit }) }),
  deposit: (amount: string) => request<Transaction>("/portfolio/deposit", { method: "POST", body: JSON.stringify({ amount }) }),
  portfolio: () => request<PortfolioSummary>("/portfolio"),
  transactions: (limit = 20) => request<Transaction[]>(`/portfolio/transactions?limit=${limit}`),
};
