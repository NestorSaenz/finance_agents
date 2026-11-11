"use client";

import type { CardPaymentsList, CreditCardStatusList, Transaction } from "@/lib/types";

import { CardStatus } from "../CardStatus";
import { Section } from "./Section";

interface CardsSectionProps {
  cards: CreditCardStatusList;
  transactions: Transaction[];
  payments: CardPaymentsList | null;
  period: string;
  /** Past-month cards come back without a statement period. */
  historical: boolean;
}

/** "Tarjetas de crédito" with the right subtitle for live vs reconstructed cards. */
export function CardsSection({
  cards,
  transactions,
  payments,
  period,
  historical,
}: CardsSectionProps) {
  return (
    <Section
      title="Tarjetas de crédito"
      subtitle={
        historical ? "Deuda, disponible y pago reconstruidos a fin de ese mes." : "Estado a hoy."
      }
    >
      <CardStatus
        data={cards}
        transactions={transactions}
        payments={payments?.payments ?? []}
        period={period}
      />
    </Section>
  );
}
