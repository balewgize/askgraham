import type { Metadata } from "next";
import FavoritesList from "@/components/favorites-list";
import { getIndex } from "@/lib/essays";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Favorites",
  description: "Paul Graham essays you've saved to read later.",
  alternates: { canonical: "/favorites" },
  robots: { index: false, follow: true },
};

export default async function FavoritesPage() {
  const entries = await getIndex();
  return <FavoritesList entries={entries} />;
}