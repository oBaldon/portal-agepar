import type { Catalog, Category, Block, User } from "@/types";
import { userCanSeeBlock } from "@/types";

export async function loadCatalog(): Promise<Catalog> {
  const url = import.meta.env.VITE_CATALOG_URL || "/catalog/dev";
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`catálogo: HTTP ${res.status}`);
  return (await res.json()) as Catalog;
}

/** RBAC ANY-of helper */
export const anyRole = (userRoles: string[] = [], required?: string[]): boolean => {
  if (!required || required.length === 0) return true;
  for (const r of required) {
    if (userRoles.includes(r)) return true;
  }
  return false;
};

/** Blocos visíveis ao usuário (RBAC + hidden), preservando a ordem declarada no catálogo */
export const visibleBlocks = (catalog: Catalog, user?: User): Block[] => {
  const blocks = catalog?.blocks ?? [];
  return blocks.filter((b) => userCanSeeBlock(user ?? null, b));
};

/** Categorias visíveis: não-hidden, RBAC ok e com pelo menos 1 bloco visível dentro */
export const visibleCategories = (catalog: Catalog, user?: User): Category[] => {
  const roles = user?.roles ?? [];
  const cats = catalog?.categories ?? [];
  const vBlocks = new Set(visibleBlocks(catalog, user).map((b) => b.categoryId));

  return cats.filter((c) => {
    const hidden = (c as any).hidden as boolean | undefined;
    const required = (c as any).requiredRoles as string[] | undefined;
    if (hidden) return false;
    if (!anyRole(roles, required)) return false;
    return vBlocks.has(c.id);
  });
};

/** Opcional: retorna o catálogo já filtrado para o usuário (útil no App) */
export const filterCatalogForUser = (catalog: Catalog, user?: User) => ({
  categories: visibleCategories(catalog, user),
  blocks: visibleBlocks(catalog, user),
});
