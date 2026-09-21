"use client";

import { createContext, useContext } from "react";

/** The tenant's currency (an admin-set ISO code, see the Settings page's
 * read-only "Plan" panel), provided once by the (app) layout so every price
 * on every page formats consistently without each fetching settings. */
const CurrencyContext = createContext("USD");

export function CurrencyProvider({ currency, children }: { currency: string; children: React.ReactNode }) {
  return <CurrencyContext.Provider value={currency}>{children}</CurrencyContext.Provider>;
}

export function useCurrency(): string {
  return useContext(CurrencyContext);
}
