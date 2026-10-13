import type { Metadata } from "next";
import EssayIndex from "@/components/essay-index";
import StartHere from "@/components/start-here";
import { getIndex } from "@/lib/essays";
import { getResolvedPaths } from "@/lib/paths";
import { getPhases, getTaxonomy } from "@/lib/phases";
import { SITE_DESCRIPTION, SITE_URL } from "@/lib/site";

export const dynamic = "force-static";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
  openGraph: { url: SITE_URL, title: "Paul Graham's Essays — Full Text, Searchable & Filterable", description: SITE_DESCRIPTION },
};

export default async function Home() {
  const [index, taxonomy, phases, paths] = await Promise.all([
    getIndex(),
    getTaxonomy(),
    getPhases(),
    getResolvedPaths(),
  ]);

  const classified = phases && Object.keys(phases.essays).length > 0;
  const chips = classified
    ? [...taxonomy.phases].sort((a, b) => a.order - b.order).map((p) => ({ id: p.id, label: p.label }))
    : [];
  const essayPhases = classified
    ? Object.fromEntries(
        Object.entries(phases.essays).map(([slug, v]) => [slug, { phases: v.phases }]),
      )
    : {};

  const hero = <StartHere paths={paths} />;

  return <EssayIndex entries={index} chips={chips} essayPhases={essayPhases} hero={hero} />;
}