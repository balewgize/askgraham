"use client";

import { useMemo, useSyncExternalStore } from "react";

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

const ACTIVE_PATH_KEY = "askgraham:active-path";
const pathDoneKey = (id: string) => `askgraham:path:${id}:done`;

// Same-tab subscribers so localStorage-backed state re-renders via useSyncExternalStore.
const listeners = new Set<() => void>();
const subscribe = (cb: () => void) => {
  listeners.add(cb);
  return () => listeners.delete(cb);
};
const emit = () => listeners.forEach((l) => l());

/** The path the reader is currently working through, if any. */
export function getActivePath(): string | null {
  try {
    return localStorage.getItem(ACTIVE_PATH_KEY);
  } catch {
    return null;
  }
}

export function setActivePath(id: string) {
  try {
    localStorage.setItem(ACTIVE_PATH_KEY, id);
    emit();
  } catch {
    /* ignore */
  }
}

export function getPathDone(id: string): string[] {
  try {
    const raw = localStorage.getItem(pathDoneKey(id));
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? parsed.filter((s): s is string => typeof s === "string") : [];
  } catch {
    return [];
  }
}

export function setPathDone(id: string, slug: string, done: boolean) {
  try {
    const current = new Set(getPathDone(id));
    if (done) current.add(slug);
    else current.delete(slug);
    localStorage.setItem(pathDoneKey(id), JSON.stringify([...current]));
    emit();
  } catch {
    /* ignore */
  }
}

/** Reactive active-path id. Server snapshot is null; client reads localStorage. */
export function useActivePathId(): string | null {
  return useSyncExternalStore(subscribe, getActivePath, () => null) || null;
}

/** Reactive list of completed slugs for a path. */
export function usePathDone(id: string): string[] {
  const raw = useSyncExternalStore(
    subscribe,
    () => {
      try {
        return localStorage.getItem(pathDoneKey(id)) ?? "";
      } catch {
        return "";
      }
    },
    () => "",
  );
  return useMemo(() => {
    try {
      const parsed = raw ? (JSON.parse(raw) as unknown) : [];
      return Array.isArray(parsed) ? parsed.filter((s): s is string => typeof s === "string") : [];
    } catch {
      return [];
    }
  }, [raw]);
}
