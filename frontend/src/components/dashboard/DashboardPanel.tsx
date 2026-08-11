"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, X } from "lucide-react";

import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import type {
  BudgetStatusList,
  CardPaymentsList,
  CreditCardStatusList,
  Goal,
  SpendingSummary,
  SummaryPeriod,
  Transaction,
  UserProfile,
} from "@/lib/types";

import { Spinner } from "@/components/ui/Spinner";
import { MovementsList } from "./MovementsList";
import { SummaryContent } from "./SummaryContent";

type DashboardView = "resumen" | "movimientos";

const VIEWS: { value: DashboardView; label: string }[] = [
  { value: "resumen", label: "Resumen" },
  { value: "movimientos", label: "Movimientos" },
];

const PERIODS: { value: SummaryPeriod; label: string }[] = [
  { value: "este_mes", label: "Este mes" },
  { value: "mes_pasado", label: "Mes pasado" },
  { value: "todo", label: "Todo" },
];

/** The last `count` months as { value: "YYYY-MM", label: "Agosto de 2026" } for the picker. */
function buildMonthOptions(count: number): { value: string; label: string }[] {
  const now = new Date();
  const fmt = new Intl.DateTimeFormat("es", { month: "long", year: "numeric" });
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const label = fmt.format(d);
    return { value, label: label.charAt(0).toUpperCase() + label.slice(1) };
  });
}

const MONTH_OPTIONS = buildMonthOptions(12);

interface DashboardPanelProps {
  open: boolean;
  onClose: () => void;
  /** Bump this to force a refetch (e.g. after a chat turn changes data). */
  refreshKey?: number;
}

export function DashboardPanel({ open, onClose, refreshKey = 0 }: DashboardPanelProps) {
  const { token } = useAuth();
  const [period, setPeriod] = useState<string>("este_mes");
  const [view, setView] = useState<DashboardView>("resumen");
  const [summary, setSummary] = useState<SpendingSummary | null>(null);
  const [movements, setMovements] = useState<Transaction[]>([]);
  const [budget, setBudget] = useState<BudgetStatusList | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [goalContributed, setGoalContributed] = useState(0);
  const [cards, setCards] = useState<CreditCardStatusList | null>(null);
  const [payments, setPayments] = useState<CardPaymentsList | null>(null);
  const [surplus, setSurplus] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Budgets are current-period, so only fetch them for the "este_mes" view.
      // Cards are reconstructed for the selected month (deuda/disponible/pago at
      // that month-end); goals likewise show their cumulative progress up to that
      // month-end. Both load in every view.
      const [
        summaryData,
        movementsData,
        budgetData,
        profileData,
        goalsData,
        cardsData,
        paymentsData,
        surplusData,
      ] = await Promise.all([
        api.spendingSummary(period, token),
        api.transactions(period, token),
        period === "este_mes" ? api.budgetStatus(token) : Promise.resolve(null),
        api.profile(token),
        api.goals(period, token),
        api.cardsStatus(period, token),
        api.cardPayments(period, token),
        api.excedente(period, token),
      ]);
      setSummary(summaryData);
      setMovements(movementsData.transactions);
      setBudget(budgetData);
      setProfile(profileData);
      setGoals(goalsData.goals);
      setGoalContributed(Number(goalsData.total_contributed ?? 0));
      setCards(cardsData);
      setPayments(paymentsData);
      setSurplus(Number(surplusData.accumulated_surplus ?? 0));
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "No se pudieron cargar los datos. Inténtalo de nuevo.";
      setError(message);
      setSummary(null);
      setMovements([]);
      setBudget(null);
      setProfile(null);
      setGoals([]);
      setGoalContributed(0);
      setCards(null);
      setPayments(null);
      setSurplus(0);
    } finally {
      setLoading(false);
    }
  }, [period, token]);

  // Refetch when opened, when the period changes, and when refreshKey bumps
  // (a chat turn may have registered a transaction) — but only while open.
  useEffect(() => {
    if (open) void load();
  }, [open, load, refreshKey]);

  return (
    <>
      {/* Backdrop (mobile / tablet) */}
      <div
        className={`fixed inset-0 z-20 bg-ink/40 transition-opacity lg:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
        aria-hidden
      />

      <aside
        className={`fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l border-line bg-canvas shadow-xl transition-transform duration-300 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
        aria-label="Resumen financiero"
        aria-hidden={!open}
      >
        <header className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-base font-semibold text-ink">Resumen</h2>
          <div className="flex items-center gap-1">
            <button
              onClick={() => void load()}
              disabled={loading}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted transition-colors hover:bg-slate-100 hover:text-ink disabled:opacity-50"
              aria-label="Actualizar resumen"
            >
              <RefreshCw
                className={`h-5 w-5 ${loading ? "animate-spin" : ""}`}
                aria-hidden
              />
            </button>
            <button
              onClick={onClose}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted transition-colors hover:bg-slate-100 hover:text-ink"
              aria-label="Cerrar resumen"
            >
              <X className="h-5 w-5" aria-hidden />
            </button>
          </div>
        </header>

        <div
          className="flex gap-1 px-5 pt-4"
          role="group"
          aria-label="Vista del panel"
        >
          {VIEWS.map((v) => (
            <button
              key={v.value}
              aria-pressed={view === v.value}
              onClick={() => setView(v.value)}
              className={`flex-1 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                view === v.value
                  ? "bg-ink text-white"
                  : "bg-slate-100 text-muted hover:text-ink"
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>

        <div className="flex gap-1 px-5 pt-3">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              aria-pressed={period === p.value}
              onClick={() => setPeriod(p.value)}
              className={`flex-1 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                period === p.value
                  ? "bg-brand-600 text-white"
                  : "bg-slate-100 text-muted hover:text-ink"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="px-5 pt-2">
          <label htmlFor="month-picker" className="sr-only">
            Elegir un mes
          </label>
          <select
            id="month-picker"
            value={MONTH_OPTIONS.some((m) => m.value === period) ? period : ""}
            onChange={(e) => {
              if (e.target.value) setPeriod(e.target.value);
            }}
            className={`w-full rounded-lg border px-3 py-1.5 text-sm transition-colors ${
              MONTH_OPTIONS.some((m) => m.value === period)
                ? "border-brand-400 bg-brand-50 font-medium text-brand-700"
                : "border-line bg-surface text-muted"
            }`}
          >
            <option value="">O elige un mes…</option>
            {MONTH_OPTIONS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="flex justify-center py-16 text-muted">
              <Spinner className="h-6 w-6" />
            </div>
          ) : error ? (
            <div className="rounded-xl border border-line bg-surface p-4 text-sm text-muted">
              <p>{error}</p>
              <button
                onClick={() => void load()}
                className="mt-3 text-sm font-medium text-brand-600 hover:underline"
              >
                Reintentar
              </button>
            </div>
          ) : view === "movimientos" ? (
            <MovementsList transactions={movements} cards={cards} payments={payments} />
          ) : summary ? (
            <SummaryContent
              summary={summary}
              budget={budget}
              profile={profile}
              goals={goals}
              goalContributions={goalContributed}
              accumulatedSurplus={surplus}
              cards={cards}
              payments={payments}
              period={period}
            />
          ) : null}
        </div>
      </aside>
    </>
  );
}
