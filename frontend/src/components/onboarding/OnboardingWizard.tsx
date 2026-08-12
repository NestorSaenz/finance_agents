"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { categoryLabel } from "@/lib/format";
import { Logo } from "@/components/ui/Logo";

import { CardsStep, newCard, type CardDraft } from "./CardsStep";
import { CategoryCapsStep } from "./CategoryCapsStep";
import { RecurringStep, newRecurring, type RecurringDraft } from "./RecurringStep";
import { WelcomeStep } from "./WelcomeStep";

// The 18 real categories (they power auto-categorization). "otros" is excluded
// as a budget target since it's the catch-all and a cap on it isn't meaningful.
const COMMON_CATEGORIES = [
  "alimentacion",
  "transporte",
  "restaurantes",
  "entretenimiento",
  "servicios",
  "vivienda",
  "salud",
  "suscripciones",
];
const MORE_CATEGORIES = [
  "educacion",
  "ropa",
  "tecnologia",
  "viajes",
  "combustible",
  "estacionamiento",
  "gimnasio",
  "mascotas",
  "regalos",
  "imprevistos",
  "otros",
];

/** First day of the current month as an ISO date (budget period start). */
function monthStartISO(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
}

function isValidDay(v: string): boolean {
  const n = Number(v);
  return Number.isInteger(n) && n >= 1 && n <= 31;
}

interface OnboardingWizardProps {
  onDone: () => void;
}

export function OnboardingWizard({ onDone }: OnboardingWizardProps) {
  const { token } = useAuth();
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [name, setName] = useState("");
  const [income, setIncome] = useState("");
  const [savings, setSavings] = useState("");
  const [currency, setCurrency] = useState("COP");
  // Insertion-ordered selection + the amount typed for each selected category.
  const [selected, setSelected] = useState<string[]>([]);
  const [caps, setCaps] = useState<Record<string, string>>({});
  const [showMore, setShowMore] = useState(false);
  // User-defined categories added during onboarding (beyond the canonical set).
  const [customCategories, setCustomCategories] = useState<string[]>([]);
  const [cards, setCards] = useState<CardDraft[]>([]);
  const [recurring, setRecurring] = useState<RecurringDraft[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const incomeValue = Number(income);
  const incomeValid = income === "" || (Number.isFinite(incomeValue) && incomeValue > 0);
  const savingsValue = Number(savings);
  const savingsValid =
    savings === "" ||
    (Number.isFinite(savingsValue) && savingsValue >= 0 && savingsValue <= 100);
  // Live "≈ $X/mes" hint when both income and savings % are provided.
  const savingsPreview =
    income !== "" && savings !== "" && incomeValid && savingsValid
      ? (incomeValue * savingsValue) / 100
      : null;

  const chipCategories = [
    ...(showMore ? [...COMMON_CATEGORIES, ...MORE_CATEGORIES] : COMMON_CATEGORIES),
    ...customCategories,
  ];

  function toggleCategory(category: string) {
    setSelected((prev) =>
      prev.includes(category)
        ? prev.filter((c) => c !== category)
        : [...prev, category],
    );
  }

  /** Add a user-defined category (normalized like the backend) and select it. */
  function addCustomCategory(raw: string) {
    const category = raw.trim().toLowerCase().replace(/\s+/g, " ");
    if (!category) return;
    if (!chipCategories.includes(category)) {
      setCustomCategories((prev) => [...prev, category]);
    }
    setSelected((prev) => (prev.includes(category) ? prev : [...prev, category]));
  }

  function updateCard(index: number, field: keyof CardDraft, value: string) {
    setCards((prev) => prev.map((c, i) => (i === index ? { ...c, [field]: value } : c)));
  }

  function updateRecurring(
    index: number,
    field: keyof Omit<RecurringDraft, "id">,
    value: string,
  ) {
    setRecurring((prev) =>
      prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)),
    );
  }

  // Only cards with every field valid are created; the rest are ignored.
  const validCards = cards.filter(
    (c) =>
      c.name.trim() !== "" &&
      Number(c.limit) > 0 &&
      isValidDay(c.cutoff) &&
      isValidDay(c.payment),
  );

  // A fixed movement needs description + amount + day to be sent; the rest ignored.
  const validRecurring = recurring.filter(
    (r) => r.description.trim() !== "" && Number(r.amount) > 0 && isValidDay(r.day),
  );

  async function finish(withData: boolean, includeRecurring = false) {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const monthlyIncome =
        withData && income !== "" && incomeValue > 0 ? incomeValue : undefined;
      const savingsGoal =
        withData && savings !== "" && savingsValid ? savingsValue : undefined;
      // Name is always sent (even when skipping caps) so Safi can greet by name.
      const displayName = name.trim() || undefined;
      await api.completeOnboarding(
        {
          display_name: displayName,
          monthly_income: monthlyIncome,
          savings_goal_percentage: savingsGoal,
          currency,
        },
        token,
      );

      if (withData) {
        const start = monthStartISO();
        const budgets = selected
          .map((category) => ({ category, amount: Number(caps[category]) }))
          .filter((b) => Number.isFinite(b.amount) && b.amount > 0);
        // Best-effort: a failed item shouldn't block finishing onboarding.
        await Promise.allSettled([
          ...budgets.map((b) =>
            api.createBudget(
              {
                name: `Tope de ${categoryLabel(b.category)}`,
                amount: b.amount,
                category: b.category,
                start_date: start,
              },
              token,
            ),
          ),
          ...validCards.map((c) =>
            api.createCard(
              {
                name: c.name.trim(),
                credit_limit: Number(c.limit),
                cutoff_day: Number(c.cutoff),
                payment_day: Number(c.payment),
              },
              token,
            ),
          ),
          ...(includeRecurring
            ? validRecurring.map((r) =>
                api.createRecurring(
                  {
                    description: r.description.trim(),
                    amount: Number(r.amount),
                    transaction_type: r.transactionType,
                    day_of_month: Number(r.day),
                  },
                  token,
                ),
              )
            : []),
        ]);
      }
      onDone();
    } catch {
      setError("No se pudo guardar tu configuración. Inténtalo de nuevo.");
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/50 p-4">
      <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-6 shadow-xl sm:p-8">
        <div className="mb-6 flex items-center justify-between">
          <Logo />
          <span className="text-xs font-medium text-muted">Paso {step} de 4</span>
        </div>

        {step === 1 ? (
          <WelcomeStep
            name={name}
            income={income}
            savings={savings}
            currency={currency}
            incomeValid={incomeValid}
            savingsValid={savingsValid}
            savingsPreview={savingsPreview}
            submitting={submitting}
            onNameChange={setName}
            onIncomeChange={setIncome}
            onSavingsChange={setSavings}
            onCurrencyChange={setCurrency}
            onSkip={() => void finish(false)}
            onContinue={() => setStep(2)}
          />
        ) : step === 2 ? (
          <CategoryCapsStep
            chipCategories={chipCategories}
            selected={selected}
            caps={caps}
            showMore={showMore}
            submitting={submitting}
            onToggle={toggleCategory}
            onAddCustom={addCustomCategory}
            onCapChange={(category, value) =>
              setCaps((prev) => ({ ...prev, [category]: value }))
            }
            onShowMore={() => setShowMore(true)}
            onBack={() => setStep(1)}
            onContinue={() => setStep(3)}
          />
        ) : step === 3 ? (
          <CardsStep
            cards={cards}
            onUpdate={updateCard}
            onRemove={(index) => setCards((prev) => prev.filter((_, i) => i !== index))}
            onAdd={() => setCards((prev) => [...prev, newCard()])}
            onBack={() => setStep(2)}
            onContinue={() => setStep(4)}
          />
        ) : (
          <RecurringStep
            recurring={recurring}
            submitting={submitting}
            error={error}
            onUpdate={updateRecurring}
            onRemove={(index) =>
              setRecurring((prev) => prev.filter((_, i) => i !== index))
            }
            onAdd={() => setRecurring((prev) => [...prev, newRecurring()])}
            onBack={() => setStep(3)}
            onSkip={() => void finish(true, false)}
            onFinish={() => void finish(true, true)}
          />
        )}
      </div>
    </div>
  );
}
