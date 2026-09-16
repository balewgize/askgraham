import EssayIndex from "@/components/essay-index";
import { getIndex } from "@/lib/essays";
import { getPhases, getTaxonomy } from "@/lib/phases";

export const dynamic = "force-static";

export default async function Home() {
  const [index, taxonomy, phases] = await Promise.all([getIndex(), getTaxonomy(), getPhases()]);

  const classified = phases && Object.keys(phases.essays).length > 0;
  const chips = classified
    ? [...taxonomy.phases].sort((a, b) => a.order - b.order).map((p) => ({ id: p.id, label: p.label }))
    : [];
  const essayPhases = classified
    ? Object.fromEntries(
        Object.entries(phases.essays).map(([slug, v]) => [slug, { phases: v.phases, why: v.why }]),
      )
    : {};

  return <EssayIndex entries={index} chips={chips} essayPhases={essayPhases} />;
}
