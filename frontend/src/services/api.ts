import { ACCOUNT_PATHS, gameStore } from "./gameStore";
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
  fixed_income_invested_brl: Decimal;
  fixed_income_value_brl: Decimal;
  goods_net_brl: Decimal;
  companies_net_brl: Decimal;
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
  unit_price: Decimal | null;
  price_currency: string | null;
  fx_rate: Decimal | null;
  unit_price_brl: Decimal | null;
  gross_amount_brl: Decimal;
  tax_brl: Decimal;
  realized_pnl_brl: Decimal | null;
  cash_amount_brl: Decimal;
  cash_balance_after: Decimal;
  note: string | null;
  created_at: string;
}

export interface DividendItem {
  id: number; asset: AssetBrief; kind: "DIVIDEND" | "JCP" | "RENDIMENTO";
  ex_date: string; pay_date: string; pay_date_estimated: boolean;
  status: "PENDING" | "PAID" | "CANCELLED"; quantity: Decimal; amount_per_unit: Decimal; currency: string;
  expected_gross_native: Decimal; gross_brl: Decimal | null; tax_brl: Decimal | null; net_brl: Decimal | null; paid_at: string | null;
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

export interface FiProduct {
  id: number; name: string; issuer: string; product_type: string; indexer: string; rate_mode: string; rate: Decimal; rate_label: string;
  maturity_date: string; min_investment_brl: Decimal; liquidity: "DAILY" | "AT_MATURITY" | "SPECIFIC_DATES"; grace_days: number;
  liquidity_dates: string[]; early_redemption: boolean; secondary_discount_pct: Decimal; uses_mtm: boolean;
  payment_frequency: "AT_MATURITY" | "MONTHLY" | "SEMIANNUAL" | "ANNUAL"; tax_regime: "REGRESSIVE" | "EXEMPT";
  risk_level: "LOW" | "MEDIUM" | "HIGH"; fgc_covered: boolean; description: string | null; source: "TESOURO_TRANSPARENTE" | "SAMPLE"; as_of: string;
}
export interface FiFlow { on: string; kind: "COUPON" | "MATURITY"; gross: Decimal; tax: Decimal; net: Decimal }
export interface FiSimulation {
  product: { id: number; name: string; rate_label: string }; principal_brl: Decimal; total_gross_brl: Decimal; total_tax_brl: Decimal;
  total_net_brl: Decimal; profit_net_brl: Decimal; annualized_net_pct: Decimal | null; flows: FiFlow[]; assumptions: string;
}
export interface FiInvestment {
  id: number; product: { id: number; name: string; issuer: string; product_type: string; rate_label: string };
  status: "ACTIVE" | "REDEEMED" | "MATURED"; applied_on: string; maturity_date: string; principal_brl: Decimal; units: Decimal | null;
  current_gross_brl: Decimal; estimated_tax_brl: Decimal; estimated_net_brl: Decimal; interest_paid_net_brl: Decimal;
  profit_net_brl: Decimal; valuation_method: string; can_redeem: boolean; redeem_block_reason: string | null;
  redeem_net_brl: Decimal | null; next_event_date: string | null; next_event_kind: string | null; closed_on: string | null;
}
export interface FiIndexes { cdi_annual: Decimal; selic_annual: Decimal; ipca_12m: Decimal; igpm_12m: Decimal; last_cdi_date: string | null }

export interface PerfPoint {
  t: string; equity: Decimal; wealth: Decimal; cash: Decimal; assets: Decimal; fixed_income: Decimal; net_deposits: Decimal;
  return_pct: Decimal; cdi_pct: Decimal; drawdown_pct: Decimal;
}
export interface Performance {
  range: string; series: PerfPoint[];
  series_stats: { period_return_pct: Decimal | null; cdi_pct: Decimal | null; vs_cdi_pp: Decimal | null; max_drawdown_pct: Decimal | null; best_day_pct: Decimal | null; worst_day_pct: Decimal | null };
  summary: { equity_brl: Decimal; wealth_brl: Decimal; initial_brl: Decimal; pnl_brl: Decimal; total_return_pct: Decimal | null;
    diversification_score: number | null; top_position: { name: string; pct: Decimal } | null; discipline_pct: Decimal | null; positions: number; days_tracked: number };
  trades: { buys: number; sells: number; fixed_income_applications: number; closed_trades: number; wins: number; losses: number; win_rate_pct: Decimal | null;
    avg_win_brl: Decimal | null; avg_loss_brl: Decimal | null; payoff_ratio: Decimal | null; profit_factor: Decimal | null; total_realized_brl: Decimal;
    income_total_brl: Decimal; best_trade_brl: Decimal | null; best_trade_label: string | null; worst_trade_brl: Decimal | null; worst_trade_label: string | null };
  allocation: { label: string; value: Decimal; pct: Decimal }[];
  monthly: { month: string; realized: Decimal; income: Decimal; trades: number }[];
  realized_cumulative: { date: string; cumulative: Decimal }[];
  achievements: { id: string; title: string; description: string; unlocked: boolean; current: number; target: number; detail: string }[];
  insights: { tone: "good" | "warn" | "info"; text: string; lesson_id: string | null }[];
  recommended_lessons: { lesson_id: string; title: string; reason: string; review: boolean }[];
}
export interface RankEntry { rank: number; nickname: string; wealth_brl: Decimal; gain_brl: Decimal; return_pct: Decimal; is_me: boolean }
export interface Ranking { board: string; period: string; participants: number; entries: RankEntry[]; me: RankEntry | null; me_hidden: boolean; note: string }
export interface RankingSettings { show_in_ranking: boolean; nickname: string | null; default_nickname: string | null }
export interface LessonVideo { url: string; poster_url: string | null; captions_url: string | null; duration_s: number; size_bytes: number }
export interface LessonBrief { id: string; title: string; minutes: number; summary: string; completed: boolean; best_score: number | null; video_seconds: number | null }
export interface LearnModule { id: string; title: string; description: string; level: string; lessons: LessonBrief[]; completed: number; total: number; video_seconds: number }
export interface LearnOverview { modules: LearnModule[]; completed: number; total: number; percent: number; points: number; level: string; next_lesson_id: string | null; video_seconds: number; videos: number }
export type Block = [string, ...unknown[]];
export interface Lesson {
  id: string; module_id: string; module_title: string; title: string; minutes: number; blocks: Block[];
  quiz: { text: string; options: string[] }[]; completed: boolean; best_score: number | null; prev_id: string | null; next_id: string | null; video: LessonVideo | null;
}
export interface QuizResult {
  score: number; passed: boolean; pass_score: number; results: { correct: boolean; correct_index: number; explanation: string }[];
  completed: boolean; next_lesson_id: string | null; overview: LearnOverview;
}

export interface QuoteBrief { asset_id: number; price: Decimal; currency: string; price_brl: Decimal; change_pct: Decimal | null }

export interface User { id: number; email: string; name: string; created_at: string }

const TOKEN_KEY = "sim.token";

export const tokenStore = {
  get(): string | null { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set(t: string) { try { localStorage.setItem(TOKEN_KEY, t); } catch { /* ignore */ } },
  clear() { try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ } },
};

// ------------------------------------------------------------------ orçamento mensal
export type FlowKind = "INCOME" | "EXPENSE";
export type Frequency = "MONTHLY" | "QUARTERLY" | "SEMIANNUAL" | "ANNUAL";
export interface BudgetCategory { id: number; name: string; kind: FlowKind; active: boolean; is_default: boolean }
export interface BudgetItem {
  id: number; name: string; kind: FlowKind; category_id: number; category_name: string;
  planned_amount: Decimal; realized: Decimal; remaining: Decimal; recurring: boolean;
  frequency: Frequency | null; end_month: string | null; entry_count: number; capital: boolean; source: string | null;
}
export interface CategoryTotal { category_id: number | null; category_name: string; kind: FlowKind; planned: Decimal; realized: Decimal; remaining: Decimal }
export interface MonthSummary {
  ref_month: string; status: "OPEN" | "CLOSED"; opening_balance: Decimal; closing_balance: Decimal | null;
  planned_investment: Decimal; balance: Decimal; planned_income: Decimal; planned_expense: Decimal;
  realized_income: Decimal; realized_expense: Decimal; forecast_income: Decimal; forecast_expense: Decimal;
  remaining_income: Decimal; remaining_expense: Decimal; invested: Decimal; result: Decimal;
  projected_closing_balance: Decimal; free_after_investment: Decimal; capital_in: Decimal; capital_out: Decimal;
  items: BudgetItem[]; by_category: CategoryTotal[];
}
export interface ClosePreview {
  ref_month: string; next_month: string; income: Decimal; expense: Decimal; invested: Decimal; result: Decimal;
  carried_balance: Decimal; pending: string[]; shortfall: Decimal; can_close: boolean;
}
export interface BudgetOverview { account: { id: number; name: string; kind: string; balance: Decimal }; month: MonthSummary; close: ClosePreview }
export interface MonthRow {
  ref_month: string; status: "OPEN" | "CLOSED"; opening_balance: Decimal; closing_balance: Decimal | null;
  income: Decimal; expense: Decimal; invested: Decimal; result: Decimal;
}
export interface LedgerEntryOut {
  id: number; kind: FlowKind; amount: Decimal; description: string; category_id: number | null; category_name: string | null;
  entry_date: string; ref_month: string; origin: string; budget_item_id: number | null; reverses_id: number | null;
  reversed: boolean; created_at: string; capital: boolean; origin_ref: string | null;
}
export interface ItemInput {
  name: string; kind: FlowKind; category_id: number; planned_amount: string; recurring: boolean;
  frequency: Frequency; end_month: string | null;
}

// ------------------------------------------------------------------ bens e patrimônio
export type GoodCategory = "RESIDENTIAL" | "COMMERCIAL" | "LAND" | "CAR" | "MOTORCYCLE" | "INSTRUMENT" | "EQUIPMENT" | "ANTIQUE" | "COLLECTIBLE" | "OTHER";
export type Occupancy = "OWNER_OCCUPIED" | "VACANT" | "LISTED_FOR_RENT" | "RENTED";
export type AmortSystem = "PRICE" | "SAC";
export interface Listing {
  key: string; category: GoodCategory; name: string; description: string; price: Decimal; purchase_fee: Decimal;
  location: string; condition: string | null; property_type: string | null; address: string | null;
  area_m2: Decimal | null; bedrooms: number | null; suggested_rent: Decimal | null; owned: boolean;
  financing: { max_ltv_pct: Decimal; min_down_payment: Decimal; annual_rate_pct: Decimal; max_term_months: number } | null;
}
export interface Good {
  id: number; name: string; category: GoodCategory; status: "ACTIVE" | "SOLD" | "LOST"; condition: string | null;
  location: string | null; acquired_on: string; purchase_price: Decimal; acquisition_cost: Decimal; current_value: Decimal;
  unrealized_result: Decimal; occupancy: Occupancy | null; monthly_rent: Decimal | null; loan_balance: Decimal | null;
  sold_on: string | null; sale_result: Decimal | null;
}
export interface Installment {
  number: number; due_month: string; payment: Decimal; interest: Decimal; amortization: Decimal; balance_after: Decimal; status?: string | null;
}
export interface GoodDetail {
  good: Good; description: string | null;
  real_estate: { property_type: string; address: string; area_m2: Decimal; bedrooms: number | null; occupancy: Occupancy;
    monthly_rent: Decimal; rent_tax_pct: Decimal; market_rent: Decimal } | null;
  vehicle_usage_km_month: number | null;
  costs: { id: number; kind: string; name: string; amount: Decimal; frequency: Frequency; start_month: string; active: boolean }[];
  values: { ref_month: string; value: Decimal; source: string }[];
  events: { ref_month: string; type: string; description: string; amount: Decimal | null; created_at: string }[];
  loan: { principal: Decimal; down_payment: Decimal; annual_rate_pct: Decimal; term_months: number; system: AmortSystem;
    start_month: string; end_month: string; balance: Decimal; status: string; paid_installments: number;
    next_payment: Decimal | null; installments: Installment[] } | null;
  entries: { id: number; kind: string; amount: Decimal; description: string; ref_month: string; capital: boolean; origin: string }[];
  income_total: Decimal; expense_total: Decimal;
  appraisal: { estimate: Decimal; low: Decimal; high: Decimal; uncertainty_pct: Decimal };
}
export interface Simulation {
  price: Decimal; down_payment: Decimal; financed: Decimal; annual_rate_pct: Decimal; first_payment: Decimal;
  last_payment: Decimal; total_interest: Decimal; total_paid: Decimal; purchase_fee: Decimal; cash_needed_now: Decimal;
  preview: Installment[];
}
export interface SaleQuote { sale_price: Decimal; fees: Decimal; loan_payoff: Decimal; net_cash: Decimal; result: Decimal }
export interface WealthOverview {
  count: number; sold_count: number; total_value: Decimal; total_acquisition_cost: Decimal; debts: Decimal; net_worth: Decimal;
  unrealized_result: Decimal; monthly_income: Decimal; monthly_expense: Decimal; monthly_debt_service: Decimal;
  income_received_total: Decimal; expense_paid_total: Decimal;
  by_category: { category: GoodCategory; count: number; value: Decimal }[];
  series: { ref_month: string; goods_value: Decimal; debts: Decimal; net: Decimal }[];
}

// ------------------------------------------------------------------ empresas
export type Segment = string;
export interface CoRole { key: string; label: string; salary: Decimal; units: number }
export interface CoSegment {
  key: Segment; label: string; description: string; unit_label: string; price: Decimal; tax_pct: Decimal;
  roles: CoRole[]; stock: string[]; required_capital: Decimal;
}
export interface CoCatalog {
  segments: CoSegment[];
  locations: { key: string; label: string; demand: number; rent_factor: string }[];
  sizes: { key: string; label: string; demand: number; setup_factor: string }[];
}
export interface CoQuote { required_capital: Decimal; setup_cost: Decimal; monthly_fixed: Decimal; monthly_payroll: Decimal; initial_stock: Decimal; expected_units: number }
export interface Company {
  id: number; name: string; segment: Segment; segment_label: string; business_type: string; location: string; location_label: string;
  size: string; units: number; capacity_level: number; price: Decimal; reputation: number; owner_share_pct: Decimal; owner_salary: Decimal;
  auto_restock: boolean; status: string; founded_on: string; marketing_until: string | null; cash: Decimal; debts: Decimal; equity: Decimal;
  last_revenue: Decimal | null; last_net_result: Decimal | null;
}
export interface CoMonth {
  ref_month: string; demand_units: Decimal; capacity_units: Decimal; units_sold: Decimal; stockout: boolean; revenue: Decimal;
  variable_costs: Decimal; fixed_costs: Decimal; payroll: Decimal; taxes: Decimal; interest: Decimal; operating_result: Decimal;
  net_result: Decimal; cash_end: Decimal; debts_end: Decimal; equity_end: Decimal; reputation_end: number;
}
export interface CompanyDetail {
  company: Company; distributable_profit: Decimal; runway_months: Decimal | null; monthly_obligations: Decimal; loan_limit: Decimal;
  expected_demand: number; expected_capacity: number; expansion_costs: Record<string, Decimal>; roles: CoRole[];
  employees: { id: number; role: string; role_label: string; level: string; salary: Decimal; total_cost: Decimal; hours_week: number;
    productivity: Decimal; status: string; hired_on: string; terminated_on: string | null }[];
  inventory: { id: number; name: string; unit: string; quantity: Decimal; unit_cost: Decimal; value: Decimal; supplier: string;
    min_quantity: Decimal; monthly_consumption_est: Decimal; low: boolean }[];
  costs: { id: number; kind: string; name: string; amount: Decimal; active: boolean }[];
  lease: { kind: string; good_id: number | null; name: string; monthly_rent: Decimal; start_month: string } | null;
  loans: { id: number; principal: Decimal; annual_rate_pct: Decimal; term_months: number; start_month: string; balance: Decimal; status: string;
    installments: Installment[] }[];
  goods: { id: number; name: string; category: string; current_value: Decimal; status: string }[];
  months: CoMonth[];
  events: { ref_month: string; type: string; description: string; amount: Decimal | null; created_at: string }[];
  ledger: { id: number; kind: string; amount: Decimal; description: string; line: string | null; capital: boolean; ref_month: string }[];
}
export interface CoOverview {
  count: number; equity_total: Decimal; equity_user_share: Decimal; cash_total: Decimal; debts_total: Decimal;
  revenue_last_month: Decimal; expenses_last_month: Decimal; net_last_month: Decimal; companies: Company[];
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const game = gameStore.get();
  if (game && !ACCOUNT_PATHS.some((p) => path.startsWith(p))) headers.set("X-Game-Id", String(game.id));

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
  sell: (asset_id: number, body: { quantity?: string; amount_brl?: string }) =>
    request<Transaction>("/trades/sell", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ asset_id, ...body }) }),
  assets: (params: { asset_class?: string; country?: string; limit?: number }) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]));
    return request<Asset[]>(`/assets?${q}`);
  },
  quotes: (ids: number[]) => request<QuoteBrief[]>(`/assets/quotes?ids=${ids.join(",")}`),
  setRisk: (asset_id: number, stop_loss: string | null, take_profit: string | null) =>
    request<{ asset_id: number; currency: string; stop_loss: Decimal | null; take_profit: Decimal | null }>(
      `/trades/risk/${asset_id}`, { method: "PUT", body: JSON.stringify({ stop_loss, take_profit }) }),
  dividends: () => request<DividendItem[]>("/portfolio/dividends"),
  syncDividends: () => request<{ new_rights: number; paid: number }>("/portfolio/dividends/sync", { method: "POST" }),
  fiProducts: (params: Record<string, string> = {}) => request<FiProduct[]>(`/fixed-income/products?${new URLSearchParams(params)}`),
  fiIndexes: () => request<FiIndexes>("/fixed-income/indexes"),
  fiSimulate: (product_id: number, amount_brl: string) =>
    request<FiSimulation>("/fixed-income/simulate", { method: "POST", body: JSON.stringify({ product_id, amount_brl }) }),
  fiInvest: (product_id: number, amount_brl: string) =>
    request<FiInvestment>("/fixed-income/invest", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ product_id, amount_brl }) }),
  fiInvestments: () => request<FiInvestment[]>("/fixed-income/investments"),
  fiRedeem: (id: number) => request<FiInvestment>(`/fixed-income/investments/${id}/redeem`, { method: "POST" }),
  fiRefresh: () => request<{ refreshed: boolean }>("/fixed-income/refresh", { method: "POST" }),
  performance: (range: string) => request<Performance>(`/performance?range=${range}`),
  ranking: (board: string, period: string) => request<Ranking>(`/ranking?board=${board}&period=${period}`),
  rankingSettings: () => request<RankingSettings>("/ranking/settings"),
  saveRankingSettings: (show_in_ranking: boolean, nickname: string | null) =>
    request<RankingSettings>("/ranking/settings", { method: "PUT", body: JSON.stringify({ show_in_ranking, nickname }) }),
  learn: () => request<LearnOverview>("/learn"),
  lesson: (id: string) => request<Lesson>(`/learn/lessons/${id}`),
  submitQuiz: (id: string, answers: number[]) =>
    request<QuizResult>(`/learn/lessons/${id}/quiz`, { method: "POST", body: JSON.stringify({ answers }) }),
  budgetOverview: () => request<BudgetOverview>("/budget/overview"),
  budgetMonths: () => request<MonthRow[]>("/budget/months"),
  budgetMonth: (ref: string) => request<MonthSummary>(`/budget/months/${ref}`),
  budgetEntries: (ref?: string) => request<LedgerEntryOut[]>(`/budget/entries${ref ? `?ref_month=${ref}` : ""}`),
  budgetCategories: () => request<BudgetCategory[]>("/budget/categories"),
  budgetCreateCategory: (name: string, kind: FlowKind) =>
    request<BudgetCategory>("/budget/categories", { method: "POST", body: JSON.stringify({ name, kind }) }),
  budgetUpdateCategory: (id: number, body: { name?: string; active?: boolean }) =>
    request<BudgetCategory>(`/budget/categories/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  budgetAddItem: (body: ItemInput) => request<MonthSummary>("/budget/items", { method: "POST", body: JSON.stringify(body) }),
  budgetUpdateItem: (id: number, body: Partial<Omit<ItemInput, "kind" | "recurring">> & { apply_to_future?: boolean; clear_end_month?: boolean }) =>
    request<MonthSummary>(`/budget/items/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  budgetDeleteItem: (id: number, stopRecurring: boolean) =>
    request<MonthSummary>(`/budget/items/${id}?stop_recurring=${stopRecurring}`, { method: "DELETE" }),
  budgetExample: () => request<MonthSummary>("/budget/example", { method: "POST" }),
  budgetSetInvestment: (planned_investment: string) =>
    request<MonthSummary>("/budget/months/current", { method: "PATCH", body: JSON.stringify({ planned_investment }) }),
  budgetCreateEntry: (body: { kind: FlowKind; amount: string; description: string; category_id?: number; budget_item_id?: number }) =>
    request<LedgerEntryOut>("/budget/entries", { method: "POST", body: JSON.stringify({ ...body, idempotency_key: crypto.randomUUID() }) }),
  budgetReverseEntry: (id: number) => request<LedgerEntryOut>(`/budget/entries/${id}/reverse`, { method: "POST" }),
  budgetClose: (ref_month: string) =>
    request<BudgetOverview>("/budget/close", { method: "POST", body: JSON.stringify({ ref_month, confirm: true }) }),
  wealth: () => request<WealthOverview>("/goods/overview"),
  market: (p: Record<string, string> = {}) => request<Listing[]>(`/goods/market?${new URLSearchParams(p)}`),
  simulateFinancing: (body: { listing_key: string; down_payment: string; term_months: number; system: AmortSystem }) =>
    request<Simulation>("/goods/market/simulate", { method: "POST", body: JSON.stringify(body) }),
  buyGood: (body: { listing_key: string; idempotency_key: string; financed: boolean; down_payment?: string; term_months?: number;
    system?: AmortSystem; extra_costs?: string; usage_km_month?: number }) =>
    request<GoodDetail>("/goods/purchase", { method: "POST", body: JSON.stringify(body) }),
  myGoods: (p: Record<string, string> = {}) => request<Good[]>(`/goods?${new URLSearchParams(p)}`),
  good: (id: number) => request<GoodDetail>(`/goods/${id}`),
  saleQuote: (id: number, salePrice?: string) =>
    request<SaleQuote>(`/goods/${id}/sale-quote${salePrice ? `?sale_price=${encodeURIComponent(salePrice)}` : ""}`),
  sellGood: (id: number, body: { sale_price?: string; extra_fees?: string }) =>
    request<GoodDetail>(`/goods/${id}/sell`, { method: "POST", body: JSON.stringify(body) }),
  writeOffGood: (id: number, reason: string) =>
    request<GoodDetail>(`/goods/${id}/write-off`, { method: "POST", body: JSON.stringify({ reason }) }),
  setOccupancy: (id: number, body: { mode: Occupancy; monthly_rent?: string; end_recurring_item_ids?: number[] }) =>
    request<GoodDetail>(`/goods/${id}/occupancy`, { method: "POST", body: JSON.stringify(body) }),
  housingCandidates: () => request<{ id: number; name: string; amount: Decimal | null }[]>("/goods/housing-candidates"),
  goodMaintenance: (id: number, amount: string, description: string) =>
    request<GoodDetail>(`/goods/${id}/maintenance`, { method: "POST", body: JSON.stringify({ amount, description, idempotency_key: crypto.randomUUID() }) }),
  addGoodCost: (id: number, body: { kind: string; name: string; amount: string; frequency: Frequency }) =>
    request<GoodDetail>(`/goods/${id}/costs`, { method: "POST", body: JSON.stringify(body) }),
  updateGoodCost: (id: number, costId: number, body: { amount?: string; active?: boolean }) =>
    request<GoodDetail>(`/goods/${id}/costs/${costId}`, { method: "PATCH", body: JSON.stringify(body) }),
  coCatalog: () => request<CoCatalog>("/companies/catalog"),
  coQuote: (segment: string, location: string, size: string) =>
    request<CoQuote>("/companies/quote", { method: "POST", body: JSON.stringify({ segment, location, size }) }),
  coOverview: () => request<CoOverview>("/companies/overview"),
  coCreate: (body: { name: string; segment: string; location: string; size: string; capital: string; owner_share_pct: string; business_type: string }) =>
    request<CompanyDetail>("/companies", { method: "POST", body: JSON.stringify(body) }),
  company: (id: number) => request<CompanyDetail>(`/companies/${id}`),
  coContribute: (id: number, amount: string) =>
    request<CompanyDetail>(`/companies/${id}/contribute`, { method: "POST", body: JSON.stringify({ amount, idempotency_key: crypto.randomUUID() }) }),
  coDistribute: (id: number, amount: string) =>
    request<CompanyDetail>(`/companies/${id}/distribute`, { method: "POST", body: JSON.stringify({ amount, idempotency_key: crypto.randomUUID() }) }),
  coSettings: (id: number, body: { price?: string; owner_salary?: string; auto_restock?: boolean }) =>
    request<CompanyDetail>(`/companies/${id}/settings`, { method: "PATCH", body: JSON.stringify(body) }),
  coHire: (id: number, role: string, level: string, confirm_risk: boolean) =>
    request<CompanyDetail>(`/companies/${id}/employees`, { method: "POST", body: JSON.stringify({ role, level, confirm_risk }) }),
  coFire: (id: number, employeeId: number) => request<CompanyDetail>(`/companies/${id}/employees/${employeeId}`, { method: "DELETE" }),
  coStock: (id: number, item_id: number, quantity: string) =>
    request<CompanyDetail>(`/companies/${id}/stock`, { method: "POST", body: JSON.stringify({ item_id, quantity, idempotency_key: crypto.randomUUID() }) }),
  coExpand: (id: number, kind: string) => request<CompanyDetail>(`/companies/${id}/expand`, { method: "POST", body: JSON.stringify({ kind }) }),
  coLease: (id: number, body: { kind: string; good_id?: number; monthly_rent?: string }) =>
    request<CompanyDetail>(`/companies/${id}/lease`, { method: "POST", body: JSON.stringify(body) }),
  coLoan: (id: number, amount: string, term_months: number) =>
    request<CompanyDetail>(`/companies/${id}/loans`, { method: "POST", body: JSON.stringify({ amount, term_months }) }),
  coBuyGood: (id: number, listing_key: string) =>
    request<CompanyDetail>(`/companies/${id}/goods/purchase`, { method: "POST", body: JSON.stringify({ listing_key, idempotency_key: crypto.randomUUID() }) }),
  portfolio: () => request<PortfolioSummary>("/portfolio"),
  transactions: (limit = 20) => request<Transaction[]>(`/portfolio/transactions?limit=${limit}`),
};
