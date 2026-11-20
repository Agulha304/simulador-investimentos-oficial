// Etapas 4-6: vida pessoal, economia, partida/progressão. Valores monetários chegam como string (Decimal).
import { request } from "./api";

export interface Attrs { health: number; wellbeing: number; quality: number; satisfaction: number; social: number; financial_stability: number; free_hours_left: number; free_hours_total: number }
export interface Rel {
  role: "MOTHER" | "FATHER" | "BROTHER" | "SISTER" | null; alive: boolean;
  gender: "M" | "F"; compat_bonus: number; finance_label: string; person_id: number; name: string; age: number; personality: string; interests: string[]; occupation: string; income: string;
  assets: string; debts: string; wants_children: number; stage: string; affinity: number; trust: number; compatibility: number;
  since_month: string; stage_since: string; finance_mode: "SEPARATE" | "SHARED"; contribution_pct: string;
}
export interface Kid { id: number; name: string; age_years: number; health: number; development: number; school_kind: "PUBLIC" | "PRIVATE"; daycare: boolean; activities: boolean; active: boolean; monthly_reference_cost: number; needs: string[] }
export interface FamExpense { key: string; name: string; kind: "EXPENSE" | "INCOME"; category: string; origin: string; amount: string; child_id: number | null }
export interface CareerField { key: string; label: string; emoji: string; outlook: string; growth_pct: number; start: number; degree: string; months: number; cost: number; premium_pct: number; hours: number }
export interface Career {
  field: string | null; label: string | null; outlook: string | null; growth_pct: number | null; since: string | null; next_raise: string | null;
  salary: string; degrees: string[]; pending: { field: string; factor: number; degree: boolean } | null;
  studying: { field: string; name: string; progress: number; total: number; cost: number } | null; fields: CareerField[];
}
export interface Life {
  month: string; character: { name: string; age_years: number; gender: string; interested_in: string }; career: Career; attributes: Attrs; choices: Record<string, string>;
  options: Record<string, string[]>; housing: { quality: number; description: string; kind: string; monthly_cost: string; pending: { kind: string; monthly_cost: string; effective_month: string } | null };
  pregnancy_due_month: string | null; relationships: Rel[]; children: Kid[]; expenses: FamExpense[]; family_expense_total: string;
  activities: { key: string; label: string; cost: number; hours: number }[]; interactions: { key: string; label: string; cost: number; hours: number }[];
  history: { month: string; kind: string; text: string }[];
  result?: { cost?: string; met?: string | null; story?: string; person_id?: number };
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
export interface Scenario { age?: number; key: string; name: string; description: string; cash: number; salary: number; expenses: { category: string; name: string; amount: number; indexed: string | null }[]; goals: { key: string; title: string; kind: string }[]; challenges: string[]; partner: boolean; children: number }
export interface GameInfo { mode: string; scenario: string | null; started: boolean; dynamic: boolean; seed: number; config: Record<string, number>; scenarios: Scenario[]; goal_templates: { key: string; kind: string; title: string; metric: string; default_target: number }[] }
export interface Overview {
  age: number | null; ended: string | null; overdraft: string;
  month: string; mode: string; scenario: string | null; dynamic_economy: boolean; cash: string; monthly_income: string; monthly_expense: string;
  net_worth: string; debts: string; invested: string; passive_income: string; emergency_months: number; companies: { id: number; name: string; segment: string }[];
  family: { partner: string | null; children: number; members: number }; wellbeing: Omit<Attrs, "financial_stability" | "free_hours_left" | "free_hours_total"> | null;
  economy: { inflation: string; interest: string; unemployment: string; growth: string; confidence: string } | null;
  goals: Goal[]; pending_events: number; pending_life_decisions: number; last_report_month: string | null; achievements_unlocked: number;
}
export interface Debt {
  cash: string; overdraft: string; balance: string; overdraft_limit: string; overdraft_rate: string; loan_rate: string; credit_limit: string;
  min_term: number; max_term: number; total_debt: string; ended: string | null;
  loans: { id: number; principal: string; balance: string; rate: string; term: number; status: string; start: string; next_payment: string | null; next_due: string | null }[];
}
export interface HousingOffer { available: boolean; budget: string; rent?: string; quality?: number; title?: string; tier?: string; description?: string; effect?: string; message: string }
export interface PlanRow { key: string; label: string; target_pct: number; target_amount: string; current: string; missing: string; filled_pct: number; month_pct: number; month_amount: string }
export interface InvestPlan {
  profile: string; profile_label: string; profile_text: string; quiz_score: number | null; wanted: string[]; customized: boolean; goal_total: string; goal_is_custom: boolean;
  invested_now: string; recommended: { amount: string; surplus: string; share_pct: number; reserve_mode: boolean; reason: string }; planned_investment: string;
  rows: PlanRow[]; classes: { key: string; label: string }[]; profiles: { key: string; label: string; text: string; alloc: Record<string, number> }[];
}
export interface CareerPerf {
  series: { month: string; net_worth: number; net_worth_real: number; income: number; expense: number; result: number; debts: number; savings_rate: number | null;
    health: number | null; wellbeing: number | null; satisfaction: number | null }[];
  summary: { net_worth: number; start_net_worth: number | null; net_worth_change: number | null; months_played: number; avg_savings_rate_12m: number | null;
    emergency_months: number; debts: number; positive_months: number; passive_income: number; age: number | null; health: number | null; wellbeing: number | null; satisfaction: number | null };
  career: { field: string | null; label: string | null; degrees: string[]; studying: string | null; cost_of_living_change_pct: number | null; wage_index_change_pct: number | null };
  insights: { tone: "good" | "warn" | "info"; text: string; lesson_id: string | null }[];
  recommended_lessons: { lesson_id: string; title: string; reason: string; review: boolean }[];
  economy_dynamic: boolean; ended: string | null;
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
  age?: number | null; ended?: string | null; ended_month?: string | null;
  market_date?: string; start_date?: string; at_present?: boolean; mode?: string | null; scenario?: string | null; started?: boolean; month?: string | null;
}
export interface Hub { account: { name: string; email: string }; games: GameSummary[]; achievements: Achievement[]; lessons: { done: number; total: number } }

const put = (body: unknown) => ({ method: "PUT", body: JSON.stringify(body) });
const post = (body: unknown = {}) => ({ method: "POST", body: JSON.stringify(body) });

export interface AccountCategory { id: number; kind: "INCOME" | "EXPENSE"; name: string; active: boolean }

export const sim = {
  searchHousing: (budget: string) => request<HousingOffer>("/life/housing/search", post({ budget })),
  investPlan: () => request<InvestPlan>("/invest-plan"),
  investSettings: (b: { profile?: string; wanted?: string[]; alloc?: Record<string, number>; goal_total?: string }) => request<InvestPlan>("/invest-plan", put(b)),
  investQuiz: () => request<{ questions: { text: string; options: string[] }[] }>("/invest-plan/quiz"),
  investQuizSubmit: (answers: number[]) => request<InvestPlan>("/invest-plan/quiz", post({ answers })),
  investApply: () => request<InvestPlan>("/invest-plan/apply", post()),
  debt: () => request<Debt>("/debt"),
  takeLoan: (amount: string, term_months: number) => request<Debt>("/debt/loans", post({ amount, term_months })),
  prepayLoan: (id: number) => request<Debt>(`/debt/loans/${id}/prepay`, post()),
  careerPerformance: () => request<CareerPerf>("/progress/performance"),
  accountCategories: () => request<AccountCategory[]>("/account/categories"),
  addAccountCategory: (name: string, kind: string) => request<AccountCategory>("/account/categories", post({ name, kind })),
  patchAccountCategory: (id: number, body: { name?: string; active?: boolean }) =>
    request<AccountCategory>(`/account/categories/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  hub: () => request<Hub>("/games"),
  createGame: (kind: string, name: string, start_date?: string) => request<GameSummary>("/games", post({ kind, name, start_date })),
  game_: (id: number) => request<GameSummary>(`/games/${id}`),
  renameGame: (id: number, name: string) => request<GameSummary>(`/games/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  archiveGame: (id: number) => request<GameSummary>(`/games/${id}/archive`, post()),
  trainAdvance: (id: number, months: number) => request<GameSummary>(`/games/${id}/training/advance`, post({ months })),
  trainDate: (id: number, date: string) => request<GameSummary>(`/games/${id}/training/date`, post({ date })),
  trainMoney: (id: number, amount: string) => request<GameSummary>(`/games/${id}/training/money`, post({ amount })),
  life: () => request<Life>("/life"),
  lifeCharacter: (name: string, age_years: number, gender?: string, interested_in?: string) => request<Life>("/life/character", put({ name, age_years, gender, interested_in })),
  lifeCareerChange: (field: string) => request<Life>("/life/career/change", post({ field })),
  lifeDegree: (field: string) => request<Life>("/life/degree", post({ field })),
  lifeDegreeDrop: () => request<Life>("/life/degree", { method: "DELETE" }),
  decisions: () => request<{ month: string; pending: EcoEvent[] }>("/economy/decisions"),
  gameSimParams: (id: number) => request<{ game: string; params: SimParams }>(`/games/${id}/sim-params`),
  putGameSimParams: (id: number, p: Partial<SimParams>) => request<{ game: string; params: SimParams }>(`/games/${id}/sim-params`, put(p)),
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
