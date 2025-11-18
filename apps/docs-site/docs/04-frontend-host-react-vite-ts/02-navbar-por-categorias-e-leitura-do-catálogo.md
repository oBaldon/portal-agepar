---
id: navbar-por-categorias-e-leitura-do-catálogo
title: "Navbar por categorias e leitura do catálogo"
sidebar_position: 2
---

Esta página explica como o **Host (React/Vite/TS)** lê o **catálogo** a partir do BFF e renderiza a **navbar por categorias**, respeitando **RBAC (ANY-of)** e a **ordem de escrita** do catálogo.

> Referências principais:  
> `apps/host/src/App.tsx`, `apps/host/src/lib/catalog.ts`, `apps/host/src/types.ts`, `apps/host/src/pages/CategoryView.tsx`

---

## 1) Conceito

A navbar exibe **categorias** do catálogo (dev: `/catalog/dev`), permitindo navegar para a visão de cada categoria.  
Regras:
- **Ordem**: por padrão **preserva a ordem do array** no catálogo. Se existir `order`, pode ser aplicada **sob demanda**.
- **RBAC**: categoria **só aparece** se tiver **pelo menos um bloco visível** ao usuário (regra ANY-of).
- **Ocultos**: itens com `hidden: true` não são exibidos.

```mermaid
flowchart LR
  C[Catalog JSON] --> L[catalog loader]
  L --> A[App]
  A --> N[Navbar]
  A --> P[Category view]
  N -->|category route| P
````

---

## 2) Estruturas do catálogo (tipos relevantes)

```ts
// apps/host/src/types.ts (resumo)
export type Role = string;

export type CatalogCategory = {
  id: string;
  label: string;
  icon?: string;
  order?: number;
  hidden?: boolean;
};

export type CatalogBlock = {
  categoryId: string;
  ui: { type: "iframe"; url: string } | { type: "link"; href: string };
  requiredRoles?: Role[]; // regra ANY-of
  order?: number;
  hidden?: boolean;
};

export type Catalog = {
  categories: CatalogCategory[];
  blocks: CatalogBlock[];
  generatedAt?: string;
};
```

---

## 3) Leitura do catálogo e utilitários (lib/catalog.ts)

```ts
// apps/host/src/lib/catalog.ts
import type { Catalog } from "../types";

export async function loadCatalog(): Promise<Catalog> {
  // via proxy do Vite: /catalog -> BFF
  const res = await fetch("/catalog/dev", { credentials: "include" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as Catalog;
}

// RBAC ANY-of
export function anyRoleAllowed(userRoles?: string[], required?: string[]) {
  if (!required || required.length === 0) return true;
  if (!userRoles || userRoles.length === 0) return false;
  return required.some((r) => userRoles.includes(r));
}

// Filtra blocos visíveis (RBAC + hidden)
export function visibleBlocks(blocks: Catalog["blocks"], userRoles?: string[]) {
  return blocks.filter((b) => !b.hidden && anyRoleAllowed(userRoles, b.requiredRoles));
}

// Retorna categorias com pelo menos 1 bloco visível
// Preserva a ORDEM DO ARRAY do catálogo por padrão.
export function visibleCategories(cat: Catalog, userRoles?: string[]) {
  const visByCat = new Map<string, number>();
  for (const b of visibleBlocks(cat.blocks, userRoles)) {
    visByCat.set(b.categoryId, (visByCat.get(b.categoryId) ?? 0) + 1);
  }
  return cat.categories.filter((c) => !c.hidden && visByCat.has(c.id));
}

// (Opcional) Ordem alternativa: priorizar 'order' quando definido.
// Só use se quiser ordenar explicitamente, caso contrário preserve o array original.
/*
export function sortByOrder<T extends { order?: number }>(arr: T[]) {
  return [...arr].sort((a, b) => (a.order ?? Number.POSITIVE_INFINITY) - (b.order ?? Number.POSITIVE_INFINITY));
}
*/
```

---

## 4) Navbar (exemplo de componente)

Crie um componente simples de navbar. Ele:

* carrega o catálogo **no `App`**,
* recebe `catalog` e `userRoles`,
* filtra categorias **visíveis**,
* **preserva a ordem** do catálogo (ou usa `sortByOrder` se desejado).

```tsx
// apps/host/src/components/Navbar.tsx (exemplo sugerido)
import React from "react";
import { NavLink } from "react-router-dom";
import type { Catalog } from "../types";
import { visibleCategories } from "../lib/catalog";

type Props = { catalog: Catalog; userRoles?: string[] };

export default function Navbar({ catalog, userRoles }: Props) {
  const cats = visibleCategories(catalog, userRoles); // ordem do catálogo preservada
  return (
    <nav className="navbar">
      <ul className="nav-list">
        {cats.map((c) => (
          <li key={c.id} className="nav-item">
            <NavLink to={`/category/${c.id}`} className={({ isActive }) => (isActive ? "active" : "")}>
              {c.icon ? <span className={`icon ${c.icon}`} aria-hidden /> : null}
              <span>{c.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
```

Estilos mínimos (opcional):

```css
/* apps/host/src/index.css (exemplo) */
.navbar { display: flex; gap: 12px; padding: 8px 12px; border-bottom: 1px solid #e5e7eb; }
.nav-list { display: flex; gap: 8px; list-style: none; margin: 0; padding: 0; }
.nav-item a { padding: 6px 10px; border-radius: 8px; text-decoration: none; }
.nav-item a.active { background: #eef2ff; }
```

---

## 5) Integração no App (roteamento + sessão)

```tsx
// apps/host/src/App.tsx (trechos)
import React, { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthProvider";
import Navbar from "./components/Navbar";
import { loadCatalog } from "./lib/catalog";
import type { Catalog } from "./types";

import HomeDashboard from "./pages/HomeDashboard";
import CategoryView from "./pages/CategoryView";
import NotFound from "./pages/NotFound";

function Shell() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const { user } = useAuth();

  useEffect(() => {
    loadCatalog().then(setCatalog).catch(console.error);
  }, []);

  if (!catalog) return <div>Carregando catálogo…</div>;

  return (
    <>
      <Navbar catalog={catalog} userRoles={user?.roles} />
      <Routes>
        <Route path="/" element={<HomeDashboard catalog={catalog} />} />
        <Route path="/category/:id" element={<CategoryView catalog={catalog} userRoles={user?.roles} />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </AuthProvider>
  );
}
```

---

## 6) CategoryView: filtragem por categoria e blocos

```tsx
// apps/host/src/pages/CategoryView.tsx (trecho ilustrativo)
import React from "react";
import { useParams } from "react-router-dom";
import type { Catalog, CatalogBlock } from "../types";
import { anyRoleAllowed } from "../lib/catalog";

export default function CategoryView({ catalog, userRoles }: { catalog: Catalog; userRoles?: string[] }) {
  const { id } = useParams<{ id: string }>();
  const blocks = catalog.blocks.filter((b) => b.categoryId === id && !b.hidden);

  // RBAC ANY-of por bloco
  const visible = blocks.filter((b) => anyRoleAllowed(userRoles, b.requiredRoles));

  // Ordem: por padrão, a do array; opcional: usar 'order' se existir
  // const ordered = sortByOrder(visible);

  if (visible.length === 0) return <div>Nenhum bloco visível nesta categoria.</div>;

  return (
    <div className="grid">
      {visible.map((b: CatalogBlock) => (
        <div key={`${b.categoryId}-${b.ui?.['url'] ?? b.ui?.['href']}`} className="card">
          {b.ui?.['type'] === "iframe" ? (
            <iframe title={b.ui['url']} src={b.ui['url']} style={{ width: "100%", height: 600, border: 0 }} />
          ) : b.ui?.['type'] === "link" ? (
            <a href={b.ui['href']} target="_blank" rel="noreferrer">Abrir</a>
          ) : null}
        </div>
      ))}
    </div>
  );
}
```

---

## 7) cURLs e verificações

```bash
# Catálogo direto no BFF
curl -s http://localhost:8000/catalog/dev | jq .

# Via proxy do Host
curl -s http://localhost:5173/catalog/dev | jq .

# Confirmação de sessão (para RBAC)
curl -s -i http://localhost:5173/api/me
```

---

## 8) Problemas comuns

* **Categoria aparece vazia**
  Todos os blocos podem estar ocultos por RBAC. Verifique `requiredRoles` e as `roles` do usuário.

* **Ordem “pulando”**
  Se estiver usando `sortByOrder`, itens sem `order` vão para o fim. Para **preservar a ordem do catálogo**, não aplique o sort.

* **Iframe não renderiza**
  O alvo pode bloquear `X-Frame-Options`. Use alternativa (link) ou ajuste a origem no serviço alvo (quando possível).

* **Catálogo 404**
  Verifique proxies do Vite e se o BFF está ativo. Teste as URLs na seção **cURLs**.

---

## Próximos passos

* **[Estrutura src/, pages/, components/](./estrutura-src-pages-components)**
* **[Proxies do Vite (/api, /catalog, /docs)](/docs/03-build-run-deploy/proxies-do-vite-api-catalog-docs)**
* **Testes de navegação/ACL** (Vitest/RTL) para garantir RBAC e ordem correta.

---

> _Criado em 2025-11-18_