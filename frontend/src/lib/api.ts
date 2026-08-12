// Single typed API client. Components never call fetch directly — they go
// through here so error handling, base path, and auth headers stay consistent.

import type {
  AccumulatedSurplus,
  BudgetCreatePayload,
  BudgetStatusList,
  CardPaymentsList,
  ChatRequest,
  ChatResponse,
  CreditCardCreatePayload,
  CreditCardStatusList,
  GoalList,
  LoginPayload,
  OnboardingPayload,
  RecurringCreatePayload,
  RecurringList,
  SessionResponse,
  SignupPayload,
  SpendingSummary,
  TransactionList,
  UserProfile,
} from "./types";

const BASE = "/api/v1"; // same-origin; Next rewrites proxy this to the backend.

/** Error carrying the HTTP status so callers can react (e.g. 401 -> logout). */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  token?: string | null;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, token } = options;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "No se pudo conectar con el servidor. Revisa tu conexión.");
  }

  if (!res.ok) {
    throw new ApiError(res.status, await extractErrorMessage(res));
  }
  return (await res.json()) as T;
}

async function extractErrorMessage(res: Response): Promise<string> {
  try {
    const data: unknown = await res.json();
    if (data && typeof data === "object" && "message" in data) {
      const message = (data as { message?: unknown }).message;
      if (typeof message === "string") return message;
    }
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
  } catch {
    /* fall through to a generic message */
  }
  if (res.status === 401) return "Credenciales inválidas o sesión expirada.";
  return "Ocurrió un error. Inténtalo de nuevo.";
}

export const api = {
  signup: (payload: SignupPayload): Promise<SessionResponse> =>
    request("/auth/signup", { method: "POST", body: payload }),

  login: (payload: LoginPayload): Promise<SessionResponse> =>
    request("/auth/login", { method: "POST", body: payload }),

  refresh: (refreshToken: string): Promise<SessionResponse> =>
    request("/auth/refresh", {
      method: "POST",
      body: { refresh_token: refreshToken },
    }),

  chat: (payload: ChatRequest, token: string | null): Promise<ChatResponse> =>
    request("/chat", { method: "POST", body: payload, token }),

  spendingSummary: (
    period: string,
    token: string | null,
  ): Promise<SpendingSummary> =>
    request(`/transactions/summary?period=${encodeURIComponent(period)}`, { token }),

  transactions: (
    period: string,
    token: string | null,
  ): Promise<TransactionList> =>
    request(`/transactions?period=${encodeURIComponent(period)}`, { token }),

  budgetStatus: (token: string | null): Promise<BudgetStatusList> =>
    request("/budgets/status", { token }),

  goals: (period: string | undefined, token: string | null): Promise<GoalList> =>
    request(
      period ? `/goals?period=${encodeURIComponent(period)}` : "/goals",
      { token },
    ),

  cardsStatus: (
    period: string,
    token: string | null,
  ): Promise<CreditCardStatusList> =>
    request(`/cards/status?period=${encodeURIComponent(period)}`, { token }),

  cardPayments: (
    period: string,
    token: string | null,
  ): Promise<CardPaymentsList> =>
    request(`/cards/payments?period=${encodeURIComponent(period)}`, { token }),

  excedente: (
    period: string,
    token: string | null,
  ): Promise<AccumulatedSurplus> =>
    request(`/analysis/excedente?period=${encodeURIComponent(period)}`, { token }),

  createCard: (payload: CreditCardCreatePayload, token: string | null): Promise<unknown> =>
    request("/cards", { method: "POST", body: payload, token }),

  profile: (token: string | null): Promise<UserProfile> =>
    request("/users/me/profile", { token }),

  completeOnboarding: (
    payload: OnboardingPayload,
    token: string | null,
  ): Promise<UserProfile> =>
    request("/users/me/onboarding", { method: "POST", body: payload, token }),

  createBudget: (payload: BudgetCreatePayload, token: string | null): Promise<unknown> =>
    request("/budgets", { method: "POST", body: payload, token }),

  recurring: (token: string | null): Promise<RecurringList> =>
    request("/recurring", { token }),

  createRecurring: (
    payload: RecurringCreatePayload,
    token: string | null,
  ): Promise<unknown> =>
    request("/recurring", { method: "POST", body: payload, token }),
};
