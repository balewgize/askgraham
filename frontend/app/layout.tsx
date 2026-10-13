import { SpeedInsights } from '@vercel/speed-insights/next';
import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Source_Serif_4 } from "next/font/google";
import HeaderHeight from "@/components/header-height";
import SiteHeader from "@/components/site-header";
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
      <body className="flex min-h-full flex-col overflow-x-clip bg-surface font-sans text-fg">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteJsonLd).replace(/</g, "\\u003c") }}
        />
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <HeaderHeight />
        <SiteHeader />
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
