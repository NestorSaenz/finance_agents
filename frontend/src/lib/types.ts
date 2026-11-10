// Types mirroring the backend `/api/v1` contract. Keep in sync with the API DTOs.

export interface SessionResponse {
  access_token: string;
  refresh_token: string;
  user_id: string;
  email: string | null;
}

export interface SignupPayload {
  email: string;
  password: string;
  full_name?: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface ChatRequest {
  message: string;
  session_id?: string | null;
  /** Base64-encoded image (no data: prefix) for spreadsheet/receipt ingestion. */
  image?: string | null;
  image_mime_type?: string | null;
}

export interface ChatResponse {
  response: string;
  session_id: string;
  agent_used: string | null;
}

export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string; // ISO 8601 timestamp set client-side when the message appears
}

export interface AuthUser {
  userId: string;
  email: string | null;
}

export type SummaryPeriod = "este_mes" | "mes_pasado" | "todo";

export interface CategorySpending {
  category: string;
  amount: string;
  percentage: number;
}

export interface SpendingSummary {
  period: string;
  total_income: string;
  total_expenses: string;
  balance: string;
  by_category: CategorySpending[];
  credit_expenses: string;
  cash_expenses: string;
  // Added by GET /analysis/summary. All optional: older payloads omit them
  // (then goal_saved = 0 and total_spent = total_expenses).
  /** Gross aportes of the period that count as gasto. */
  goal_saved?: string;
  /** Gross retiros (informational; not income). */
  goal_withdrawn?: string;
  /** total_expenses (consumo) + goal_saved. */
  total_spent?: string;
  /** ISO date: only aportes dated on/after it count as gasto. */
  goal_spending_from?: string | null;
}

export interface BudgetStatusItem {
  budget: {
    id: string;
    name: string;
    category: string | null;
    amount: string;
    /** Additive: older payloads omit it (backend default is monthly). */
    period_type?: "weekly" | "monthly" | "yearly";
  };
  spent: string;
  /** Part of `spent` that comes from recurring (fixed) expenses. Additive: older
   *  backends omit it. */
  spent_fixed?: string;
  remaining: string;
  percentage: number;
  alert_triggered: boolean;
  period_start: string;
  period_end: string;
}

export interface BudgetStatusList {
  statuses: BudgetStatusItem[];
  total_budgeted: string;
  total_spent: string;
}

export interface Goal {
  id: string;
  name: string;
  target_amount: string;
  current_amount: string;
  status: "active" | "paused" | "completed" | "cancelled";
}

export interface GoalList {
  goals: Goal[];
  total: number;
  /** Total contributed to goals within the requested period (Decimal serialized as string). */
  total_contributed: string;
}

/** One goal's monthly plan vs what was contributed (GET /goals/plan-status). */
export interface GoalPlanStatus {
  goal_id: string;
  goal_name: string;
  /** ISO-4217 currency of the goal. */
  currency: string;
  /** "YYYY-MM". */
  month: string;
  planned: string;
  /** The plan capped at what the goal still lacked — use it for "faltan". */
  effective_planned: string;
  /** Gross contributions of the month (withdrawals are NOT netted). */
  contributed_gross: string;
  withdrawn: string;
  remaining: string;
  percentage: number;
  is_met: boolean;
  goal_completed: boolean;
}

/** Totals are keyed by currency and never mixed. */
export interface GoalPlanStatusList {
  statuses: GoalPlanStatus[];
  total_planned: Record<string, string>;
  total_effective_planned: Record<string, string>;
  total_saved: Record<string, string>;
  total_withdrawn: Record<string, string>;
}

/** One goal in one month of the history (GET /goals/monthly). */
export interface GoalMonthLine {
  goal_id: string;
  goal_name: string;
  currency: string;
  /** "YYYY-MM". */
  month: string;
  /** null = no plan that month. */
  planned: string | null;
  /** The plan capped at what the goal still lacked (same rule as plan-status).
   *  Additive: absent/null on older backends, then `planned` is used. */
  effective_planned?: string | null;
  saved: string;
  withdrawn: string;
  /** Accumulated at the close of the month. */
  cumulative: string;
}

export interface GoalMonthlyHistory {
  lines: GoalMonthLine[];
}

export interface AccumulatedSurplus {
  /** Free cash accumulated up to the period's month-end (Decimal serialized as string). */
  accumulated_surplus: string;
}

export interface CreditCardStatusItem {
  card: {
    id: string;
    name: string;
    credit_limit: string;
    cutoff_day: number;
    payment_day: number;
  };
  cycle_start: string;
  cycle_end: string;
  spent_cycle: string;
  balance: string;
  available: string;
  utilization: number;
  /** Next payment due on/after today; may settle an already-closed statement. */
  next_payment_date: string;
  /** Statement settled on next_payment_date. Null in a historical (month) view. */
  statement_start: string | null;
  statement_end: string | null;
  /** Amount due on next_payment_date; null while that statement is still open
   *  (or in a historical view). */
  statement_amount: string | null;
  /** Unpaid debt whose due date already passed; only set when next_payment_date
   *  belongs to the still-open cycle. */
  overdue_amount: string | null;
}

export interface CreditCardStatusList {
  cards: CreditCardStatusItem[];
  total_limit: string;
  total_balance: string;
  total_available: string;
}

export interface CardPaymentItem {
  card_id: string;
  card_name: string;
  amount: string;
  payment_date: string;
}

export interface CardPaymentsList {
  payments: CardPaymentItem[];
  total: string;
}

export interface GoalContributionItem {
  goal_name: string;
  amount: string;
  contribution_date: string;
}

export interface GoalContributionsList {
  contributions: GoalContributionItem[];
  total: string;
}

export interface Transaction {
  id: string;
  amount: string;
  description: string;
  transaction_type: "income" | "expense";
  category: string;
  payment_method: "credito" | "efectivo" | null;
  card_id: string | null; // credit card this charge belongs to, if any
  transaction_date: string;
  budget_date: string; // month this charge hits the budget (credit: payment date)
  // Set only on a materialized recurring occurrence; a fixed bill never counts
  // toward a budget's "spent" (mirrors the backend's migration 014 exclusion).
  recurring_id: string | null;
  created_at: string;
}

export interface TransactionList {
  transactions: Transaction[];
  total: number;
  page: number;
  page_size: number;
}

export interface Recurring {
  id: string;
  description: string;
  amount: string;
  transaction_type: "income" | "expense";
  category: string | null;
  payment_method: string | null;
  day_of_month: number;
  next_run_date: string;
  active: boolean;
}

export interface RecurringList {
  recurring: Recurring[];
  total: number;
}

export interface RecurringCreatePayload {
  description: string;
  amount: number;
  transaction_type: "income" | "expense";
  day_of_month: number;
  category?: string;
}

export interface UserProfile {
  display_name: string | null;
  monthly_income: string | null;
  savings_goal_percentage: string | null;
  onboarding_completed: boolean;
  /** ISO-4217 currency code the user's amounts are formatted in (defaults to "COP"). */
  currency: string;
  /** IANA timezone name (e.g. "America/Bogota"). */
  timezone: string | null;
}

export interface OnboardingPayload {
  display_name?: string;
  monthly_income?: number;
  savings_goal_percentage?: number;
  /** ISO-4217 currency code chosen during onboarding. */
  currency?: string;
  /** IANA timezone auto-detected from the browser (e.g. "America/Bogota"). */
  timezone?: string;
}

export interface BudgetCreatePayload {
  name: string;
  amount: number;
  category: string;
  start_date: string; // ISO date (YYYY-MM-DD)
}

export interface CreditCardCreatePayload {
  name: string;
  credit_limit: number;
  cutoff_day: number;
  payment_day: number;
}
