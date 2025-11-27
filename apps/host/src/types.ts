// src/types.ts

/**
 * Tipos centrais do Portal (Catálogo, Blocos, Categorias, Usuário).
 *
 * Propósito
 * ---------
 * Padronizar as estruturas compartilhadas entre o Host (frontend) e o BFF,
 * mantendo retrocompatibilidade quando possível (ex.: `categories` opcional).
 *
 * Segurança
 * ---------
 * Somente declarações de tipos e helpers puros; não há efeitos colaterais
 * nem manipulação de dados sensíveis.
 *
 * Referências
 * -----------
 * - Design de catálogo do Host (blocos/categorias e RBAC simples).
 * - Integração com BFF: campos esperados em `/api/automations` e `/catalog/*`.
 *
 * Observações
 * -----------
 * A lógica foi preservada integralmente; foram removidos comentários dispersos
 * e adicionadas docstrings JSDoc sem alterar comportamento.
 */

export type AuthMode = "local" | "oidc" | "mock";

/** Link de navegação gerado por um bloco. */
export type NavigationLink = {
  /** Texto exibido no menu/rotas. */
  label: string;
  /** Caminho SPA (ex.: "/form2json"). */
  path: string;
  /** Nome de ícone (ex.: "Home", "FileJson"). */
  icon?: string;
};

/** Rotas expostas pelo bloco. */
export type BlockRoute =
  | { path: string; kind: "iframe" }
  | { path: string; kind: "react" };

/** UI do bloco: iframe externo ou componente React hospedado. */
export type BlockUI =
  | { type: "iframe"; url: string }
  | { type: "react"; component?: string };

/** Categoria para agrupar blocos (navbar e /categoria/:id). */
export type Category = {
  /** Identificador estável (slug), ex.: "compras". */
  id: string;
  /** Rótulo exibido, ex.: "Compras". */
  label: string;
  /** Nome de ícone (opcional), ex.: "ShoppingCart". */
  icon?: string;
  /** Ordenação (menor = primeiro). */
  order?: number;
  /** Esconde a categoria na navegação. */
  hidden?: boolean;
  /** RBAC ANY-of para a categoria (além do RBAC por bloco). */
  requiredRoles?: string[];
};

/** Metadados e definição de um bloco/automação. */
export type Block = {
  /** Nome técnico único, ex.: "form2json". */
  name: string;
  /** Nome amigável (retrocompat). */
  displayName?: string;
  /** Versão do bloco. */
  version: string;

  /** Modo de exibição. */
  ui: BlockUI;
  /** Links de navegação (retrocompat). */
  navigation?: NavigationLink[];
  /** Rotas reais do bloco (retrocompat). */
  routes?: BlockRoute[];

  /** Categoria (Category.id). */
  categoryId?: string;
  /** Rótulos livres. */
  tags?: string[];
  /** Descrição curta para cards. */
  description?: string;
  /** Se true, esconde da lista/menus (rotas continuam válidas). */
  hidden?: boolean;
  /** Ordenação dentro da categoria (menor = primeiro). */
  order?: number;

  /**
   * RBAC ANY-of: se definido, o usuário precisa ter pelo menos um dos roles.
   * A checagem é feita na UI.
   */
  requiredRoles?: string[];
  /** Se true, apenas superusers visualizam (admin não basta). */
  superuserOnly?: boolean;
};

/** Catálogo entregue pelo BFF e consumido pelo host. */
export type Catalog = {
  /** ISO de geração do catálogo (retrocompat). */
  generatedAt?: string;
  /** Metadados do host. */
  host: { version: string; minBlockEngine: string };
  /** Categorias disponíveis (opcional para retrocompatibilidade). */
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
  /** Mecanismo de auth atual ("mock" apenas em DEV). */
  auth_mode?: AuthMode;
  is_superuser?: boolean;
  /**
   * Quando true, o servidor exige troca de senha antes de permitir navegação.
   * Retornado por /api/auth/login e /api/me.
   */
  must_change_password?: boolean;
};

/* =============================================================================
   Helpers (agrupamento, ordenação e RBAC simples)
   ============================================================================= */

/** Categoria padrão usada quando o bloco não define `categoryId`. */
export const DEFAULT_CATEGORY: Category = {
  id: "uncategorized",
  label: "Outros",
};

/**
 * Resolve a categoria de um bloco.
 *
 * @param block Bloco de origem.
 * @param categories Lista de categorias conhecidas.
 * @returns Categoria correspondente ou `DEFAULT_CATEGORY`.
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
 * Ordenação:
 * - Categorias seguem a ordem de escrita em `catalog.categories`.
 * - Categorias não listadas aparecem ao final na ordem de descoberta.
 * - Blocos preservam a ordem original em `catalog.blocks`.
 *
 * @param blocks Blocos a agrupar.
 * @param categories Categorias conhecidas (opcional).
 * @returns Array de buckets { category, blocks } na ordem calculada.
 */
export function groupBlocksByCategory(
  blocks: Block[],
  categories?: Category[]
): Array<{ category: Category; blocks: Block[] }> {
  const catIndex: Record<string, number> = {};
  categories?.forEach((c, i) => {
    catIndex[c.id] = i;
  });
  let nextIdx = categories ? categories.length : 0;

  const buckets: Record<
    string,
    { category: Category; blocks: Block[]; idx: number }
  > = {};

  const getBucket = (b: Block) => {
    const cat = resolveCategoryForBlock(b, categories);
    if (!buckets[cat.id]) {
      const idx = Object.prototype.hasOwnProperty.call(catIndex, cat.id)
        ? catIndex[cat.id]
        : nextIdx++;
      buckets[cat.id] = { category: cat, blocks: [], idx };
    }
    return buckets[cat.id];
  };

  for (const b of blocks) {
    if (b.hidden) continue;
    getBucket(b).blocks.push(b);
  }

  return Object.values(buckets)
    .sort((a, b) => a.idx - b.idx)
    .map(({ category, blocks }) => ({ category, blocks }));
}

/**
 * RBAC simples (ANY-of).
 *
 * Regras:
 * - `hidden` → false.
 * - `superuserOnly` → exige `is_superuser === true`.
 * - `requiredRoles` vazio/ausente → público.
 * - Caso contrário, usuário precisa ter ao menos um dos roles.
 * - Bypass para `is_superuser` ou role `admin`.
 *
 * @param user Usuário atual (ou null).
 * @param block Bloco alvo.
 * @returns `true` se o usuário pode ver o bloco.
 */
export function userCanSeeBlock(user: User | null, block: Block): boolean {
  if (block.hidden) return false;
  if (block.superuserOnly) {
    return !!(user && user.is_superuser === true);
    }
  const required = block.requiredRoles ?? [];
  if (required.length === 0) return true;
  if (!user) return false;

  const userRoles = new Set((user.roles || []).map((r) => r.trim().toLowerCase()));
  if (user.is_superuser || userRoles.has("admin")) return true;

  return required.some((r) => userRoles.has(r.trim().toLowerCase()));
}

/**
 * Indica se a sessão atual é do modo mock (legado).
 *
 * @param user Usuário atual (ou null).
 * @returns `true` para sessões mock (ambientes de DEV).
 */
export function isMockSession(user: User | null): boolean {
  return !!user && user.auth_mode === "mock";
}
