import { createContext, useContext, useEffect, useState } from "react";
import client from "../api/client";
import { useAuth } from "./AuthContext";

// Symbol + locale per ISO currency code (accounts.currency in the DB).
const CURRENCIES = {
  INR: { symbol: "₹", locale: "en-IN" },
  USD: { symbol: "$", locale: "en-US" },
  EUR: { symbol: "€", locale: "de-DE" },
  GBP: { symbol: "£", locale: "en-GB" },
  JPY: { symbol: "¥", locale: "ja-JP" },
};
const DEFAULT_CODE = "INR";

const CurrencyContext = createContext(null);

export function CurrencyProvider({ children }) {
  const { user } = useAuth();
  const [code, setCode] = useState(DEFAULT_CODE);

  // The account being viewed decides the currency (also correct in
  // beneficiary view-as mode, since /accounts/me honors X-View-As).
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    client.get("/api/accounts/me")
      .then((res) => {
        if (!cancelled && res.data.currency) setCode(res.data.currency);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [user]);

  const { symbol, locale } = CURRENCIES[code] || CURRENCIES[DEFAULT_CODE];

  function fmt(n, opts = {}) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    return `${symbol}${Number(n).toLocaleString(locale, opts)}`;
  }

  return (
    <CurrencyContext.Provider value={{ currency: code, symbol, locale, fmt }}>
      {children}
    </CurrencyContext.Provider>
  );
}

export function useCurrency() {
  return useContext(CurrencyContext);
}
