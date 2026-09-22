"use client";

/**
 * Theme state for the dashboard: a light/dark/system mode plus an accent
 * colour. Both live in localStorage and are reflected onto <html> as
 * `data-theme` / `data-accent`, which `globals.css` keys off.
 *
 * Reads go through `useSyncExternalStore` so the server render and the first
 * client render agree (both use the defaults), then the client swaps to the
 * stored values without a hydration warning. The pre-paint bootstrap script
 * in the root layout has already set the correct attributes, so there's no
 * visual flash during that swap.
 *
 * "system" is resolved to light/dark here (via the OS preference) so the rest
 * of the app — and Tailwind's `dark:` variant — only sees an explicit theme.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
} from "react";

export type ThemeMode = "light" | "dark" | "system";
export type Accent = "indigo" | "teal" | "rose" | "amber" | "violet";

export const ACCENTS: { value: Accent; label: string; swatch: string }[] = [
  { value: "indigo", label: "Indigo", swatch: "#4f46e5" },
  { value: "teal", label: "Teal", swatch: "#0d9488" },
  { value: "rose", label: "Rose", swatch: "#e11d48" },
  { value: "amber", label: "Amber", swatch: "#d97706" },
  { value: "violet", label: "Violet", swatch: "#7c3aed" },
];

const MODE_KEY = "helalien.theme.mode";
const ACCENT_KEY = "helalien.theme.accent";
const STORE_EVENT = "helalien:theme-change";
const DARK_QUERY = "(prefers-color-scheme: dark)";

// ---- localStorage as an external store ---------------------------------------

function readStored<T extends string>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    return (localStorage.getItem(key) as T | null) ?? fallback;
  } catch {
    return fallback;
  }
}

function writeStored(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // storage unavailable (private mode etc.) — the in-memory value below
    // still updates for this session.
  }
  window.dispatchEvent(new Event(STORE_EVENT));
}

function subscribeStored(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(STORE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(STORE_EVENT, onChange);
  };
}

function useStoredMode(): ThemeMode {
  return useSyncExternalStore(
    subscribeStored,
    () => readStored<ThemeMode>(MODE_KEY, "system"),
    () => "system",
  );
}

function useStoredAccent(): Accent {
  return useSyncExternalStore(
    subscribeStored,
    () => readStored<Accent>(ACCENT_KEY, "indigo"),
    () => "indigo",
  );
}

function useSystemDark(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia(DARK_QUERY);
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    },
    () => window.matchMedia(DARK_QUERY).matches,
    () => false,
  );
}

// ---- Context ----------------------------------------------------------------

type ThemeContextValue = {
  mode: ThemeMode;
  accent: Accent;
  /** The mode actually in effect — "system" resolved to light/dark. */
  resolved: "light" | "dark";
  setMode: (mode: ThemeMode) => void;
  setAccent: (accent: Accent) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function applyToDocument(resolved: "light" | "dark", accent: Accent) {
  const root = document.documentElement;
  root.setAttribute("data-theme", resolved);
  root.setAttribute("data-accent", accent);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const mode = useStoredMode();
  const accent = useStoredAccent();
  const systemDark = useSystemDark();

  const resolved: "light" | "dark" =
    mode === "system" ? (systemDark ? "dark" : "light") : mode;

  useEffect(() => {
    applyToDocument(resolved, accent);
  }, [resolved, accent]);

  const setMode = useCallback((next: ThemeMode) => writeStored(MODE_KEY, next), []);
  const setAccent = useCallback((next: Accent) => writeStored(ACCENT_KEY, next), []);

  const value = useMemo<ThemeContextValue>(
    () => ({ mode, accent, resolved, setMode, setAccent }),
    [mode, accent, resolved, setMode, setAccent],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within <ThemeProvider>");
  return ctx;
}

/**
 * Inline script run before first paint to set the theme attributes from
 * storage, avoiding a flash of the wrong theme. Injected via `next/script`
 * with `strategy="beforeInteractive"` — keep it dependency-free and tiny.
 */
export const themeBootstrapScript = `
(function () {
  try {
    var mode = localStorage.getItem("${MODE_KEY}") || "system";
    var accent = localStorage.getItem("${ACCENT_KEY}") || "indigo";
    var dark = mode === "dark" || (mode === "system" &&
      window.matchMedia("${DARK_QUERY}").matches);
    var root = document.documentElement;
    root.setAttribute("data-theme", dark ? "dark" : "light");
    root.setAttribute("data-accent", accent);
  } catch (e) {}
})();
`;
