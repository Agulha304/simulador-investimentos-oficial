/** Cliente HTTP da API. Valores Decimal chegam como string e assim são mantidos. */
export type Decimal = string;

export interface AssetBrief { id: number; symbol: string; name: string; asset_class: string; currency: string }

export interface Holding {
  asset: AssetBrief;
  quantity: Decimal;
  avg_price_brl: Decimal;
  total_cost_brl: Decimal;
  current_price_brl: Decimal | null;
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
  portfolio: () => request<PortfolioSummary>("/portfolio"),
  transactions: (limit = 20) => request<Transaction[]>(`/portfolio/transactions?limit=${limit}`),
};
