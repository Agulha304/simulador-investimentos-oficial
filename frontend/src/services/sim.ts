// Etapas 4-6: vida pessoal, economia, partida/progressão. Valores monetários chegam como string (Decimal).
import { request } from "./api";

export interface Attrs { health: number; wellbeing: number; quality: number; satisfaction: number; social: number; financial_stability: number; free_hours_left: number; free_hours_total: number }
export interface Rel {
  person_id: number; name: string; age: number; personality: string; interests: string[]; occupation: string; income: string;
  assets: string; debts: string; wants_children: number; stage: string; affinity: number; trust: number; compatibility: number;
  since_month: string; stage_since: string; finance_mode: "SEPARATE" | "SHARED"; contribution_pct: string;
}
export interface Kid { id: number; name: string; age_years: number; health: number; development: number; school_kind: "PUBLIC" | "PRIVATE"; daycare: boolean; activities: boolean; active: boolean; monthly_reference_cost: number; needs: string[] }
export interface FamExpense { key: string; name: string; kind: "EXPENSE" | "INCOME"; category: string; origin: string; amount: string; child_id: number | null }
export interface Life {
  month: string; character: { name: string; age_years: number }; attributes: Attrs; choices: Record<string, string>;
  options: Record<string, string[]>; housing: { kind: string; monthly_cost: string; pending: { kind: string; monthly_cost: string; effective_month: string } | null };
  pregnancy_due_month: string | null; relationships: Rel[]; children: Kid[]; expenses: FamExpense[]; family_expense_total: string;
  activities: { key: string; label: string; cost: number; hours: number }[]; interactions: { key: string; label: string; cost: number; hours: number }[];
  pending_decisions: { key: string; text: string }[]; history: { month: string; kind: string; text: string }[];
  result?: { cost: string; met: string | null };
}
export interface EcoState {
  month: string; inflation: string; interest: string; unemployment: string; growth: string; demand: string; confidence: string;
  monthly_changes: Record<string, number>; indices: Record<string, number>;
  fx: number | null; credit: number | null; liquidity: number | null; business_conf: number | null; household_debt: number | null;
  firm_debt: number | null; default_rate: number | null; wage_growth: number | null; regime: string | null;
  class_index: Record<string, number> | null; general_inflation_month: number | null;
}
export interface Crisis {
  id: number; type: string; label: string; start_month: string; end_month: string | null; status: string; phase: string; intensity: number; peak: number;
  sectors: Record<string, number>; assets: Record<string, number>; triggers: Record<string, number>; path: { m: string; i: number; phase: string }[];
}
export interface SimParams { volatility: number; event_frequency: number; crisis_frequency: number; crisis_severity: number; shock_scale: number }
export interface EcoEvent {
  id: number; key: string; name: string; description: string; category: string; scope: string; sector: string | null; positive: boolean;
  intensity: number; start_month: string; end_month: string; status: string; choice: string | null; outcome: string | null;
  options?: { key: string; label: string; hint: string; cost: number }[];
}
export interface Economy { month: string; dynamic: boolean; seed: number; state: EcoState | null; history: EcoState[]; categories: { key: string; label: string }[]; params: SimParams; crises: Crisis[]; pending: EcoEvent[]; active: EcoEvent[]; past: EcoEvent[] }
export interface Goal { id: number; key: string; kind: string; title: string; description: string; metric_label: string; target: string; current: string; streak: number; sustain_months: number; status: string; origin: string; progress: number; done_month: string | null }
export interface Achievement { key: string; name: string; description: string; unlocked: boolean; unlocked_month: string | null }
export interface Scenario { key: string; name: string; description: string; cash: number; salary: number; expenses: { category: string; name: string; amount: number; indexed: string | null }[]; goals: { key: string; title: string; kind: string }[]; challenges: string[]; partner: boolean; children: number }
export interface GameInfo { mode: string; scenario: string | null; started: boolean; dynamic: boolean; seed: number; config: Record<string, number>; scenarios: Scenario[]; goal_templates: { key: string; kind: string; title: string; metric: string; default_target: number }[] }
export interface Overview {
  month: string; mode: string; scenario: string | null; dynamic_economy: boolean; cash: string; monthly_income: string; monthly_expense: string;
  net_worth: string; debts: string; invested: string; passive_income: string; emergency_months: number; companies: { id: number; name: string; segment: string }[];
  family: { partner: string | null; children: number; members: number }; wellbeing: Omit<Attrs, "financial_stability" | "free_hours_left" | "free_hours_total"> | null;
  economy: { inflation: string; interest: string; unemployment: string; growth: string; confidence: string } | null;
  goals: Goal[]; pending_events: number; pending_life_decisions: number; last_report_month: string | null; achievements_unlocked: number;
}
export interface MonthReport {
  month: string; income: number; expense: number; result: number; invested: number; closing_balance: number; net_worth: number; net_worth_open: number | null;
  net_worth_change: number | null; debts: number; expense_by_category: Record<string, number>; family_expense: number; personal_expense: number;
  companies: { company_id: number; name: string; revenue: number; net_result: number }[]; company_profit: number;
  family_changes: { kind: string; text: string }[]; events: { name: string; category: string; status: string; start: string; end: string }[];
  economy: { inflation: number; interest: number; unemployment: number; growth: number; demand: number; confidence: number } | null;
  achievements: { key: string; name: string }[]; goals_done: { key: string; title: string }[];
  real?: { cpi: number; purchasing_power: number; income_real: number; expense_real: number; net_worth_real: number; wage_index: number; cost_of_living_12m: number | null };
}
export interface AnnualReport {
  year: number; months: number; complete: boolean; net_worth_start: number; net_worth_end: number; net_worth_change: number; income: number; expense: number;
  invested: number; company_profit: number; debts_start: number; debts_end: number; personal_change: Record<string, number> | null;
  events: { name: string; month: string }[]; family_changes: { kind: string; text: string; month: string }[];
  achievements: { key: string; name: string }[]; goals_done: { key: string; title: string }[]; monthly: { month: string; income: number; expense: number; result: number; net_worth: number }[];
  real: { income_real: number; expense_real: number; cpi_start: number; cpi_end: number; cost_of_living_change_pct: number; purchasing_power_end: number; net_worth_real_end: number; wage_index_change_pct: number } | null;
}

export interface GameSummary {
  id: number; kind: "LIFE" | "TRAINING"; name: string; status: string; created_at: string; last_played_at: string; equity_brl: string | null;
  market_date?: string; start_date?: string; at_present?: boolean; mode?: string | null; scenario?: string | null; started?: boolean; month?: string | null;
}
export interface Hub { account: { name: string; email: string }; games: GameSummary[]; achievements: Achievement[]; lessons: { done: number; total: number } }

const put = (body: unknown) => ({ method: "PUT", body: JSON.stringify(body) });
const post = (body: unknown = {}) => ({ method: "POST", body: JSON.stringify(body) });

export const sim = {
  hub: () => request<Hub>("/games"),
  createGame: (kind: string, name: string, start_date?: string) => request<GameSummary>("/games", post({ kind, name, start_date })),
  game_: (id: number) => request<GameSummary>(`/games/${id}`),
  renameGame: (id: number, name: string) => request<GameSummary>(`/games/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  archiveGame: (id: number) => request<GameSummary>(`/games/${id}/archive`, post()),
  trainAdvance: (id: number, months: number) => request<GameSummary>(`/games/${id}/training/advance`, post({ months })),
  trainDate: (id: number, date: string) => request<GameSummary>(`/games/${id}/training/date`, post({ date })),
  trainMoney: (id: number, amount: string) => request<GameSummary>(`/games/${id}/training/money`, post({ amount })),
  life: () => request<Life>("/life"),
  lifeCharacter: (name: string, age_years: number) => request<Life>("/life/character", put({ name, age_years })),
  lifeChoices: (c: Record<string, string>) => request<Life>("/life/choices", put(c)),
  lifeActivity: (key: string) => request<Life>("/life/activities", post({ key })),
  lifeInteract: (id: number, key: string) => request<Life>(`/life/people/${id}/interact`, post({ key })),
  lifeRelationship: (id: number, action: string) => request<Life>(`/life/people/${id}/relationship`, post({ action })),
  lifeFinances: (id: number, mode: string, contribution_pct?: string) => request<Life>(`/life/people/${id}/finances`, put({ mode, contribution_pct })),
  lifePlanChild: () => request<Life>("/life/children/plan", post()),
  lifeChild: (id: number, body: Partial<Pick<Kid, "school_kind" | "daycare" | "activities">>) => request<Life>(`/life/children/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  lifeMove: (kind: string, monthly_cost: string) => request<Life>("/life/move", post({ kind, monthly_cost })),
  economy: () => request<Economy>("/economy"),
  ecoParams: (p: Partial<SimParams>) => request<SimParams>("/economy/params", put(p)),
  ecoDecide: (id: number, option: string) => request<{ event: EcoEvent }>(`/economy/events/${id}/decide`, post({ option })),
  game: () => request<GameInfo>("/game"),
  gameStart: (body: unknown) => request<{ mode: string }>("/game/start", post(body)),
  overview: () => request<Overview>("/progress/overview"),
  goals: () => request<Goal[]>("/progress/goals"),
  addGoal: (template: string, target?: string, sustain_months?: number) => request<Goal>("/progress/goals", post({ template, target, sustain_months })),
  achievements: () => request<Achievement[]>("/progress/achievements"),
  reports: () => request<{ month: string; income: number; expense: number; result: number; net_worth: number }[]>("/progress/reports"),
  report: (ym: string) => request<MonthReport>(`/progress/reports/${ym}`),
  latestReport: () => request<MonthReport>("/progress/reports/latest"),
  annual: (year: number) => request<AnnualReport>(`/progress/reports/annual/${year}`),
};
