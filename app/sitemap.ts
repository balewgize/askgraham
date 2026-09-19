import type { MetadataRoute } from "next";
import { getSlugs } from "@/lib/essays";
import { getPaths } from "@/lib/paths";
import { SITE_URL } from "@/lib/site";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [slugs, paths] = await Promise.all([getSlugs(), getPaths()]);
  const lastModified = new Date();

  return [
    { url: `${SITE_URL}/`, lastModified, changeFrequency: "weekly", priority: 1 },
    { url: `${SITE_URL}/export`, lastModified, changeFrequency: "monthly", priority: 0.6 },
    ...paths.map((p) => ({
      url: `${SITE_URL}/paths/${p.id}`,
      lastModified,
      changeFrequency: "monthly" as const,
      priority: 0.7,
    })),
    ...slugs.map((slug) => ({
      url: `${SITE_URL}/essays/${slug}`,
      lastModified,
      changeFrequency: "yearly" as const,
      priority: 0.8,
    })),
  ];
}
