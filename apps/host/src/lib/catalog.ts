// apps/host/src/lib/catalog.ts
import type { Catalog, Category, Block, User } from "@/types";
import { userCanSeeBlock } from "@/types";

/**
 * Carrega o catálogo de blocos/categorias do backend.
 *
 * Propósito
 * ---------
 * - Obter a definição (metadados) de blocos e categorias exibidos no app.
 * - Respeita credenciais de sessão via `credentials: "include"`.
 *
 * Retorno
 * -------
 * `Promise<Catalog>` com a estrutura crua do catálogo.
 *
 * Erros
 * -----
 * Lança `Error("catálogo: HTTP <status>")` quando a resposta não for 2xx.
 *
 * Referências
 * -----------
 * - MDN Fetch API: https://developer.mozilla.org/docs/Web/API/Fetch_API
 */
export async function loadCatalog(): Promise<Catalog> {
  const url = import.meta.env.VITE_CATALOG_URL || "/catalog/dev";
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`catálogo: HTTP ${res.status}`);
  return (await res.json()) as Catalog;
}

/**
 * Verifica RBAC no modo ANY-of (qualquer um dos papéis exigidos).
 *
 * Parâmetros
 * ----------
 * - `userRoles`: papéis do usuário autenticado (array).
 * - `required`: papéis aceitos para o recurso (qualquer um deles habilita acesso).
 *
 * Retorno
 * -------
 * `true` se:
 *  - `required` estiver vazio/indefinido; ou
 *  - houver interseção entre `userRoles` e `required`.
 *
 * Referências
 * -----------
 * - Modelo ANY-of (controle de acesso): prática comum em RBAC.
 */
export const anyRole = (userRoles: string[] = [], required?: string[]): boolean => {
  if (!required || required.length === 0) return true;
  for (const r of required) {
    if (userRoles.includes(r)) return true;
  }
  return false;
};

/**
 * Retorna os blocos visíveis ao usuário, mantendo a ordem do catálogo.
 *
 * Regras de visibilidade
 * ----------------------
 * - Delegada a `userCanSeeBlock(user, block)` (RBAC + flags como `hidden`).
 *
 * Parâmetros
 * ----------
 * - `catalog`: catálogo completo (cru).
 * - `user`: snapshot do usuário (opcional).
 *
 * Retorno
 * -------
 * `Block[]` somente com os blocos que o usuário pode ver.
 */
export const visibleBlocks = (catalog: Catalog, user?: User): Block[] => {
  const blocks = catalog?.blocks ?? [];
  return blocks.filter((b) => userCanSeeBlock(user ?? null, b));
};

/**
 * Retorna as categorias visíveis, na ordem do catálogo, desde que:
 * - não estejam marcadas como `hidden`;
 * - passem no RBAC (ANY-of em `requiredRoles`);
 * - contenham pelo menos 1 bloco visível para o usuário.
 *
 * Parâmetros
 * ----------
 * - `catalog`: catálogo completo (cru).
 * - `user`: snapshot do usuário (opcional).
 *
 * Retorno
 * -------
 * `Category[]` filtradas por visibilidade efetiva.
 */
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

/**
 * Convenience: devolve o catálogo já filtrado para o usuário.
 *
 * Retorno
 * -------
 * Objeto `{ categories, blocks }` contendo apenas elementos visíveis.
 *
 * Uso típico
 * ----------
 * - Otimiza o estado exibido no App/Router, evitando filtros repetidos.
 */
export const filterCatalogForUser = (catalog: Catalog, user?: User) => ({
  categories: visibleCategories(catalog, user),
  blocks: visibleBlocks(catalog, user),
});
