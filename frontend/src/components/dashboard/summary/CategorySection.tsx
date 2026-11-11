"use client";

import { useCurrency } from "@/context/CurrencyContext";
import type { SummaryFigures } from "@/lib/summary";
import type { BudgetStatusList, GoalMonthlyHistory, GoalPlanStatusList, Transaction } from "@/lib/types";

import { BudgetIncomeSummary } from "../BudgetIncomeSummary";
import { BudgetProgress } from "../BudgetProgress";
import { GoalPlanHistory } from "../GoalPlanHistory";
import { GoalPlanProgress } from "../GoalPlanProgress";
import { Section } from "./Section";

interface CategorySectionProps {
  budget: BudgetStatusList | null;
  /** Expenses that impact this period's budget (to list what makes up each tope). */
  budgetTransactions: Transaction[];
  planStatus: GoalPlanStatusList | null;
  goalHistory: GoalMonthlyHistory | null;
  period: string;
  /** Tapping a month in the plan history switches the panel to it. */
  onSelectMonth?: (month: string) => void;
  figures: Pick<
    SummaryFigures,
    | "referenceIncome"
    | "planShare"
    | "planCurrency"
    | "hasPlans"
    | "hasTopes"
    | "hasHistory"
    | "viewedMonth"
  >;
}

/** "Cómo voy en cada categoría": topes (current month only), the month's goal plan
 *  and the plan history. Decides by itself whether it has anything to show. */
export function CategorySection({
  budget,
  budgetTransactions,
  planStatus,
  goalHistory,
  period,
  onSelectMonth,
  figures,
}: CategorySectionProps) {
  const currency = useCurrency();
  const { referenceIncome, planShare, planCurrency, hasPlans, hasTopes, hasHistory, viewedMonth } =
    figures;
  if (!(budget || hasPlans || hasHistory)) return null;
  return (
    <Section
      title="Cómo voy en cada categoría"
      subtitle={
        budget
          ? "Incluye tus gastos fijos y las compras a crédito según el mes en que las pagas. El aviso llega cuando tus gastos variables se acercan al tope o te pasas."
          : "Los topes se muestran solo para el mes en curso."
      }
    >
      <div className="flex flex-col gap-4">
        {budget ? (
          <BudgetProgress
            data={budget}
            transactions={budgetTransactions}
            monthlyIncome={referenceIncome}
            plan={planShare}
            hasPlans={hasPlans}
          />
        ) : null}
        {/* Without topes BudgetProgress renders no income lines: show the plan's here. */}
        {!hasTopes && planShare && <BudgetIncomeSummary share={null} plan={planShare} />}
        <GoalPlanProgress data={planStatus} displayCurrency={currency} />
        {goalHistory && onSelectMonth && (
          <GoalPlanHistory
            lines={goalHistory.lines}
            currency={planCurrency}
            displayCurrency={currency}
            selectedMonth={period === "todo" ? null : viewedMonth}
            endMonth={viewedMonth}
            onSelectMonth={onSelectMonth}
          />
        )}
      </div>
    </Section>
  );
}
