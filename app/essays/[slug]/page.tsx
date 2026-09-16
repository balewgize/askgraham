import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import EssayReader from "@/components/essay-reader";
import { formatDateShort } from "@/lib/dates";
import { getEssay, getPrevNext, getSlugs } from "@/lib/essays";
import { essayDescription, isoDate } from "@/lib/seo";
import { SITE_KEYWORDS, SITE_NAME, SITE_URL } from "@/lib/site";

export const dynamic = "force-static";

export async function generateStaticParams() {
  const slugs = await getSlugs();
  return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  try {
    const essay = await getEssay(slug);
    const description = essayDescription(essay);
    const title = `${essay.title} by Paul Graham`;
    return {
      title,
      description,
      keywords: [essay.title, ...SITE_KEYWORDS],
      alternates: { canonical: `/essays/${slug}` },
      openGraph: {
        type: "article",
        title,
        description,
        url: `${SITE_URL}/essays/${slug}`,
        publishedTime: isoDate(essay.date),
        authors: ["Paul Graham"],
      },
      twitter: { card: "summary_large_image", title, description },
    };
  } catch {
    return { title: "Not found" };
  }
}

export default async function EssayPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let essay;
  try {
    essay = await getEssay(slug);
  } catch {
    notFound();
  }
  const { prev, next } = await getPrevNext(slug);

  const description = essayDescription(essay);
  const url = `${SITE_URL}/essays/${essay.slug}`;
  const published = isoDate(essay.date);
  const articleJsonLd = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: essay.title,
    description,
    url,
    mainEntityOfPage: url,
    author: { "@type": "Person", name: "Paul Graham", url: "https://www.paulgraham.com" },
    ...(published ? { datePublished: published, dateModified: published } : {}),
    wordCount: essay.word_count,
    timeRequired: `PT${essay.reading_time_min}M`,
    inLanguage: "en",
    isPartOf: { "@type": "WebSite", name: SITE_NAME, url: SITE_URL },
    publisher: { "@type": "Organization", name: SITE_NAME, url: SITE_URL },
  };
  const breadcrumbJsonLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "All essays", item: SITE_URL },
      { "@type": "ListItem", position: 2, name: essay.title, item: url },
    ],
  };

  return (
    <div>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(articleJsonLd).replace(/</g, "\\u003c") }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbJsonLd).replace(/</g, "\\u003c") }}
      />
      <nav className="mb-6 text-xs text-zinc-500">
        <Link href="/" className="hover:underline">
          ← All essays
        </Link>
      </nav>
      <header className="mb-8 max-w-[70ch]">
        <h1 className="font-serif text-2xl font-bold leading-tight tracking-tight sm:text-3xl" style={{ fontFamily: "Georgia, serif" }}>
          {essay.title}
        </h1>
        <p className="mt-2 text-sm text-zinc-500">
          {formatDateShort(essay.date)} · {essay.word_count.toLocaleString()} words · {essay.reading_time_min} min read ·{" "}
          <a href={essay.url} target="_blank" rel="noopener noreferrer" className="underline hover:text-zinc-700 dark:hover:text-zinc-300">
            original ↗
          </a>
        </p>
      </header>
      <EssayReader essay={essay} prev={prev} next={next} />
    </div>
  );
}
