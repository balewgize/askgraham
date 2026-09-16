"use client";

export type Theme = "light" | "dark" | "system";
export type FontScale = "s" | "m" | "l";

const THEME_KEY = "askgraham:theme";
const FONT_KEY = "askgraham:font-scale";
const progressKey = (slug: string) => `askgraham:progress:${slug}`;

export function getTheme(): Theme {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function resolvedTheme(t: Theme): "light" | "dark" {
  if (t === "system") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return t;
}

export function applyTheme(t: Theme) {
  document.documentElement.classList.toggle("dark", resolvedTheme(t) === "dark");
  document.documentElement.style.colorScheme = resolvedTheme(t);
}

export function setTheme(t: Theme) {
  try {
    localStorage.setItem(THEME_KEY, t);
  } catch {
    /* ignore */
  }
  applyTheme(t);
}

export function getFontScale(): FontScale {
  try {
    const v = localStorage.getItem(FONT_KEY);
    return v === "s" || v === "l" ? v : "m";
  } catch {
    return "m";
  }
}

export function setFontScale(s: FontScale) {
  try {
    localStorage.setItem(FONT_KEY, s);
  } catch {
    /* ignore */
  }
}

export function getProgress(slug: string): number {
  try {
    return Number(localStorage.getItem(progressKey(slug)) ?? 0) || 0;
  } catch {
    return 0;
  }
}

export function setProgress(slug: string, y: number) {
  try {
    localStorage.setItem(progressKey(slug), String(Math.round(y)));
  } catch {
    /* ignore */
  }
}
