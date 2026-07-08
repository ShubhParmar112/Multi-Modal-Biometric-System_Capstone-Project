import { createContext, useContext, useEffect, useState } from "react";
import client from "../api/client";

// Theme preference: "dark" | "light" | "system". "system" follows the
// OS/browser prefers-color-scheme setting live. The choice is stored in
// localStorage (works pre-login) and, when signed in, persisted per user
// via /api/settings/theme so it follows the user across devices.

const THEMES = ["dark", "light", "system"];
const ThemeContext = createContext(null);

function systemTheme() {
  return window.matchMedia?.("(prefers-color-scheme: light)").matches
    ? "light" : "dark";
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    const stored = localStorage.getItem("smartbank_theme");
    return THEMES.includes(stored) ? stored : "dark";
  });
  const resolvedTheme = theme === "system" ? systemTheme() : theme;

  // Re-render on OS theme changes while in "system" mode.
  const [, forceRender] = useState(0);
  useEffect(() => {
    if (theme !== "system" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => forceRender((n) => n + 1);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", resolvedTheme);
    localStorage.setItem("smartbank_theme", theme);
  }, [theme, resolvedTheme]);

  // User-initiated change: also persist per user on the server.
  function setTheme(next) {
    if (!THEMES.includes(next)) return;
    setThemeState(next);
    if (localStorage.getItem("smartbank_token")) {
      client.post("/api/settings/theme", { theme: next }).catch(() => {});
    }
  }

  // Server-initiated (after login): apply without echoing back a POST.
  function applyServerTheme(next) {
    if (THEMES.includes(next)) setThemeState(next);
  }

  function toggleTheme() {
    setTheme(resolvedTheme === "dark" ? "light" : "dark");
  }

  return (
    <ThemeContext.Provider
      value={{ theme, resolvedTheme, setTheme, applyServerTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
