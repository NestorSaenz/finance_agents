"use client";

import { createContext, useContext, useMemo } from "react";

import { formatMoney } from "@/lib/format";

// The active user's ISO-4217 currency. Defaults to "COP" so components used
// outside a provider (or before the profile loads) still format sensibly.
const CurrencyContext = createContext<string>("COP");

export function CurrencyProvider({
  currency,
  children,
}: {
  currency: string;
  children: React.ReactNode;
}) {
  return (
    <CurrencyContext.Provider value={currency}>
      {children}
    </CurrencyContext.Provider>
  );
}

/** The active user's ISO-4217 currency code (e.g. "COP", "USD"). */
export function useCurrency(): string {
  return useContext(CurrencyContext);
}

/**
 * A money formatter bound to the active user's currency. Prefer this over
 * calling `formatMoney` directly in authenticated components so amounts always
 * render in the user's currency.
 */
export function useMoney(): (value: string | number) => string {
  const currency = useContext(CurrencyContext);
  return useMemo(
    () => (value: string | number) => formatMoney(value, currency),
    [currency],
  );
}
