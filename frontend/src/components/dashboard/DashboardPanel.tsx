"use client";

import { useCallback, useEffect, useState } from "react";
import { X } from "lucide-react";

import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import type {
  BudgetStatusList,
  CardPaymentsList,
  CreditCardStatusList,
  Goal,
  SpendingSummary,
  SummaryPeriod,
  UserProfile,
} from "@/lib/types";

import { Spinner } from "@/components/ui/Spinner";
import { SummaryContent } from "./SummaryContent";

const PERIODS: { value: SummaryPeriod; label: string }[] = [
  { value: "este_mes", label: "Este mes" },
  { value: "mes_pasado", label: "Mes pasado" },
  { value: "todo", label: "Todo" },
];

interface DashboardPanelProps {
  open: boolean;
  onClose: () => void;
  /** Bump this to force a refetch (e.g. after a chat turn changes data). */
  refreshKey?: number;
}

export function DashboardPanel({ open, onClose, refreshKey = 0 }: DashboardPanelProps) {
  const { token } = useAuth();
  const [period, setPeriod] = useState<SummaryPeriod>("este_mes");
  const [summary, setSummary] = useState<SpendingSummary | null>(null);
  const [budget, setBudget] = useState<BudgetStatusList | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [cards, setCards] = useState<CreditCardStatusList | null>(null);
  const [payments, setPayments] = useState<CardPaymentsList | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Budgets are current-period, so only fetch them for the "este_mes" view.
      // Cards/goals reflect current state, so they load in every view.
      const [summaryData, budgetData, profileData, goalsData, cardsData, paymentsData] =
        await Promise.all([
          api.spendingSummary(period, token),
          period === "este_mes" ? api.budgetStatus(token) : Promise.resolve(null),
          api.profile(token),
          api.goals(token),
          api.cardsStatus(token),
          api.cardPayments(period, token),
        ]);
      setSummary(summaryData);
      setBudget(budgetData);
      setProfile(profileData);
      setGoals(goalsData.goals);
      setCards(cardsData);
      setPayments(paymentsData);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "No se pudo cargar el resumen. Inténtalo de nuevo.";
      setError(message);
      setSummary(null);
      setBudget(null);
      setProfile(null);
      setGoals([]);
      setCards(null);
      setPayments(null);
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
          <button
            onClick={onClose}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted transition-colors hover:bg-slate-100 hover:text-ink"
            aria-label="Cerrar resumen"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        </header>

        <div className="flex gap-1 px-5 pt-4">
          {PERIODS.map((p) => (
            <button
              key={p.value}
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
          ) : summary ? (
            <SummaryContent
              summary={summary}
              budget={budget}
              profile={profile}
              goals={goals}
              cards={cards}
              payments={payments}
            />
          ) : null}
        </div>
      </aside>
    </>
  );
}
