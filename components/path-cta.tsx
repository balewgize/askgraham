import Link from "next/link";
import type { ResolvedPath } from "@/lib/paths";

/** The single "start here" entry point shown above the catalog. */
export default function PathCta({ path, secondary }: { path: ResolvedPath; secondary?: ResolvedPath }) {
  return (
    <section className="mb-8 rounded-xl border border-orange-500/30 bg-orange-50 p-4 dark:border-orange-400/20 dark:bg-orange-950/20">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-orange-600 dark:text-orange-400">
        New to Paul Graham?
      </p>
      <div className="mt-1 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="font-serif text-lg font-bold tracking-tight sm:text-xl" style={{ fontFamily: "Georgia, serif" }}>
          {path.title}
        </h2>
        <span className="text-xs text-zinc-500">{path.steps.length} essays</span>
      </div>
      <p className="mt-1 max-w-[60ch] text-sm text-zinc-600 dark:text-zinc-300">{path.subtitle}</p>
      <div className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-2">
        <Link
          href={`/paths/${path.id}`}
          className="inline-block rounded-full bg-zinc-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
        >
          Start reading →
        </Link>
        {secondary && (
          <Link
            href={`/paths/${secondary.id}`}
            className="text-sm text-zinc-600 underline decoration-zinc-300 underline-offset-2 hover:text-zinc-900 dark:text-zinc-400 dark:decoration-zinc-600 dark:hover:text-zinc-100"
          >
            Starting a company? Follow the founder path →
          </Link>
        )}
      </div>
    </section>
  );
}
