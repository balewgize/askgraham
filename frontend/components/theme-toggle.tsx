"use client";

import { useEffect, useState } from "react";
import { MonitorIcon, MoonIcon, SunIcon } from "./icons";
import { applyTheme, getTheme, setTheme, type Theme } from "./reader-prefs";

const ORDER: Theme[] = ["system", "light", "dark"];
const ICONS = { system: MonitorIcon, light: SunIcon, dark: MoonIcon };
const LABELS = { system: "Auto", light: "Light", dark: "Dark" };

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

  const Icon = ICONS[theme];

  return (
    <button
      type="button"
      onClick={cycle}
      title={`Theme: ${theme} (click to change)`}
      aria-label={`Theme: ${theme} (click to change)`}
      className="flex items-center gap-1.5 rounded-md border border-black/10 px-2 py-1.5 text-xs text-zinc-600 hover:bg-black/5 dark:border-white/15 dark:text-zinc-300 dark:hover:bg-white/10"
    >
      <Icon size={15} />
      <span className="hidden sm:inline">{LABELS[theme]}</span>
    </button>
  );
}
