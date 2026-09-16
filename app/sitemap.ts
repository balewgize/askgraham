import type { MetadataRoute } from "next";
import { getSlugs } from "@/lib/essays";
import { SITE_URL } from "@/lib/site";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const slugs = await getSlugs();
  const lastModified = new Date();

  return [
    { url: `${SITE_URL}/`, lastModified, changeFrequency: "weekly", priority: 1 },
    { url: `${SITE_URL}/corpus`, lastModified, changeFrequency: "monthly", priority: 0.6 },
    ...slugs.map((slug) => ({
      url: `${SITE_URL}/essays/${slug}`,
      lastModified,
      changeFrequency: "yearly" as const,
      priority: 0.8,
    })),
  ];
}
