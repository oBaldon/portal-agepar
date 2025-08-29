import type { Catalog } from "./types";
export async function loadCatalog(url: string): Promise<Catalog> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error("Falha ao carregar catálogo");
  return res.json();
}
