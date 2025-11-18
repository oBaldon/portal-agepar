---
id: ordem-de-categorias-blocos
title: "Ordem de categorias/blocos"
sidebar_position: 5
---

Esta página define **como o Host determina a ordem** de exibição de **categorias** e **blocos** do catálogo. A regra padrão do projeto é **preservar a ordem de escrita do catálogo** (sem reordenar), e permitir **ordenação explícita** apenas quando solicitado via campo `order`.

> Referências principais:  
> `apps/host/src/types.ts`, `apps/host/src/lib/catalog.ts`,  
> `apps/host/src/pages/CategoryView.tsx`, `catalog/catalog.dev.json`

---

## 1) Regra padrão

- **Categorias**: exibidas na **mesma ordem** em que aparecem em `catalog.categories`.  
- **Blocos** (dentro de cada categoria): exibidos na **mesma ordem** em que aparecem em `catalog.blocks`.  
- **RBAC** e `hidden` são aplicados **antes** da ordenação; itens não visíveis são descartados.

Quando necessário, um item pode informar `order: number`. Valores **menores** aparecem **antes**. Itens **sem `order`** preservam a ordem relativa original.

---

## 2) Tipos relevantes (resumo)

```ts
// apps/host/src/types.ts (trechos relevantes)
export type CatalogCategory = {
  id: string;
  label: string;
  icon?: string;
  order?: number;   // opcional
  hidden?: boolean;
};

export type CatalogBlock = {
  categoryId: string;
  ui: { type: "iframe"; url: string } | { type: "link"; href: string };
  requiredRoles?: string[];
  order?: number;   // opcional
  hidden?: boolean;
};
````

---

## 3) Utilitários de ordenação (estáveis)

> **Estável**: quando dois itens têm a **mesma chave** ou não têm `order`, mantém-se a ordem original do array.

```ts
// apps/host/src/lib/catalog.ts (sugestão)
type WithOrder = { order?: number };

export function stableSortByOrder<T extends WithOrder>(arr: T[]) {
  return arr
    .map((item, i) => ({ item, i }))
    .sort((a, b) => {
      const ao = a.item.order ?? Number.POSITIVE_INFINITY;
      const bo = b.item.order ?? Number.POSITIVE_INFINITY;
      if (ao !== bo) return ao - bo;
      return a.i - b.i; // estabilidade
    })
    .map(({ item }) => item);
}
```

---

## 4) Categorias visíveis e ordenação

```ts
// apps/host/src/lib/catalog.ts (exemplo)
import type { Catalog } from "../types";
import { anyRoleAllowed } from "./catalog"; // se estiver no mesmo arquivo, ajuste

// Retorna categorias com ao menos 1 bloco visível (preservando ordem original)
export function visibleCategoriesPreservingOrder(cat: Catalog, userRoles?: string[]) {
  const visibleCatIds = new Set<string>();
  for (const b of cat.blocks) {
    if (!b.hidden && anyRoleAllowed(userRoles, b.requiredRoles)) {
      visibleCatIds.add(b.categoryId);
    }
  }
  return cat.categories.filter(c => !c.hidden && visibleCatIds.has(c.id));
}

// Variante com 'order' explícito quando desejado
export function visibleCategoriesOrdered(cat: Catalog, userRoles?: string[]) {
  const vis = visibleCategoriesPreservingOrder(cat, userRoles);
  return stableSortByOrder(vis);
}
```

---

## 5) Blocos por categoria e ordenação

```ts
// apps/host/src/lib/catalog.ts (exemplo)
import type { Catalog, CatalogBlock } from "../types";

export function visibleBlocksForCategory(cat: Catalog, categoryId: string, userRoles?: string[]): CatalogBlock[] {
  return cat.blocks.filter(
    b => b.categoryId === categoryId && !b.hidden && anyRoleAllowed(userRoles, b.requiredRoles)
  );
}

// Variante ordenada por 'order' quando solicitado
export function visibleBlocksForCategoryOrdered(cat: Catalog, categoryId: string, userRoles?: string[]) {
  return stableSortByOrder(visibleBlocksForCategory(cat, categoryId, userRoles));
}
```

---

## 6) Uso no App (padrão vs. ordenado)

Por padrão (recomendado), **não** aplicamos sort — só filtragem (RBAC/hidden).
Para cenários que **pedem ordenação explícita**, use as variantes `*Ordered`.

```tsx
// apps/host/src/pages/CategoryView.tsx (trecho ilustrativo)
import React from "react";
import type { Catalog } from "../types";
import { visibleBlocksForCategory } from "../lib/catalog"; // padrão (sem sort)
// import { visibleBlocksForCategoryOrdered } from "../lib/catalog"; // com sort

export default function CategoryView({ catalog, userRoles }: { catalog: Catalog; userRoles?: string[] }) {
  const { id } = useParams<{ id: string }>();
  const blocks = visibleBlocksForCategory(catalog, id!, userRoles); // preserva ordem do catálogo
  // const blocks = visibleBlocksForCategoryOrdered(catalog, id!, userRoles); // com 'order'

  // render ...
  return <div className="grid">{/* ... */}</div>;
}
```

```tsx
// apps/host/src/components/Navbar.tsx (trecho)
import { visibleCategoriesPreservingOrder } from "../lib/catalog"; // padrão
// import { visibleCategoriesOrdered } from "../lib/catalog"; // com 'order'

const cats = visibleCategoriesPreservingOrder(catalog, userRoles);
```

---

## 7) Exemplo de catálogo (misturando `order` e padrão)

```json
{
  "categories": [
    { "id": "compras",   "label": "Compras" },           // sem order -> usa ordem do array
    { "id": "contratos", "label": "Contratos", "order": 1 },
    { "id": "orcamento", "label": "Orçamento", "order": 0 }
  ],
  "blocks": [
    { "categoryId": "compras", "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" } },
    { "categoryId": "compras", "ui": { "type": "iframe", "url": "/api/automations/pca/ui" }, "order": 0 },
    { "categoryId": "contratos", "ui": { "type": "iframe", "url": "/api/automations/tr/ui" } }
  ]
}
```

* Se **preservar ordem**: `compras`, `contratos`, `orcamento`. Blocos de `compras` na ordem em que aparecem (exceto se escolher a variante ordenada).
* Se **usar `order`**: `orcamento` (0), `contratos` (1), `compras` (∞). Em `compras`, o bloco `pca` (0) vem antes de `dfd` (∞).

---

## 8) Testes (Vitest) para ordenação estável

```ts
// apps/host/src/lib/catalog.order.spec.ts
import { describe, it, expect } from "vitest";
import { stableSortByOrder } from "./catalog";

describe("stableSortByOrder", () => {
  it("mantém ordem relativa para itens sem 'order'", () => {
    const input = [{ name: "a" }, { name: "b" }, { name: "c" }];
    const out = stableSortByOrder(input as any);
    expect(out.map((x: any) => x.name)).toEqual(["a", "b", "c"]);
  });
  it("ordena por 'order' e preserva estabilidade entre iguais", () => {
    const input = [{ name: "a", order: 2 }, { name: "b" }, { name: "c", order: 2 }, { name: "d", order: 1 }];
    const out = stableSortByOrder(input as any);
    expect(out.map((x: any) => x.name)).toEqual(["d", "a", "c", "b"]);
  });
});
```

---

## 9) Problemas comuns

* **Ordem “mudando sozinha”**
  Verifique se algum helper está aplicando `sort` sem necessidade. Use as funções “preserving order” por padrão.

* **Itens sem `order` indo para o fim**
  É o comportamento esperado quando **opta** por ordenar (`stableSortByOrder`). Se quiser manter itens sem `order` intercalados, **não aplique sort**.

* **Navbar vazia**
  Pode não haver blocos visíveis na categoria (RBAC/hidden). Reveja `requiredRoles`.

* **JSON reordenado pelo gerador**
  Se o catálogo for **gerado**, garanta que o **gerador respeite** a ordem de escrita desejada ou defina `order` explicitamente.

---

## Próximos passos

* **[Navbar por categorias e leitura do catálogo](./navbar-por-categorias-e-leitura-do-catálogo)**
* **[RBAC simples (requiredRoles ANY-of)](./rbac-simples-requiredroles-any-of)**
* **[Renderização de blocos (iframe ui.url)](./renderização-de-blocos-iframe-uiurl)**

---

> _Criado em 2025-11-18_
