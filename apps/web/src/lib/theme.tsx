"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

export type ThemeChoice = "light" | "dark" | "system";
export type EffectiveTheme = "light" | "dark";

const STORAGE_KEY = "recon-theme";

/**
 * Blocking script injected before paint so the correct theme class is on
 * <html> on the very first frame. <html> ships with `class="dark"` from the
 * server (dark is the RECON default), so dark users never see a flip; only
 * a stored or OS-preferred light choice removes the class pre-paint.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var c=localStorage.getItem('${STORAGE_KEY}')||'system';var m=window.matchMedia('(prefers-color-scheme: dark)').matches;var dark=c==='dark'||(c==='system'&&m);var r=document.documentElement;r.classList.toggle('dark',dark);r.style.colorScheme=dark?'dark':'light';}catch(e){}})();`;

function systemPrefersDark(): boolean {
  if (typeof window === "undefined") return true;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function resolve(choice: ThemeChoice): EffectiveTheme {
  if (choice === "system") return systemPrefersDark() ? "dark" : "light";
  return choice;
}

function apply(effective: EffectiveTheme) {
  const root = document.documentElement;
  root.classList.add("theme-anim");
  root.classList.toggle("dark", effective === "dark");
  root.style.colorScheme = effective;
  window.setTimeout(() => root.classList.remove("theme-anim"), 220);
}

interface ThemeContextValue {
  choice: ThemeChoice;
  effective: EffectiveTheme;
  setTheme: (c: ThemeChoice) => void;
  cycle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [choice, setChoice] = useState<ThemeChoice>("system");
  const [effective, setEffective] = useState<EffectiveTheme>("dark");

  // Hydrate from storage once mounted.
  useEffect(() => {
    let stored: ThemeChoice = "system";
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw === "light" || raw === "dark" || raw === "system") stored = raw;
    } catch {
      /* private mode / blocked storage */
    }
    setChoice(stored);
    setEffective(resolve(stored));
  }, []);

  // React to OS changes while in "system" mode.
  useEffect(() => {
    if (choice !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const next = mq.matches ? "dark" : "light";
      setEffective(next);
      apply(next);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [choice]);

  const setTheme = useCallback((c: ThemeChoice) => {
    setChoice(c);
    try {
      localStorage.setItem(STORAGE_KEY, c);
    } catch {
      /* ignore */
    }
    const next = resolve(c);
    setEffective(next);
    apply(next);
  }, []);

  const cycle = useCallback(() => {
    setChoice((prev) => {
      const order: ThemeChoice[] = ["light", "dark", "system"];
      const next = order[(order.indexOf(prev) + 1) % order.length];
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* ignore */
      }
      const eff = resolve(next);
      setEffective(eff);
      apply(eff);
      return next;
    });
  }, []);

  return (
    <ThemeContext.Provider value={{ choice, effective, setTheme, cycle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    // Safe fallback if used outside provider (e.g. isolated tests).
    return {
      choice: "system",
      effective: "dark",
      setTheme: () => {},
      cycle: () => {},
    };
  }
  return ctx;
}
