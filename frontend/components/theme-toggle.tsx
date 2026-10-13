"use client";

import { MonitorIcon, MoonIcon, SunIcon } from "./icons";
import { setTheme, useTheme, type Theme } from "./reader-prefs";

const ORDER: Theme[] = ["system", "light", "dark"];
const ICONS = { system: MonitorIcon, light: SunIcon, dark: MoonIcon };
const LABELS = { system: "Auto", light: "Light", dark: "Dark" };

export default function ThemeToggle() {
  // Hydration-safe: the server snapshot is "system" and the stored value is
  // read after hydration, so the button never disagrees with the markup.
  const theme = useTheme();
  const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
  const Icon = ICONS[theme];

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      title={`Theme: ${theme} — switch to ${next}`}
      aria-label={`Theme: ${LABELS[theme]}. Switch to ${LABELS[next].toLowerCase()} theme.`}
      className="flex items-center gap-1.5 rounded-md border border-line-firm px-2 py-2 text-sm text-fg-muted transition-colors hover:bg-fg/[0.06] hover:text-fg"
    >
      <Icon size={16} />
      <span className="hidden sm:inline">{LABELS[theme]}</span>
    </button>
  );
}
