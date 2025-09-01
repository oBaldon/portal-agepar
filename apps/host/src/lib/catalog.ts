import type { Catalog } from "@/types";

export async function loadCatalog(): Promise<Catalog> {
  const url = import.meta.env.VITE_CATALOG_URL || "/catalog/dev";
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`catálogo: HTTP ${res.status}`);
  return (await res.json()) as Catalog;
}
