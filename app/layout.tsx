import { SpeedInsights } from '@vercel/speed-insights/next';
import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import SearchPalette from "@/components/search-palette";
import ThemeToggle from "@/components/theme-toggle";
import { DownloadIcon, GitHubIcon } from "@/components/icons";
import { SITE_DESCRIPTION, SITE_KEYWORDS, SITE_NAME, SITE_URL } from "@/lib/site";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Paul Graham's Essays — Full Text, Searchable & Filterable",
    template: `%s | ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  keywords: SITE_KEYWORDS,
  creator: SITE_NAME,
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: SITE_NAME,
    title: "Paul Graham's Essays — Full Text, Searchable & Filterable",
    description: SITE_DESCRIPTION,
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "Paul Graham's Essays — Full Text, Searchable & Filterable",
    description: SITE_DESCRIPTION,
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large", "max-snippet": -1 },
  },
  category: "education",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#18181b" },
  ],
};

const websiteJsonLd = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: SITE_NAME,
  alternateName: "Paul Graham's Essays",
  url: SITE_URL,
  description: SITE_DESCRIPTION,
  inLanguage: "en",
  about: { "@type": "Person", name: "Paul Graham", url: "https://www.paulgraham.com" },
};

// Runs before paint: restores persisted theme (or system) to avoid a flash.
const themeInit = `(function(){try{var t=localStorage.getItem("askgraham:theme");var d=t==="dark"||(t!=="light"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.classList.toggle("dark",d);document.documentElement.style.colorScheme=d?"dark":"light";}catch(e){}})();`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body className="flex min-h-full flex-col bg-white text-zinc-900 dark:bg-zinc-900 dark:text-zinc-100">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteJsonLd).replace(/</g, "\\u003c") }}
        />
        <header className="sticky top-0 z-40 border-b border-black/10 bg-white/90 backdrop-blur dark:border-white/10 dark:bg-zinc-900/90">
          <div className="mx-auto flex max-w-3xl items-center justify-between gap-2 px-4 py-2.5">
            <div className="flex items-center gap-1.5">
              <Link
                href="/"
                className="mr-1 font-serif text-base font-bold tracking-tight sm:text-lg"
                style={{ fontFamily: "Georgia, serif" }}
              >
                Ask Graham
              </Link>
              <Link
                href="/export"
                aria-label="Export essays"
                className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs text-zinc-600 hover:bg-black/5 dark:text-zinc-300 dark:hover:bg-white/10"
              >
                <DownloadIcon size={15} />
                <span className="hidden sm:inline">Export</span>
              </Link>
              <a
                href="https://github.com/balewgize/askgraham"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="View source on GitHub"
                className="flex items-center rounded-md px-2 py-1.5 text-zinc-500 hover:bg-black/5 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-zinc-100"
              >
                <GitHubIcon size={16} />
              </a>
            </div>
            <div className="flex items-center gap-1.5">
              <SearchPalette />
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 sm:py-8">{children}</main>
        <footer className="border-t border-black/10 py-4 text-center text-sm text-zinc-500 dark:border-white/10 dark:text-zinc-400">
          Personal learning tool · Essays by Paul Graham ·{" "}
          <a
            href="https://www.paulgraham.com"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-zinc-600 dark:hover:text-zinc-200"
          >
            paulgraham.com
          </a>{" "}
          · {new Date().getFullYear()}
        </footer>
        <SpeedInsights />
      </body>
    </html>
  );
}
