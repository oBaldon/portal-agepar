---
id: testes-do-host-vitest-se-houver
title: "Testes do Host (Vitest, se houver)"
sidebar_position: 2
---

Hoje o **Host** (`apps/host`) ainda **não possui suíte de testes automatizados** configurada:

- `package.json` não tem script `test`,
- não há dependência `vitest`,
- não existem arquivos `*.test.ts(x)` ou `*.spec.ts(x)` na pasta `src`.

Mesmo assim, o projeto já está organizado de um jeito que facilita muito adicionar
**Vitest + Testing Library** no futuro. Esta página documenta:

- o **estado atual**,
- a **stack recomendada** de testes,
- exemplos práticos de testes em TypeScript,
- e um **checklist** para quando a suíte for implementada.

> Referências no repo:
>
> - `apps/host/package.json`
> - `apps/host/vite.config.ts`
> - `apps/host/src/types.ts`
> - `apps/host/src/App.tsx`
> - `apps/host/src/pages/HomeDashboard.tsx`, `CategoryView.tsx`

---

## 1) Estado atual do Host

Resumo do Host:

- **Vite + React 18 + TypeScript**;
- alias `@` → `apps/host/src` (`vite.config.ts`);
- scripts em `package.json`:

  ```json title="apps/host/package.json (trecho)"
  {
    "scripts": {
      "dev": "vite --host 0.0.0.0 --port 5173",
      "build": "vite build",
      "preview": "vite preview --host 0.0.0.0 --port 5173",
      "typecheck": "tsc --noEmit"
    }
  }
    ```

* **não há**:

  * script `"test"`,
  * config de Vitest em `vite.config.ts`,
  * setup de ambiente de teste.

Ou seja, os testes do Host são hoje:

* **manuais** (clicar, navegar, checar RBAC, proxy, etc.),
* complementados por testes de API do BFF (cURL/pytest) descritos na página anterior.

O objetivo desta página é “deixar pronto o caminho” para quando quisermos:

> `npm test` no Host, com Vitest rodando unitários e testes de componentes.

---

## 2) Stack recomendada de testes para o Host

Quando for o momento de implementar, o padrão sugerido é:

* **Test runner**: [Vitest](https://vitest.dev/) (se integra nativamente com Vite).
* **Ambiente DOM**: `jsdom`.
* **Testes de componentes**: `@testing-library/react`.
* **Asserts extras de DOM**: `@testing-library/jest-dom`.

### 2.1. Dependências dev (sugestão)

No `apps/host/package.json`, adicionar:

```jsonc
"devDependencies": {
  // ... já existentes
  "vitest": "^2.0.0",
  "@testing-library/react": "^16.0.0",
  "@testing-library/jest-dom": "^6.0.0",
  "@testing-library/user-event": "^14.0.0",
  "jsdom": "^26.0.0"
}
```

> Versões são sugestão — ajustar conforme a época em que for implementar.

E scripts:

```jsonc
"scripts": {
  "dev": "vite --host 0.0.0.0 --port 5173",
  "build": "vite build",
  "preview": "vite preview --host 0.0.0.0 --port 5173",
  "typecheck": "tsc --noEmit",
  "test": "vitest",
  "test:watch": "vitest --watch"
}
```

---

## 3) Configuração integrada com Vite (vitest.config)

Em vez de um arquivo separado, dá para configurar Vitest direto no `vite.config.ts`:

```ts title="apps/host/vite.config.ts (com bloco de test sugerido)" showLineNumbers
// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      // ---------- BFF ----------
      "/api":     { target: "http://bff:8000", changeOrigin: true },
      "/catalog": { target: "http://bff:8000", changeOrigin: true },
      "/devdocs": { target: "http://docs:8000", changeOrigin: true },
    },
  },

  // ---------- Testes (Vitest) ----------
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setupTests.ts",
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
```

E um arquivo de setup em `src/test/setupTests.ts`:

```ts title="apps/host/src/test/setupTests.ts" showLineNumbers
import "@testing-library/jest-dom/vitest";

// Aqui dá para configurar:
// - mocks globais,
// - polyfills (ex.: ResizeObserver),
// - helpers comuns de teste.
```

---

## 4) Testes unitários de helpers (ex.: `types.ts`)

O arquivo `src/types.ts` concentra **helpers puros** ideais para testes unitários:

* `resolveCategoryForBlock`
* `groupBlocksByCategory`
* `blocksForCategory`
* `visibleBlocks`
* `visibleCategories`
* `userCanSeeBlock`
* `isMockSession`

### 4.1. Exemplo: testando `userCanSeeBlock`

`userCanSeeBlock` controla o RBAC da camada de UI (ANY-of):

```ts title="apps/host/src/types.ts (trecho)" showLineNumbers
export function userCanSeeBlock(
  block: Block,
  user?: User | null,
): boolean {
  const required = (block.requiredRoles ?? []).map((r) => r.trim().toLowerCase());
  if (!required.length) return true;

  if (!user) return false;
  const roles = (user.roles ?? []).map((r) => r.trim().toLowerCase());
  const userRoles = new Set(roles);

  if (user.is_superuser || userRoles.has("admin")) return true;

  return required.some((r) => userRoles.has(r.trim().toLowerCase()));
}
```

Teste Vitest correspondente:

```ts title="apps/host/src/types.userCanSeeBlock.test.ts" showLineNumbers
import { describe, it, expect } from "vitest";
import { type Block, type User, userCanSeeBlock } from "@/types";

const baseBlock: Block = {
  name: "exemplo",
  version: "1.0.0",
  ui: { type: "iframe", url: "/api/automations/exemplo/ui" },
};

const baseUser: User = {
  cpf: "00000000000",
  nome: "Usuário Teste",
  roles: [],
};

describe("userCanSeeBlock", () => {
  it("permite acesso quando o bloco não exige roles", () => {
    const block: Block = { ...baseBlock, requiredRoles: undefined };
    expect(userCanSeeBlock(block, null)).toBe(true);
    expect(userCanSeeBlock(block, { ...baseUser, roles: ["qualquer"] })).toBe(true);
  });

  it("nega acesso para usuário anon quando há roles exigidas", () => {
    const block: Block = { ...baseBlock, requiredRoles: ["compras"] };
    expect(userCanSeeBlock(block, null)).toBe(false);
  });

  it("permite acesso para superuser mesmo sem roles", () => {
    const block: Block = { ...baseBlock, requiredRoles: ["compras"] };
    const user: User = { ...baseUser, is_superuser: true };
    expect(userCanSeeBlock(block, user)).toBe(true);
  });

  it("permite acesso se usuário tiver pelo menos uma role exigida (ANY-of)", () => {
    const block: Block = { ...baseBlock, requiredRoles: ["compras", "financeiro"] };
    const user: User = { ...baseUser, roles: ["rh", "Compras"] }; // case-insensitive
    expect(userCanSeeBlock(block, user)).toBe(true);
  });

  it("permite acesso se usuário for admin", () => {
    const block: Block = { ...baseBlock, requiredRoles: ["compras"] };
    const user: User = { ...baseUser, roles: ["Admin"] };
    expect(userCanSeeBlock(block, user)).toBe(true);
  });

  it("nega acesso se usuário não tiver nenhuma role exigida", () => {
    const block: Block = { ...baseBlock, requiredRoles: ["compras", "juridico"] };
    const user: User = { ...baseUser, roles: ["financeiro"] };
    expect(userCanSeeBlock(block, user)).toBe(false);
  });
});
```

### 4.2. Exemplo: `isMockSession`

```ts title="apps/host/src/types.ts (trecho)" showLineNumbers
export function isMockSession(user: User | null): boolean {
  return !!user && user.auth_mode === "mock";
}
```

Teste:

```ts title="apps/host/src/types.isMockSession.test.ts" showLineNumbers
import { describe, it, expect } from "vitest";
import { type User, isMockSession } from "@/types";

describe("isMockSession", () => {
  it("retorna false para usuário nulo", () => {
    expect(isMockSession(null)).toBe(false);
  });

  it("retorna false quando auth_mode não é mock", () => {
    const user: User = { cpf: "1", nome: "X", roles: [], auth_mode: "ldap" };
    expect(isMockSession(user)).toBe(false);
  });

  it("retorna true quando auth_mode é mock", () => {
    const user: User = { cpf: "1", nome: "X", roles: [], auth_mode: "mock" };
    expect(isMockSession(user)).toBe(true);
  });
});
```

Esses testes já dão bastante confiança na **lógica de RBAC** da UI sem precisar montar componentes React.

---

## 5) Testes de componentes com React Testing Library

Com a stack configurada (`jsdom`, `@testing-library/react`, etc.), podemos testar:

* páginas como `HomeDashboard` e `CategoryView`,
* componentes que leem o catálogo e o usuário,
* comportamento de botões/links conforme RBAC.

### 5.1. Exemplo conceitual: HomeDashboard mostra blocos visíveis

`HomeDashboard` usa helpers de catálogo/usuário:

* `visibleBlocks(catalog, user)`
* `visibleCategories(catalog, user)`

Um teste simplificado poderia:

1. Mockar `useAuth` para fornecer um `User` com roles específicas.
2. Mockar um `CatalogContext` com um catálogo pequeno (2 categorias, alguns blocos).
3. Renderizar `HomeDashboard`.
4. Verificar se:

   * cards de blocos permitidos aparecem,
   * blocos ocultos por RBAC não aparecem.

Pseudo-exemplo (não 100% plug-and-play, mas ilustra o padrão):

```ts title="apps/host/src/pages/HomeDashboard.test.tsx (conceitual)" showLineNumbers
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Catalog, User } from "@/types";
import HomeDashboard from "./HomeDashboard";

// Mock do hook de auth
vi.mock("@/auth/AuthProvider", () => {
  return {
    useAuth: () => ({
      user: {
        cpf: "00000000000",
        nome: "Usuário Compras",
        roles: ["compras"],
      } as User,
    }),
  };
});

// Mock de provider de catálogo (ajustar para o que o projeto realmente usa)
vi.mock("@/lib/useCatalog", () => {
  const catalog: Catalog = {
    categories: [
      { id: "compras", label: "Compras" },
      { id: "financeiro", label: "Financeiro" },
    ],
    blocks: [
      {
        name: "dfd",
        version: "1.0.0",
        categoryId: "compras",
        ui: { type: "iframe", url: "/api/automations/dfd/ui" },
        displayName: "DFD",
        requiredRoles: ["compras"],
      },
      {
        name: "orcamento",
        version: "1.0.0",
        categoryId: "financeiro",
        ui: { type: "iframe", url: "/api/automations/orc/ui" },
        displayName: "Orçamento",
        requiredRoles: ["financeiro"],
      },
    ],
  };

  return {
    useCatalog: () => ({ catalog, loading: false, error: null }),
  };
});

describe("HomeDashboard", () => {
  it("mostra apenas blocos compatíveis com os roles do usuário", () => {
    render(<HomeDashboard />);

    // Deve mostrar o card DFD (role compras)
    expect(screen.getByText("DFD")).toBeInTheDocument();

    // Não deve mostrar o card Orçamento (role financeiro)
    expect(screen.queryByText("Orçamento")).not.toBeInTheDocument();
  });
});
```

> Quando for implementar de fato, ajustar os imports/mocks para bater 100% com a
> estrutura atual (`useCatalog`, providers, etc.).

---

## 6) Como rodar testes do Host (quando existirem)

Com tudo configurado:

```bash title="Rodar testes do Host (futuro)" showLineNumbers
cd apps/host

# instalar deps, incluindo vitest/testing-library
npm install

# rodar todos os testes uma vez
npm test

# rodar em modo watch
npm run test:watch
```

Integrações úteis:

* rodar `npm test` no pipeline CI após `npm run build`,
* combinar com `npm run typecheck` para garantir tipos + testes.

---

## 7) Checklist para implementar Vitest no Host

Quando for o momento de “ligar” a suíte de testes, seguir este checklist:

1. **Infra de testes**

   * [ ] Adicionar `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom` como devDependencies.
   * [ ] Configurar `test` / `test:watch` em `package.json`.
   * [ ] Adicionar bloco `test` em `vite.config.ts` com `environment: "jsdom"` e `setupFiles`.

2. **Setup global**

   * [ ] Criar `src/test/setupTests.ts` com `@testing-library/jest-dom/vitest`.
   * [ ] Adicionar polyfills/mocks globais se necessário.

3. **Testes unitários**

   * [ ] Cobrir helpers puros (`types.ts`: RBAC, categorias, mock session).
   * [ ] Cobrir outras funções de utilidade (`lib/api.ts`, etc.).

4. **Testes de componentes**

   * [ ] Cobrir pelo menos:

     * `HomeDashboard`,
     * `CategoryView`,
     * componentes de layout/erro (`Forbidden`, `NotFound`) se tiver lógica.

5. **Integração com CI**

   * [ ] Adicionar etapa `npm test` (Host) no pipeline de CI, junto com testes de BFF (pytest).
   * [ ] Documentar como rodar os testes localmente (README ou docs).

---

> _Criado em 2025-12-02_