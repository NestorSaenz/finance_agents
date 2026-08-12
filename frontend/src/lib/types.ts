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
}

export interface BudgetStatusItem {
  budget: { id: string; name: string; category: string | null; amount: string };
  spent: string;
  remaining: string;
  percentage: number;
  alert_triggered: boolean;
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
  next_payment_date: string;
}

export interface CreditCardStatusList {
  cards: CreditCardStatusItem[];
  total_limit: string;
  total_balance: string;
  total_available: string;
}

export interface CardPaymentItem {
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
}

export interface OnboardingPayload {
  display_name?: string;
  monthly_income?: number;
  savings_goal_percentage?: number;
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
