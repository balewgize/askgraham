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
  const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];

  return (
    <button
      type="button"
      onClick={cycle}
      title={`Theme: ${theme} — switch to ${next}`}
      aria-label={`Theme: ${LABELS[theme]}. Switch to ${LABELS[next].toLowerCase()} theme.`}
      className="flex items-center gap-1.5 rounded-md border border-line-firm px-2 py-2 text-sm text-fg-muted transition-colors hover:bg-fg/[0.06] hover:text-fg"
    >
      <Icon size={16} />
      <span className="hidden sm:inline">{LABELS[theme]}</span>
    </button>
  );
}