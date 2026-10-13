import type { Metadata } from "next";
import { notFound } from "next/navigation";
import PathView from "@/components/path-view";
import { getResolvedPaths } from "@/lib/paths";
import { SITE_URL } from "@/lib/site";

export const dynamic = "force-static";

export async function generateStaticParams() {
  const paths = await getResolvedPaths();
  return paths.map((p) => ({ id: p.id }));
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const paths = await getResolvedPaths();
  const path = paths.find((p) => p.id === id);
  if (!path) return { title: "Not found" };
  const title = `${path.title} — a Paul Graham reading path`;
  const description = `${path.description} ${path.steps.length} essays, in order, from paulgraham.com.`;
  return {
    title,
    description,
    alternates: { canonical: `/paths/${path.id}` },
    openGraph: { type: "article", title, description, url: `${SITE_URL}/paths/${path.id}` },
    twitter: { card: "summary_large_image", title, description },
  };
}

export default async function PathPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const paths = await getResolvedPaths();
  const path = paths.find((p) => p.id === id);
  if (!path) notFound();

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: path.title,
    description: path.description,
    numberOfItems: path.steps.length,
    itemListElement: path.steps.map((s, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: s.title,
      url: `${SITE_URL}/essays/${s.slug}`,
    })),
  };

  return (
    <div>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }}
      />
      <PathView path={path} />
    </div>
  );
}
