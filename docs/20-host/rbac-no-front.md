# RBAC no Frontend (Host)

Este documento explica como o **Host (React + Vite + TS)** implementa **RBAC (Role-Based Access Control)** no frontend.  
O RBAC define **quem pode ver e acessar** cada bloco do catálogo.

---

## 🎯 Objetivos

- Filtrar blocos visíveis de acordo com `requiredRoles`.
- Garantir que o usuário só veja o que pode acessar.
- Aplicar guardas de rota (`RequireRole`) para segurança adicional.
- Manter **defesa em profundidade**: front apenas oculta, back reforça.

---

## 📦 Estrutura de Dados

### Usuário

```ts
export type User = {
  id: string;
  username: string;
  roles?: string[];
};
````

### Bloco do Catálogo

```ts
export type CatalogBlock = {
  id: string;
  label: string;
  categoryId: string;
  requiredRoles?: string[];
  hidden?: boolean;
  // demais campos omitidos...
};
```

---

## 🔑 Helper `userCanSeeBlock`

```ts
// apps/host/src/utils/rbac.ts
import type { CatalogBlock } from "../types/catalog";

export type User = { id: string; username: string; roles?: string[] };

export function userCanSeeBlock(user: User | null, block: CatalogBlock): boolean {
  if (block.hidden) return false;
  if (!block.requiredRoles || block.requiredRoles.length === 0) return true;
  if (!user?.roles?.length) return false;
  return block.requiredRoles.some((r) => user.roles!.includes(r));
}
```

* Se `hidden = true`, bloco nunca é exibido.
* Se `requiredRoles` não existe → público.
* Se existe, usuário precisa ter **pelo menos uma** role.

---

## 🧩 Uso em Navbar e Home

```tsx
const visibleBlocks = catalog.blocks.filter((b) => userCanSeeBlock(user, b));
```

* Navbar só exibe blocos permitidos.
* Home mostra apenas cards visíveis.

---

## 🛣️ Guardas de Rota

Mesmo que o bloco esteja oculto, o usuário pode **forçar URL direta**.
Por isso, usamos `<RequireRole />`:

```tsx
// apps/host/src/components/RequireRole.tsx
import { Navigate, useLocation } from "react-router-dom";
import { userCanSeeBlock, User } from "../utils/rbac";
import { CatalogBlock } from "../types/catalog";

export function RequireRole({
  user,
  block,
  children,
}: {
  user: User | null;
  block: CatalogBlock;
  children: React.ReactNode;
}) {
  const location = useLocation();
  if (!userCanSeeBlock(user, block)) {
    return <Navigate to="/403" replace state={{ from: location }} />;
  }
  return <>{children}</>;
}
```

Exemplo no roteador:

```tsx
<Route
  path={block.routes[0]}
  element={
    <RequireRole user={user} block={block}>
      <IFrameRoute src={block.ui.url} title={block.label} />
    </RequireRole>
  }
/>
```

---

## 🔐 Estratégia de Segurança

* **Frontend:** apenas oculta blocos e protege navegação.
* **Backend (BFF):** sempre reforça:

  * `/api/automations/...` deve validar sessão + roles.
  * `/catalog/prod` só retorna blocos permitidos.
* **Defesa em profundidade**: nunca confiar só no front.

---

## 🧪 Testes

Exemplo em Vitest/RTL:

```tsx
import { render, screen } from "@testing-library/react";
import { userCanSeeBlock } from "../src/utils/rbac";

test("oculta bloco quando usuário não tem role", () => {
  const block: any = { requiredRoles: ["admin"] };
  const user: any = { roles: ["user"] };
  expect(userCanSeeBlock(user, block)).toBe(false);
});

test("permite bloco público", () => {
  const block: any = {};
  const user: any = null;
  expect(userCanSeeBlock(user, block)).toBe(true);
});
```

---

## 🔮 Futuro

* Implementar **atribuição de roles** no backend (/api/auth/login).
* Cache local de roles em sessão frontend.
* Logs de tentativas de acesso negadas no front.
* Customizar página **403** com contato/suporte.

---

📖 Relacionado:

* [Roteamento e Rotas](roteamento-e-rotas.md)
* [Integração com o Catálogo](catalog-integration.md)
