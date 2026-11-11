"use client";

import { useCurrency, useMoney } from "@/context/CurrencyContext";
import { heroFigure } from "@/lib/heroFigure";
import { summaryFigures } from "@/lib/summary";

import { CardPayments } from "../CardPayments";
import { CategorySpendingBars } from "../CategorySpendingBars";
import { GoalProgress } from "../GoalProgress";
import { PaymentSplit } from "../PaymentSplit";
import type { SummaryContentProps } from "../SummaryContent";
import { CardsSection } from "./CardsSection";
import { CashFlowCard } from "./CashFlowCard";
import { CategorySection } from "./CategorySection";
import { HeroFigure } from "./HeroFigure";
import { MoreDetails } from "./MoreDetails";
import { RecurringCard } from "./RecurringCard";
import { Section } from "./Section";
import { SectionJumps, type JumpSection } from "./SectionJumps";
import { SurplusCompact } from "./SurplusCompact";

const IDS = {
  flujo: "resumen-flujo",
  topes: "resumen-topes",
  metas: "resumen-metas",
  tarjetas: "resumen-tarjetas",
} as const;

/** The redesigned summary (behind ?nuevo=1): a lead figure, jumps to sections, the
 *  same cards as before in a new order, and the rest under "Más detalles". Every
 *  figure comes from `summaryFigures`, exactly as in SummaryContent. */
export function SummaryContentV2(props: SummaryContentProps) {
  const { summary, budget, cards, payments, period, planStatus = null, goalHistory = null } = props;
  const money = useMoney();
  const currency = useCurrency();
  const figures = summaryFigures({ ...props, planStatus, goalHistory, currency });

  if (!figures.hasData) {
    return (
      <div className="rounded-xl border border-dashed border-line bg-surface p-6 text-center text-sm text-muted">
        Aún no hay movimientos en este período. Registra un gasto o ingreso desde el
        chat y aparecerá aquí.
      </div>
    );
  }

  const hero = heroFigure(figures, {
    period,
    accumulatedSurplus: props.accumulatedSurplus,
    money,
  });
  const showCategories = Boolean(budget) || figures.hasPlans || figures.hasHistory;
  const showCards = cards !== null && cards.cards.length > 0;
  const jumps: JumpSection[] = [
    ...(figures.hasCashFlow ? [{ id: IDS.flujo, label: "Flujo", fullLabel: "Flujo de caja" }] : []),
    ...(showCategories ? [{ id: IDS.topes, label: "Topes", fullLabel: "Topes" }] : []),
    ...(figures.activeGoals.length > 0 ? [{ id: IDS.metas, label: "Metas", fullLabel: "Metas" }] : []),
    ...(showCards ? [{ id: IDS.tarjetas, label: "Tarjetas", fullLabel: "Tarjetas" }] : []),
  ];

  return (
    <div className="flex flex-col gap-5">
      <HeroFigure
        hero={hero}
        income={figures.income}
        totalSpent={figures.totalSpent}
        consumo={figures.expenses}
        spentOnGoals={figures.spentOnGoals}
        balance={figures.balance}
        goalsReturned={figures.goalsReturned}
        pending={figures.pending}
      />
      <SectionJumps sections={jumps} />

      {figures.hasCashFlow && (
        <div id={IDS.flujo} className="scroll-mt-2 focus:outline-none">
          <h3 className="sr-only">Flujo de caja</h3>
          <CashFlowCard
            goalSaved={props.goalSaved}
            goalWithdrawn={props.goalWithdrawn}
            figures={figures}
          />
        </div>
      )}

      {period !== "todo" && <SurplusCompact accumulatedSurplus={props.accumulatedSurplus} />}

      {showCategories && (
        <div id={IDS.topes} className="scroll-mt-2">
          <CategorySection
            budget={budget}
            budgetTransactions={props.budgetTransactions}
            planStatus={planStatus}
            goalHistory={goalHistory}
            period={period}
            onSelectMonth={props.onSelectMonth}
            figures={figures}
          />
        </div>
      )}

      {figures.activeGoals.length > 0 && (
        <div id={IDS.metas} className="scroll-mt-2">
          <Section title="Metas de ahorro">
            <GoalProgress goals={figures.activeGoals} />
          </Section>
        </div>
      )}

      {cards && showCards && (
        <div id={IDS.tarjetas} className="scroll-mt-2">
          <CardsSection
            cards={cards}
            transactions={props.transactions}
            payments={payments}
            period={period}
            historical={figures.historicalCards}
          />
        </div>
      )}

      <MoreDetails>
        <RecurringCard recurring={props.recurring} />
        {payments && payments.payments.length > 0 && (
          <Section title="Pagos a tarjetas">
            <CardPayments data={payments} />
          </Section>
        )}
        <PaymentSplit
          credit={Number(summary.credit_expenses)}
          cash={Number(summary.cash_expenses)}
          totalExpenses={Number(summary.total_expenses)}
        />
        {summary.by_category.length > 0 && (
          <Section title="Gastos por categoría (consumo)">
            <CategorySpendingBars data={summary.by_category} />
          </Section>
        )}
      </MoreDetails>
    </div>
  );
}
