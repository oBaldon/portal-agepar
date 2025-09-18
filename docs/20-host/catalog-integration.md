# Integração com o Catálogo (Host)

Este documento explica como o **Host (React + Vite + TS)** consome o **catálogo** exposto pelo BFF para montar **navbar**, **cards por categoria** e **rotas**.

---

## 🎯 Objetivos

- Carregar o catálogo de **desenvolvimento** ou **produção** (`/catalog/dev` ou `/catalog/prod`).
- Montar **UI dinâmica** (navbar + cards) a partir de `categories[]` e `blocks[]`.
- Respeitar **RBAC** no cliente antes de exibir itens.
- Preservar **ordem de escrita** (ou `order` quando definido).
- Tratar **erros, fallback e cache** de forma previsível.
- Endurecer **segurança** quando renderizando iframes do BFF.

---

## 📦 Tipos (TS)

```ts
// apps/host/src/types/catalog.ts
export type CatalogCategory = { id: string; label: string; icon?: string; order?: number };
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
export type Catalog = { categories: CatalogCategory[]; blocks: CatalogBlock[] };
````

---

## 🔌 Fetch do Catálogo

```ts
// apps/host/src/services/catalog.ts
export async function fetchCatalog(env: "dev" | "prod" = "dev") {
  const res = await fetch(`/catalog/${env}`, { credentials: "include" });
  if (!res.ok) throw new Error(`Catalog fetch failed: ${res.status}`);
  return (await res.json()) as import("../types/catalog").Catalog;
}

/** Estratégia com fallback: tenta prod → cai para dev se falhar */
export async function fetchCatalogWithFallback() {
  try {
    return await fetchCatalog("prod");
  } catch {
    return await fetchCatalog("dev");
  }
}
```

> A escolha de `dev`/`prod` pode vir de `import.meta.env.MODE` ou de uma flag no `.env`.

---

## 🧊 Cache (SWR simples)

```ts
// apps/host/src/hooks/useCatalog.ts
import { useEffect, useState } from "react";
import type { Catalog } from "../types/catalog";
import { fetchCatalogWithFallback } from "../services/catalog";

export function useCatalog() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  async function reload() {
    setLoading(true);
    setError(null);
    try {
      const cached = sessionStorage.getItem("catalog");
      if (cached) setCatalog(JSON.parse(cached));
      const fresh = await fetchCatalogWithFallback();
      setCatalog(fresh);
      sessionStorage.setItem("catalog", JSON.stringify(fresh));
    } catch (err: any) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { reload(); }, []);
  return { catalog, loading, error, reload };
}
```

---

## 👤 RBAC no Cliente

```ts
// apps/host/src/utils/rbac.ts
import type { CatalogBlock } from "../types/catalog";
export type User = { id: string; username: string; roles?: string[] };

export function userCanSeeBlock(user: User | null, block: CatalogBlock) {
  const req = block.requiredRoles;
  if (!req?.length) return true;
  const roles = user?.roles ?? [];
  return req.some((r) => roles.includes(r));
}
```

> Mesmo com o filtro no front, o **BFF reforça** RBAC (defesa em profundidade).

---

## 🧭 Montagem da Navbar (categorias)

* A navbar lista **categorias** em ordem:

  1. `order` crescente (se existir), senão
  2. **ordem de escrita** no JSON.
* Cada item de categoria mostra **blocos visíveis** (filtrados por RBAC e `hidden !== true`).

```tsx
// apps/host/src/components/Navbar.tsx
import { Link } from "react-router-dom";
import type { Catalog } from "../types/catalog";
import { userCanSeeBlock, User } from "../utils/rbac";

export default function Navbar({ catalog, user }: { catalog: Catalog; user: User | null }) {
  const orderedCats = [...catalog.categories].sort(
    (a, b) => (a.order ?? Number.MAX_SAFE_INTEGER) - (b.order ?? Number.MAX_SAFE_INTEGER)
  );
  const blocksByCat = (catId: string) =>
    catalog.blocks
      .filter((b) => b.categoryId === catId && !b.hidden && userCanSeeBlock(user, b))
      .sort((a, b) => (a.order ?? 999) - (b.order ?? 999));

  return (
    <nav className="border-b bg-white/70 backdrop-blur sticky top-0 z-50">
      <ul className="flex gap-4 px-4 h-14 items-center">
        {orderedCats.map((cat) => (
          <li key={cat.id} className="group relative">
            <span className="font-medium">{cat.label}</span>
            <div className="absolute top-full left-0 hidden group-hover:block bg-white shadow-xl rounded-xl p-2 min-w-64">
              {blocksByCat(cat.id).map((b) => (
                <Link key={b.id} to={b.routes[0]} className="block px-3 py-2 rounded-lg hover:bg-gray-50" title={b.description}>
                  {b.label}
                </Link>
              ))}
              {blocksByCat(cat.id).length === 0 && (
                <div className="px-3 py-2 text-sm text-gray-500">Sem itens</div>
              )}
            </div>
          </li>
        ))}
      </ul>
    </nav>
  );
}
```

---

## 🧱 Cards por Categoria (Home)

```tsx
// apps/host/src/pages/Home.tsx
import type { Catalog } from "../types/catalog";
import { userCanSeeBlock, User } from "../utils/rbac";
import { Link } from "react-router-dom";

export default function Home({ catalog, user }: { catalog: Catalog; user: User | null }) {
  const orderedCats = [...catalog.categories].sort(
    (a, b) => (a.order ?? Number.MAX_SAFE_INTEGER) - (b.order ?? Number.MAX_SAFE_INTEGER)
  );

  return (
    <div className="p-6 space-y-10">
      {orderedCats.map((cat) => {
        const blocks = catalog.blocks
          .filter((b) => b.categoryId === cat.id && !b.hidden && userCanSeeBlock(user, b))
          .sort((a, b) => (a.order ?? 999) - (b.order ?? 999));
        if (!blocks.length) return null;

        return (
          <section key={cat.id}>
            <h2 className="text-xl font-semibold mb-4">{cat.label}</h2>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {blocks.map((b) => (
                <Link to={b.routes[0]} key={b.id} className="rounded-2xl border shadow-sm p-4 hover:shadow-md transition">
                  <div className="text-lg font-medium">{b.label}</div>
                  {b.description && <p className="text-sm text-gray-600 mt-1 line-clamp-2">{b.description}</p>}
                </Link>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
```

---

## 🧵 Breadcrumbs do Catálogo

Cada bloco pode definir `navigation[]`. O Layout resolve a trilha pela **rota ativa**:

```ts
// apps/host/src/utils/breadcrumbs.ts
import type { Catalog } from "../types/catalog";

export function getBreadcrumbs(catalog: Catalog, pathname: string) {
  const block = catalog.blocks.find(b => b.routes.includes(pathname));
  if (!block) return [];
  return block.navigation ?? [{ path: pathname, label: block.label }];
}
```

Renderizar no Layout:

```tsx
// apps/host/src/pages/Layout.tsx (trecho)
import { useLocation, Outlet } from "react-router-dom";
import { getBreadcrumbs } from "../utils/breadcrumbs";
export default function Layout({ catalog, user }: any) {
  const { pathname } = useLocation();
  const crumbs = catalog ? getBreadcrumbs(catalog, pathname) : [];
  return (
    <div>
      {/* Navbar aqui */}
      <div className="px-6 py-3 text-sm text-gray-600">
        {crumbs.map((c, i) => (
          <span key={i}>
            {i > 0 && " / "}
            <a href={c.path} className="hover:underline">{c.label}</a>
          </span>
        ))}
      </div>
      <Outlet />
    </div>
  );
}
```

---

## 🔐 Segurança de Iframe (CSP & sandbox)

Endureça o uso de iframes (mesmo sendo do BFF) para reduzir superfície:

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
        // restringe capacidades do iframe
        sandbox="allow-forms allow-scripts allow-same-origin"
        referrerPolicy="no-referrer"
      />
    </div>
  );
}
```

> Configure **CSP** no host (ex.: `Content-Security-Policy: frame-src 'self'; child-src 'self';`), ajustando se o BFF estiver em outro domínio.

---

## 🔄 Comunicação Host ↔ Iframe (postMessage)

Para futuras UIs mais ricas:

```ts
// apps/host/src/utils/bridge.ts
export function sendToIframe(iframe: HTMLIFrameElement, type: string, payload: any) {
  iframe.contentWindow?.postMessage({ type, payload }, "*"); // ajuste targetOrigin em prod
}
window.addEventListener("message", (e) => {
  if (!e.data?.type) return;
  // trate eventos vindos da automação: ex. "automation:ready", "download:success"
});
```

> Em produção, **nunca** use `*` em `targetOrigin` — informe a origem exata do BFF.

---

## 🧯 Erros & Estados

* **Falha no fetch**: exibir mensagem técnica + botão **Tentar novamente** (`reload()`).
* **Catálogo vazio**: placeholder “Nenhum bloco disponível”.
* **RBAC**: blocos ocultos no front; back reforça com `403` em endpoints sensíveis.
* **Hidden**: `hidden: true` → não aparece em navbar/cards/rotas.

```tsx
// apps/host/src/pages/AppShell.tsx (exemplo)
const { catalog, loading, error, reload } = useCatalog();
if (loading) return <div className="p-6">Carregando catálogo...</div>;
if (error) return <div className="p-6">Falha ao carregar catálogo. <button onClick={reload}>Tentar novamente</button></div>;
if (!catalog) return <div className="p-6">Catálogo indisponível.</div>;
```

---

## ♿ Acessibilidade

* Links de navbar com `title` e texto claro.
* Foco visível em itens navegáveis.
* `aria-current="page"` para rota ativa (opcional).
* Contraste mínimo em textos dos cards.

---

## 🧪 Testes (Vitest/RTL)

* **Carregamento**: skeleton/spinner até fetch resolver.
* **RBAC**: rotas/cards ocultos para usuários sem role.
* **Ordem**: `order` e ordem de escrita preservados.
* **Fallback**: simular erro em `/catalog/prod` → cair para `/catalog/dev`.
* **Iframe**: `sandbox` presente e `src` correto.

```tsx
import { render, screen } from "@testing-library/react";
import Home from "../src/pages/Home";

test("exibe cards de blocos visíveis", () => {
  const catalog: any = {
    categories: [{ id: "c1", label: "Compras" }],
    blocks: [{ id: "b1", label: "DFD", categoryId: "c1", ui: { type: "iframe", url: "/a" }, routes: ["/dfd"] }],
  };
  render(<Home catalog={catalog} user={{ id: "u", username: "x", roles: [] }} />);
  expect(screen.getByText("DFD")).toBeInTheDocument();
});
```

---

## 🔮 Futuro

* **Busca global** de blocos (com destaque por categoria).
* **Favoritos recentes** por usuário (localStorage).
* **Telemetria de UX** (cliques, erros de iframe).
* Suporte a **ui.type !== "iframe"** (componentes nativos do Host).
* **Invalidação** do cache quando `/api/version` mudar.

---

📖 Relacionado:

* [Roteamento e Rotas](roteamento-e-rotas.md)
* [RBAC no Front](rbac-no-front.md)
* [Vite – Proxies](vite-config-proxies.md)


