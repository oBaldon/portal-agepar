// src/types.ts

/* =============================================================================
   Tipos centrais do Portal (Catálogo, Blocos, Categorias, Usuário)
   =============================================================================
   - Retrocompatível: se "categories" não vier no catálogo, tudo segue funcionando.
   - As categorias servem para organizar a navbar e os cards da Home por grupos.
   - "categoryId" no Block referencia Category.id (ex.: "compras").
   - Autenticação: mock é legado; manter apenas para ambientes com AUTH_MODE=mock.
   ============================================================================= */

export type AuthMode = "local" | "oidc" | "mock";

/** Link de navegação gerado por um bloco. */
export type NavigationLink = {
  /** Texto exibido no menu/rotas. */
  label: string;
  /** Caminho SPA (ex.: "/form2json"). */
  path: string;
  /** Nome de ícone (ex.: "Home", "FileJson") – opcional. */
  icon?: string;
};

/** Rotas expostas pelo bloco. */
export type BlockRoute =
  | { path: string; kind: "iframe" }
  | { path: string; kind: "react" };

/** UI do bloco: se "iframe", embutimos a URL; se "react", renderizamos componente local. */
export type BlockUI =
  | { type: "iframe"; url: string }
  | { type: "react"; component?: string };

/** Categoria para agrupar blocos (aparece na navbar e em /categoria/:id). */
export type Category = {
  /** Identificador estável (slug). ex.: "compras", "fiscalizacao", "lab". */
  id: string;
  /** Rótulo exibido para o usuário. ex.: "Compras". */
  label: string;
  /** Nome de ícone (opcional). ex.: "ShoppingCart". */
  icon?: string;
  /** Ordenação da categoria (menor = aparece primeiro). */
  order?: number;
};

/** Metadados e definição de um bloco/automação. */
export type Block = {
  /** Nome técnico único. ex.: "form2json". */
  name: string;
  /** Nome amigável. ex.: "Formulário para JSON". */
  displayName?: string; // opcional p/ retrocompat
  /** Versão do bloco (para exibição/auditoria). */
  version: string;

  /** Como o bloco será exibido. */
  ui: BlockUI;
  /** Links gerados pelo bloco (usados para roteamento SPA). */
  navigation?: NavigationLink[]; // opcional p/ retrocompat
  /** Rotas reais do bloco (precisam existir no Router). */
  routes?: BlockRoute[]; // opcional p/ retrocompat

  // ---- Metadados opcionais (retrocompatíveis) ----
  /** Categoria à qual o bloco pertence (Category.id). */
  categoryId?: string;
  /** Rótulos livres para busca/filtragem. */
  tags?: string[];
  /** Descrição curta (aparece no card da Home/Categoria). */
  description?: string;
  /** Se true, esconder na lista/menus (mas rotas continuam válidas). */
  hidden?: boolean;
  /** Ordenação dentro da categoria (menor = aparece primeiro). */
  order?: number;

  /**
   * RBAC simples: se definido, só exibir o bloco para usuários que tenham
   * AO MENOS um dos roles listados (ex.: ["compras.editor"]).
   * A checagem é responsabilidade da UI (helpers abaixo podem ajudar).
   */
  requiredRoles?: string[];
};

/** Catálogo entregue pelo BFF e consumido pelo host. */
export type Catalog = {
  /** ISO string de quando o catálogo foi gerado. */
  generatedAt?: string; // opcional p/ retrocompat
  /** Metadados do host. */
  host: { version: string; minBlockEngine: string };
  /** Categorias disponíveis (opcional para manter retrocompatibilidade). */
  categories?: Category[];
  /** Lista de blocos/automações registradas. */
  blocks: Block[];
};

/** Usuário autenticado (via sessão). */
export type User = {
  cpf: string | null;
  nome: string;
  email: string | null;
  roles: string[];
  unidades: string[];
  /** Mecanismo de auth atual. "mock" é legado e só deve aparecer em DEV. */
  auth_mode?: AuthMode;
  is_superuser?: boolean;
};

/* =============================================================================
   Helpers (agrupamento, ordenação e RBAC simples)
   ============================================================================= */

/** Categoria padrão usada quando o bloco não define categoryId. */
export const DEFAULT_CATEGORY: Category = {
  id: "uncategorized",
  label: "Outros",
};

/**
 * Resolve a categoria de um bloco. Se categoryId não bater com nenhuma categoria
 * do catálogo, cai em DEFAULT_CATEGORY.
 */
export function resolveCategoryForBlock(
  block: Block,
  categories?: Category[]
): Category {
  if (!block.categoryId) return DEFAULT_CATEGORY;
  const found = categories?.find((c) => c.id === block.categoryId);
  return found ?? DEFAULT_CATEGORY;
}

/**
 * Agrupa blocos por categoria, ignorando os com `hidden === true`.
 *
 * Regras de ordenação:
 *  - Categorias: seguem a ordem de escrita em `catalog.categories`.
 *    * Categorias não listadas em `catalog.categories` aparecem no final,
 *      na ordem em que forem encontradas ao percorrer os blocos.
 *  - Blocos: preservam a ordem de escrita em `catalog.blocks` (sem sort),
 *    garantindo que o que está no JSON é o que aparece na UI.
 */
export function groupBlocksByCategory(
  blocks: Block[],
  categories?: Category[]
): Array<{ category: Category; blocks: Block[] }> {
  // Mapa: categoria -> índice conforme escrita em catalog.categories
  const catIndex: Record<string, number> = {};
  categories?.forEach((c, i) => {
    catIndex[c.id] = i;
  });
  let nextIdx = categories ? categories.length : 0; // para categorias não listadas

  // buckets com índice de ordenação de categorias
  const buckets: Record<
    string,
    { category: Category; blocks: Block[]; idx: number }
  > = {};

  const getBucket = (b: Block) => {
    const cat = resolveCategoryForBlock(b, categories);
    if (!buckets[cat.id]) {
      const idx = Object.prototype.hasOwnProperty.call(catIndex, cat.id)
        ? catIndex[cat.id]
        : nextIdx++; // categoria fora da lista → vai para o final, na ordem encontrada
      buckets[cat.id] = { category: cat, blocks: [], idx };
    }
    return buckets[cat.id];
  };

  // Preserva a ordem dos blocos como escrita no catálogo (sem sort)
  for (const b of blocks) {
    if (b.hidden) continue;
    getBucket(b).blocks.push(b);
  }

  // Ordena apenas as categorias pela ordem de escrita
  return Object.values(buckets)
    .sort((a, b) => a.idx - b.idx)
    .map(({ category, blocks }) => ({ category, blocks }));
}

/**
 * RBAC simples (ANY-of):
 * - Se o bloco estiver `hidden` => false.
 * - Se não exige roles => público.
 * - Caso contrário, o usuário precisa ter pelo menos um dos roles exigidos
 *   (com normalização para lower-case e trim).
 */
export function userCanSeeBlock(user: User | null, block: Block): boolean {
  if (block.hidden) return false;

  const required = block.requiredRoles ?? [];
  if (required.length === 0) return true;

  if (!user) return false;
  const userRoles = new Set((user.roles || []).map(r => r.trim().toLowerCase()));

  // bypass para admin/superuser
  if (user.is_superuser || userRoles.has("admin")) return true;

  return required.some(r => userRoles.has(r.trim().toLowerCase()));
}

/** Helper para identificar sessão mock (legado), útil para banners/avisos em DEV. */
export function isMockSession(user: User | null): boolean {
  return !!user && user.auth_mode === "mock";
}
