"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { iconButton } from "@/lib/ui";
import { BookmarkIcon, ChatIcon, CloseIcon, DownloadIcon, GitHubIcon, MenuIcon } from "./icons";
import SearchPalette from "./search-palette";
import ThemeToggle from "./theme-toggle";

const GITHUB_URL = "https://github.com/balewgize/askgraham";

/** Secondary destinations. Inline on desktop, folded into the sheet on mobile. */
const NAV = [
  { href: "/chat", label: "Ask", Icon: ChatIcon },
  { href: "/export", label: "Export", Icon: DownloadIcon },
  { href: "/favorites", label: "Favorites", Icon: BookmarkIcon },
] as const;

/** `/essays/foo` counts as being on `/essays`, but `/chat` does not match `/chatter`. */
function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

const activeLink = "bg-fg/[0.07] font-medium text-fg";
const idleLink = "text-fg-muted hover:bg-fg/[0.06] hover:text-fg";

export default function SiteHeader() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    const onPointerDown = (e: PointerEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointerDown);
    };
  }, [menuOpen]);

  return (
    <header
      data-site-header
      className="sticky top-0 z-40 border-b border-line bg-raised/80 backdrop-blur-xl"
    >
      <div className="mx-auto flex h-14 max-w-3xl items-center gap-2 px-4">
        <Link
          href="/"
          className="-ml-1.5 shrink-0 rounded-lg px-1.5 py-1 font-serif text-[1.0625rem] font-semibold tracking-tight transition-colors hover:bg-fg/[0.06]"
        >
          Ask Graham
        </Link>

        <nav aria-label="Primary" className="ml-2 hidden items-center gap-1 sm:flex">
          {NAV.map(({ href, label }) => {
            const active = isActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`relative rounded-md px-2.5 py-1.5 text-sm transition-colors ${
                  active ? "text-fg" : "text-fg-muted hover:text-fg"
                }`}
              >
                {label}
                <span
                  aria-hidden="true"
                  className={`absolute inset-x-2.5 -bottom-0.5 h-0.5 rounded-full bg-accent transition-opacity ${
                    active ? "opacity-100" : "opacity-0"
                  }`}
                />
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-0.5">
          <SearchPalette />
          <ThemeToggle />
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="View source on GitHub"
            className={`hidden sm:flex ${iconButton}`}
          >
            <GitHubIcon size={17} />
          </a>

          <div ref={menuRef} className="relative sm:hidden">
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              aria-controls="site-menu"
              className={iconButton}
            >
              {menuOpen ? <CloseIcon size={18} /> : <MenuIcon size={18} />}
            </button>
            {menuOpen && (
              <nav
                id="site-menu"
                aria-label="Site"
                className="absolute right-0 top-full z-50 mt-2 w-52 overflow-hidden rounded-xl border border-line bg-overlay p-1.5 shadow-2xl"
              >
                {NAV.map(({ href, label, Icon }) => {
                  const active = isActive(pathname, href);
                  return (
                    <Link
                      key={href}
                      href={href}
                      onClick={() => setMenuOpen(false)}
                      aria-current={active ? "page" : undefined}
                      className={`flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                        active ? activeLink : idleLink
                      }`}
                    >
                      <Icon size={16} />
                      {label}
                    </Link>
                  );
                })}
                <div className="my-1 border-t border-line" />
                <a
                  href={GITHUB_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setMenuOpen(false)}
                  className={`flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm transition-colors ${idleLink}`}
                >
                  <GitHubIcon size={16} />
                  GitHub
                </a>
              </nav>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
