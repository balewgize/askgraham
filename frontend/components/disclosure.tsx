"use client";

import { useId, useState, type ReactNode } from "react";
import { ChevronDownIcon } from "./icons";

/**
 * A slim section that is collapsed until opened.
 *
 * A standard disclosure widget: the header is a real <button> carrying
 * `aria-expanded`/`aria-controls`, and the panel animates open with the
 * `grid-template-rows: 0fr → 1fr` trick. While collapsed the panel is `inert`,
 * so its links stay out of the tab order and the accessibility tree.
 *
 * Used for the landing page's secondary blocks (guided paths, filters) so the
 * catalog itself stays above the fold.
 */
export default function Disclosure({
  label,
  meta,
  defaultOpen = false,
  className = "",
  children,
}: {
  label: string;
  /** Right-aligned summary text. Keep it useful when collapsed (e.g. active filter). */
  meta?: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();

  return (
    <div
      className={`rounded-lg border border-line transition-colors ${open ? "bg-raised" : "bg-raised/60"} ${className}`}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex min-h-11 w-full cursor-pointer select-none items-center gap-2.5 rounded-lg px-3.5 py-2.5 text-left text-fg-subtle transition-colors hover:bg-fg/[0.04]"
      >
        <ChevronDownIcon
          size={16}
          className={`shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
        <span className="text-[11px] font-semibold uppercase tracking-[0.12em]">{label}</span>
        {meta && <span className="ml-auto shrink-0 text-xs tabular-nums">{meta}</span>}
      </button>
      <div
        id={panelId}
        inert={!open}
        className={`grid transition-[grid-template-rows] duration-200 ease-out ${
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
        }`}
      >
        <div className="overflow-hidden">
          <div className="px-3.5 pb-3.5">{children}</div>
        </div>
      </div>
    </div>
  );
}
