"use client";

import { useEffect } from "react";

/**
 * Publishes the sticky header's height as `--header-h` on <html>.
 *
 * Sticky year headers (home) and the reading-progress bar (essay) both need to
 * stop exactly where the header ends. Measuring beats hardcoding a magic number,
 * and it stays correct when the header wraps or the font scale changes.
 */
export default function HeaderHeight() {
  useEffect(() => {
    const header = document.querySelector<HTMLElement>("[data-site-header]");
    if (!header) return;

    const publish = () => {
      const h = Math.round(header.getBoundingClientRect().height);
      document.documentElement.style.setProperty("--header-h", `${h}px`);
    };

    publish();
    const observer = new ResizeObserver(publish);
    observer.observe(header);
    return () => observer.disconnect();
  }, []);

  return null;
}