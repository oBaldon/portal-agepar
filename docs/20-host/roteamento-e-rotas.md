# Roteamento e Rotas no Host

Este documento descreve como o **Host (React + Vite + TS)** gera e gerencia **rotas** a partir do **catálogo** exposto pelo BFF e como elas se integram ao React Router.

---

## 🎯 Objetivos

- Derivar rotas **dinamicamente** do catálogo (`/catalog/dev` ou `/catalog/prod`).
- Manter **navbar** e **rotas** sincronizadas com `categories[]` e `blocks[]`.
- Renderizar **iframes** para automações (`ui.type = "iframe"`).
- Aplicar **RBAC** no cliente antes de montar a rota.
- Tratar **404**, **fallbacks de carregamento** e **breadcrumbs**.

---

## 📦 Dependências

- **React Router DOM** (v6+)
- **Axios** ou `fetch` para buscar `/catalog/*`
- **Zustand**/Context para estado global (opcional)
- **TypeScript** para tipagem do catálogo

---

## 🧱 Modelos (Types)

```ts
// apps/host/src/types/catalog.ts
export type CatalogCategory = {
  id: string;
  label: string;
  icon?: string;
  order?: number;
};

export type CatalogBlock = {
  id: string;
  label: string;
  categoryId: string;
  description?: string;
  ui: { type: "iframe"; url: string };
  routes: string[];
  navigation?: { path: string; label: string }[];
  requiredRoles?: string[];
  order?: number;
  hidden?: boolean;
};

export type Catalog = {
  categories: CatalogCategory[];
  blocks: CatalogBlock[];
};
````

---

## 🔌 Aquisição do Catálogo

```ts
// apps/host/src/services/catalog.ts
export async function getCatalog(env: "dev" | "prod" = "dev") {
  const res = await fetch(`/catalog/${env}`, { credentials: "include" });
  if (!res.ok) throw new Error(`Catalog fetch failed: ${res.status}`);
  return (await res.json()) as import("../types/catalog").Catalog;
}
```

---

## 👤 RBAC no Front (helper)

```ts
// apps/host/src/utils/rbac.ts
import { CatalogBlock } from "../types/catalog";

export type User = { id: string; username: string; roles?: string[] };

export function userCanSeeBlock(user: User | null, block: CatalogBlock): boolean {
  if (!block.requiredRoles || block.requiredRoles.length === 0) return true;
  if (!user?.roles?.length) return false;
  return block.requiredRoles.some((r) => user.roles!.includes(r));
}
```

---

## 🧭 Estratégia de Roteamento

1. Carregar catálogo na inicialização do app.
2. Derivar lista de **rotas públicas e protegidas** dos `blocks`.
3. Para `ui.type = "iframe"`, usar `<IFrameRoute />`.
4. Aplicar **guardas de rota** (RBAC) com `<RequireRole />`.
5. Adicionar rotas estáticas (`/login`, `/403`, `/404`).
6. Gerar breadcrumbs a partir de `navigation[]`.

---

## 🧩 Componentes de Suporte

```tsx
// apps/host/src/components/IFrameRoute.tsx
export default function IFrameRoute({ src, title }: { src: string; title?: string }) {
  return (
    <div className="w-full h-full">
      <iframe
        src={src}
        title={title || "Automation"}
        className="w-full h-[calc(100vh-4rem)] border-0"
        loading="eager"
      />
    </div>
  );
}
```

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
  const allowed = userCanSeeBlock(user, block);
  if (!allowed) {
    return <Navigate to="/403" replace state={{ from: location }} />;
  }
  return <>{children}</>;
}
```

---

## 🛣️ Geração Dinâmica de Rotas

```tsx
// apps/host/src/routes/Router.tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import IFrameRoute from "../components/IFrameRoute";
import { RequireRole } from "../components/RequireRole";
import type { Catalog, User } from "../types/catalog";
import Layout from "../pages/Layout";
import NotFound from "../pages/NotFound";
import Forbidden from "../pages/Forbidden";
import Home from "../pages/Home";

export default function Router({ catalog, user }: { catalog: Catalog; user: User | null }) {
  const visibleBlocks = catalog.blocks.filter((b) => !b.hidden);

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout catalog={catalog} user={user} />}>
          <Route index element={<Home catalog={catalog} user={user} />} />

          {visibleBlocks.map((block) =>
            block.routes.map((path) => (
              <Route
                key={path}
                path={path}
                element={
                  block.requiredRoles?.length ? (
                    <RequireRole user={user} block={block}>
                      <IFrameRoute src={block.ui.url} title={block.label} />
                    </RequireRole>
                  ) : (
                    <IFrameRoute src={block.ui.url} title={block.label} />
                  )
                }
              />
            ))
          )}

          <Route path="/403" element={<Forbidden />} />
          <Route path="*" element={<NotFound />} />
        </Route>
        <Route path="/home" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
```

---

## 🧭 Navbar por Categorias

* Derivada de `categories[]` do catálogo.
* Mantém a **ordem de escrita** ou campo `order`.
* Filtra blocos visíveis com `userCanSeeBlock(user, block)`.

---

## 🧵 Breadcrumbs

Cada bloco pode definir `navigation[]`.
O **Layout** resolve o bloco ativo pela rota e gera a trilha de navegação.

---

## 🔐 Estados de Erro

* **403**: rota acessada sem permissão (`<RequireRole />`).
* **404**: rota não encontrada (`*`).
* **Erro no catálogo**: exibir mensagem técnica + botão de retry.
* **Carregamento**: mostrar skeleton/spinner até o catálogo ser carregado.

---

## 🧪 Testes (Vitest/RTL)

* Rota deve renderizar `<iframe>` com `src` correto.
* RBAC: rota negada quando `requiredRoles` não é atendido.
* Blocos `hidden: true` não aparecem.
* Ordem respeita `order` ou ordem de escrita.
* Rotas 403/404 renderizam as páginas corretas.

---

## 🚀 Futuro

* Code splitting por categoria (lazy load de rotas).
* Guarda global de autenticação (`user == null` → `/login`).
* Cache de catálogo com **stale-while-revalidate**.
* Rotas parametrizadas (`/contratos/:id`).
* Deep linking entre host e automação via **postMessage**.

---