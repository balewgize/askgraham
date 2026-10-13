import type { Metadata } from "next";
import { notFound } from "next/navigation";
import EssayReader from "@/components/essay-reader";
import { formatDateShort } from "@/lib/dates";
import { getEssay, getPrevNext, getSlugs } from "@/lib/essays";
import { getResolvedPaths } from "@/lib/paths";
import { getPhases } from "@/lib/phases";
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
  const [phases, paths] = await Promise.all([getPhases(), getResolvedPaths()]);
  const why = phases?.essays[slug]?.why;
  const essayPaths = paths.filter((p) => p.steps.some((s) => s.slug === slug));

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
      <header className="mb-7 max-w-[34em]">
        <h1 className="font-serif text-[1.9rem] font-semibold leading-[1.15] tracking-tight text-balance sm:text-[2.35rem]">
          {essay.title}
        </h1>
        <p className="mt-2.5 text-sm tabular-nums text-fg-subtle">
          {formatDateShort(essay.date)} · {essay.reading_time_min} min read ·{" "}
          <a
            href={essay.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-fg-muted underline underline-offset-2 transition-colors hover:text-fg"
          >
            original ↗
          </a>
        </p>
      </header>
      <EssayReader essay={essay} prev={prev} next={next} why={why} paths={essayPaths} />
    </div>
  );
}