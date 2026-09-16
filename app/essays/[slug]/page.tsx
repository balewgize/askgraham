import Link from "next/link";
import { notFound } from "next/navigation";
import EssayReader from "@/components/essay-reader";
import { getEssay, getPrevNext, getSlugs } from "@/lib/essays";

export const dynamic = "force-static";

export async function generateStaticParams() {
  const slugs = await getSlugs();
  return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  try {
    const essay = await getEssay(slug);
    return {
      title: `${essay.title} — Ask Graham`,
      description: `${essay.title} by Paul Graham${essay.date ? ` (${essay.date})` : ""} · ${essay.reading_time_min} min read`,
    };
  } catch {
    return { title: "Not found — Ask Graham" };
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

  return (
    <div>
      <nav className="mb-6 text-xs text-zinc-500">
        <Link href="/" className="hover:underline">
          ← All essays
        </Link>
      </nav>
      <header className="mb-8 max-w-[70ch]">
        <h1 className="font-serif text-3xl font-bold leading-tight tracking-tight" style={{ fontFamily: "Georgia, serif" }}>
          {essay.title}
        </h1>
        <p className="mt-2 text-sm text-zinc-500">
          {essay.date ?? "undated"} · {essay.word_count.toLocaleString()} words · {essay.reading_time_min} min read ·{" "}
          <a href={essay.url} target="_blank" rel="noopener noreferrer" className="underline hover:text-zinc-700 dark:hover:text-zinc-300">
            original ↗
          </a>
        </p>
      </header>
      <EssayReader essay={essay} prev={prev} next={next} />
    </div>
  );
}
