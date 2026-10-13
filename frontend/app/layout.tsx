import { SpeedInsights } from '@vercel/speed-insights/next';
import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Source_Serif_4 } from "next/font/google";
import Link from "next/link";
import HeaderHeight from "@/components/header-height";
import SearchPalette from "@/components/search-palette";
import ThemeToggle from "@/components/theme-toggle";
import { BookmarkIcon, DownloadIcon, GitHubIcon } from "@/components/icons";
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

// Reading serif. `opsz` lets the browser pick letterforms tuned to the rendered
// size, which matters here because the reader offers three text sizes.
const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
  style: ["normal", "italic"],
  axes: ["opsz"],
  display: "swap",
});

const navLink =
  "flex items-center gap-1.5 rounded-md px-2 py-2 text-sm text-fg-muted transition-colors hover:bg-fg/[0.06] hover:text-fg";

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
    { media: "(prefers-color-scheme: light)", color: "#faf9f7" },
    { media: "(prefers-color-scheme: dark)", color: "#131211" },
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
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${sourceSerif.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body className="flex min-h-full flex-col bg-surface font-sans text-fg">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteJsonLd).replace(/</g, "\\u003c") }}
        />
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <HeaderHeight />
        <header
          data-site-header
          className="sticky top-0 z-40 border-b border-line bg-raised/85 backdrop-blur-md"
        >
          <div className="mx-auto flex max-w-3xl items-center justify-between gap-2 px-4 py-2">
            <div className="flex items-center gap-0.5">
              <Link
                href="/"
                className="mr-1.5 rounded-md px-1.5 py-1 font-serif text-lg font-semibold tracking-tight transition-colors hover:bg-fg/[0.06]"
              >
                Ask Graham
              </Link>
              <Link href="/export" aria-label="Export essays" className={navLink}>
                <DownloadIcon size={16} />
                <span className="hidden sm:inline">Export</span>
              </Link>
              <Link href="/favorites" aria-label="Favorites" className={navLink}>
                <BookmarkIcon size={16} />
                <span className="hidden sm:inline">Favorites</span>
              </Link>
              <a
                href="https://github.com/balewgize/askgraham"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="View source on GitHub"
                className={navLink}
              >
                <GitHubIcon size={17} />
              </a>
            </div>
            <div className="flex items-center gap-1">
              <SearchPalette />
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main id="main" className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 sm:py-10">
          {children}
        </main>
        <footer className="border-t border-line py-5 text-center text-sm text-fg-subtle">
          Personal learning tool · Essays by Paul Graham ·{" "}
          <a
            href="https://www.paulgraham.com"
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2 hover:text-fg-muted"
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
