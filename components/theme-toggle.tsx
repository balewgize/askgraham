"use client";

import { useEffect, useState } from "react";
import { applyTheme, getTheme, setTheme, type Theme } from "./reader-prefs";

const ORDER: Theme[] = ["system", "light", "dark"];

export default function ThemeToggle() {
  const [theme, setT] = useState<Theme>(getTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const cycle = () => {
    const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
    setT(next);
    setTheme(next);
  };

  return (
    <button
      type="button"
      onClick={cycle}
      title={`Theme: ${theme} (click to change)`}
      aria-label={`Theme: ${theme}`}
      className="rounded-md border border-black/10 px-2 py-1 text-xs text-zinc-600 hover:bg-black/5 dark:border-white/15 dark:text-zinc-300 dark:hover:bg-white/10"
    >
      {theme === "dark" ? "● dark" : theme === "light" ? "○ light" : "◐ auto"}
    </button>
  );
}
