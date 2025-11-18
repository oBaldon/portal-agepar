---
id: rbac-simples-requiredroles-any-of
title: "RBAC simples (requiredRoles ANY-of)"
sidebar_position: 4
---

Este documento descreve o **RBAC simples** do Host (React/Vite/TS), baseado no campo `requiredRoles` do **catálogo**. A regra é **ANY-of**: se o usuário possuir **qualquer** uma das roles exigidas, o item fica visível/acessível.

> Referências:  
> `apps/host/src/types.ts`, `apps/host/src/lib/catalog.ts`, `apps/host/src/auth/AuthProvider.tsx`,  
> `apps/host/src/pages/CategoryView.tsx`, `apps/host/src/App.tsx`

---

## 1) Conceito

- **Bloco** pode declarar `requiredRoles?: string[]`.  
- **Categoria** aparece na navbar **se tiver ao menos 1 bloco visível** ao usuário.  
- **Sem `requiredRoles`** (ou array vazio) ⇒ **público**.  
- **Regra ANY-of** ⇒ basta **uma** role coincidir.

```mermaid
flowchart LR
  U[Usuario roles] --> R[RBAC ANY-of]
  R -->|filtra| B[Blocos visiveis]
  B --> N[Navbar por categorias]
  R --> P[Paginas protegidas]
````

---

## 2) Tipos (resumo)

```ts
// apps/host/src/types.ts (trechos relevantes)
export type Role = string;

export type CatalogBlock = {
  categoryId: string;
  ui:
    | { type: "iframe"; url: string }
    | { type: "link"; href: string };
  requiredRoles?: Role[]; // regra: ANY-of
  order?: number;
  hidden?: boolean;
};

export type CatalogCategory = {
  id: string;
  label: string;
  icon?: string;
  order?: number;
  hidden?: boolean;
};
```

---

## 3) Utilitários de RBAC

```ts
// apps/host/src/lib/catalog.ts
export function anyRoleAllowed(userRoles?: string[], required?: string[]) {
  if (!required || required.length === 0) return true;            // público
  if (!userRoles || userRoles.length === 0) return false;         // usuário sem roles
  return required.some((r) => userRoles.includes(r));              // ANY-of
}

export function visibleBlocks(
  blocks: { hidden?: boolean; requiredRoles?: string[] }[],
  userRoles?: string[]
) {
  return blocks.filter((b) => !b.hidden && anyRoleAllowed(userRoles, b.requiredRoles));
}
```

---

## 4) Guard de rota / componente

```tsx
// apps/host/src/App.tsx (trecho)
function Guard({ children, required }: { children: React.ReactNode; required?: string[] }) {
  const { user, loading } = useAuth(); // AuthProvider expõe user.roles
  if (loading) return <div>Carregando…</div>;
  return anyRoleAllowed(user?.roles, required) ? <>{children}</> : <Forbidden />;
}

// Exemplo de uso:
<Route
  path="/account/sessions"
  element={
    <Guard required={["editor", "admin"]}>
      <AccountSessions />
    </Guard>
  }
/>
```

---

## 5) Filtro por categoria (navbar)

```ts
// apps/host/src/lib/catalog.ts (exemplo)
import type { Catalog } from "../types";

export function visibleCategories(cat: Catalog, userRoles?: string[]) {
  const visMap = new Set<string>();
  for (const b of visibleBlocks(cat.blocks, userRoles)) {
    visMap.add(b.categoryId);
  }
  // preserva a ordem original do catálogo
  return cat.categories.filter((c) => !c.hidden && visMap.has(c.id));
}
```

---

## 6) Exemplo de catálogo

```json
{
  "categories": [
    { "id": "compras", "label": "Compras" },
    { "id": "contratos", "label": "Contratos" }
  ],
  "blocks": [
    {
      "categoryId": "compras",
      "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" },
      "requiredRoles": ["editor", "admin"]
    },
    {
      "categoryId": "contratos",
      "ui": { "type": "iframe", "url": "/api/automations/contrato/ui" }
      // sem requiredRoles => público
    }
  ]
}
```

---

## 7) Sessão e origem das roles

O Host obtém o usuário/roles via **`/api/me`**.

```ts
// apps/host/src/auth/AuthProvider.tsx (trecho)
type User = { id: string; name: string; roles: string[] } | null;

useEffect(() => {
  api<User>("/api/me")
    .then(setUser)
    .catch(() => setUser(null))
    .finally(() => setLoading(false));
}, []);
```

### cURLs úteis

```bash
# Quem sou (roles)
curl -s http://localhost:5173/api/me

# Login mock (se habilitado no BFF)
curl -s -X POST http://localhost:5173/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret"}' -i
```

> Observação: login mock pode estar desabilitado por padrão. Use apenas se habilitado no BFF.

---

## 8) Testes (Vitest) do utilitário

```ts
// apps/host/src/lib/catalog.spec.ts
import { describe, it, expect } from "vitest";
import { anyRoleAllowed } from "./catalog";

describe("anyRoleAllowed", () => {
  it("permite quando não há requiredRoles", () => {
    expect(anyRoleAllowed([], undefined)).toBe(true);
    expect(anyRoleAllowed([], [])).toBe(true);
  });
  it("nega quando usuário não tem roles", () => {
    expect(anyRoleAllowed(undefined, ["editor"])).toBe(false);
  });
  it("ANY-of: permite com pelo menos 1 coincidência", () => {
    expect(anyRoleAllowed(["viewer", "editor"], ["admin", "editor"])).toBe(true);
    expect(anyRoleAllowed(["viewer"], ["admin", "editor"])).toBe(false);
  });
});
```

---

## 9) Problemas comuns

* **Tudo oculto**: verifique se `user.roles` está chegando; teste com `/api/me`.
* **Navbar vazia**: pode haver categorias sem **blocos visíveis**; revise `requiredRoles` e `hidden`.
* **Rota protegida redirecionando para Forbidden**: a página/rota está sob `<Guard required=[...]>` e o usuário não possui nenhuma das roles exigidas.
* **Ambiente dev sem sessão**: CORS/credentials precisam estar corretos entre Host e BFF.

---

## 10) Boas práticas

* **Mantenha `requiredRoles` o mais simples possível** (curto e coerente com o BFF).
* **Evite negar por padrão** em itens públicos (deixe `requiredRoles` ausente ou vazio).
* **Teste com usuários de perfis distintos** (ex.: `viewer`, `editor`, `admin`) para garantir a UX correta.

---

## Próximos passos

* **[Navbar por categorias e leitura do catálogo](./navbar-por-categorias-e-leitura-do-catálogo)**
* **[Renderização de blocos (iframe ui.url)](./renderização-de-blocos-iframe-uiurl)**

---

> _Criado em 2025-11-18_