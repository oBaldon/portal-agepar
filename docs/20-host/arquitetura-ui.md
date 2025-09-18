# Arquitetura de UI do Host

Este documento descreve a arquitetura de **UI** do Host (React + Vite + TS), incluindo **layout**, **componentes-base**, **tema**, **responsividade**, **acessibilidade**, padrão de **estado**, integração com **iframes** e diretrizes de **performance** e **segurança**.

---

## 🎯 Princípios

- **Simplicidade primeiro**: layout limpo, foco no conteúdo (automações).
- **Isolamento**: automações sempre em **iframe** (defesa em profundidade).
- **Consistência**: design system com **Tailwind** + **ShadCN/UI**.
- **Escalabilidade**: componentes desacoplados, composição via props.
- **A11y**: componentes navegáveis por teclado e leitores de tela.

---

## 🧱 Layout Base

```

Layout
├─ Navbar (top)
├─ Breadcrumbs (opcional)
└─ Content (Outlet)
└─ Iframe route (quando ui.type = "iframe")

````

### `Layout.tsx` (esqueleto)

```tsx
import { Outlet, useLocation } from "react-router-dom";
import Navbar from "../components/Navbar";
import { getBreadcrumbs } from "../utils/breadcrumbs";
import type { Catalog } from "../types/catalog";
import type { User } from "../utils/rbac";

export default function Layout({ catalog, user }: { catalog: Catalog; user: User | null }) {
  const { pathname } = useLocation();
  const crumbs = catalog ? getBreadcrumbs(catalog, pathname) : [];

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <header className="sticky top-0 z-50 bg-white/70 backdrop-blur border-b">
        <div className="max-w-7xl mx-auto px-4">
          <div className="h-14 flex items-center justify-between">
            <div className="font-semibold">Portal AGEPAR</div>
            <Navbar catalog={catalog} user={user} />
          </div>
        </div>
      </header>

      {crumbs.length > 0 && (
        <nav className="max-w-7xl mx-auto w-full px-4 py-2 text-sm text-gray-600">
          {crumbs.map((c, i) => (
            <span key={i}>
              {i > 0 && " / "}
              <a href={c.path} className="hover:underline">{c.label}</a>
            </span>
          ))}
        </nav>
      )}

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-4">
        <Outlet />
      </main>

      <footer className="border-t text-xs text-gray-500 py-3 text-center">
        © {new Date().getFullYear()} AGEPAR — v1
      </footer>
    </div>
  );
}
````

---

## 🎨 Tema e Design System

### Tailwind (tokens principais)

* **Espaçamento**: `2, 3, 4, 6, 10` para ritmar layouts.
* **Cantos**: `rounded-2xl` em cartões e dropdowns.
* **Sombras**: `shadow-sm` default, `hover:shadow-md` em interações.
* **Cores**: cinzas para estrutura; cores de destaque reservadas a ações.

**Exemplo de `tailwind.config.js` (trecho):**

```js
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      borderRadius: { xl: "0.75rem", "2xl": "1rem" },
      maxWidth: { "7xl": "80rem" },
    },
  },
  plugins: [],
};
```

### ShadCN/UI

* Preferir componentes acessíveis (Dialog, Dropdown, Button, Input).
* Estilizar via Tailwind utilities (sem tema complexo inicial).
* Evitar sobreposição de estilos complexos — simplicidade.

**Ex.:**

```tsx
import { Button } from "@/components/ui/button";

<Button className="rounded-2xl">Ação</Button>
```

---

## 📱 Responsividade

* Grid de **cards** na Home: `grid gap-4 md:grid-cols-2 lg:grid-cols-3`.
* Navbar com **dropdown** por categoria (abre ao hover/foco).
* Iframe ocupa **altura da viewport** menos header: `h-[calc(100vh-4rem)]`.

---

## ♿ Acessibilidade (A11y)

* **Foco visível** (`focus:outline-none focus:ring` onde necessário).
* Navbar e dropdowns **navegáveis por teclado** (Tab/Shift+Tab, Esc).
* Texto de links descritivo + `aria-current="page"` quando aplicável.
* Contraste mínimo em textos e ícones.

---

## 🔐 Segurança de UI

* **Iframe** com `sandbox="allow-forms allow-scripts allow-same-origin"` e `referrerPolicy="no-referrer"`.
* **CSP** sugerido (ajustar no servidor):
  `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-src 'self'; connect-src 'self'; img-src 'self' data:`
* Evitar `innerHTML` direto; se precisar, sanitizar.

---

## 🧩 Componentes Base

* `Navbar`: lista categorias, exibe blocos visíveis por RBAC.
* `IFrameRoute`: encapsula sandbox e sizing de iframes.
* `RequireRole`: guarda de rota para blocos com `requiredRoles`.
* `Home`: cards por categoria com descrição.
* `Forbidden`/`NotFound`: páginas padrão de erro.

**IFrameRoute.tsx**

```tsx
export default function IFrameRoute({ src, title }: { src: string; title?: string }) {
  return (
    <div className="w-full h-full">
      <iframe
        src={src}
        title={title || "Automation"}
        className="w-full h-[calc(100vh-4rem)] border-0"
        loading="eager"
        sandbox="allow-forms allow-scripts allow-same-origin"
        referrerPolicy="no-referrer"
      />
    </div>
  );
}
```

---

## 🧠 Estado e Dados

* **Catálogo**: hook `useCatalog` (SWR simples + `sessionStorage`).
* **Usuário**: `useMe()` para `/api/me`, invalidar no login/logout.
* **RBAC**: helper `userCanSeeBlock(user, block)` — filtra UI.

---

## 🔄 Comunicação Host ↔ Automação

* Padrão **`postMessage`** (futuro):

  * `automation:ready`, `automation:download`, `host:notify`, etc.
  * **Nunca** usar `*` em `targetOrigin` em produção.

---

## ⚡ Performance

* Evitar re-renders: memorizar listas derivadas (categorias/blocos ordenados).
* **Code splitting** por páginas/rotas (futuro: categorias).
* Cache leve do catálogo + **fallback prod→dev**.
* Evitar iframes fora da viewport (render apenas quando rota ativa).

---

## 🧪 Testes de UI

* **Snapshot** de Layout + Navbar.
* **RBAC**: render condicional de blocos/rotas.
* **A11y**: foco navegável nos menus; `aria-*` coerentes.
* **Iframe**: `src` e `sandbox` corretos.
* **Erro/Loading**: estados de catálogo.

---

## 🧯 Erros e Mensagens

* Falha no catálogo → mensagem técnica e botão **“Tentar novamente”**.
* Sem permissões → página **403** (link de retorno para Home).
* 404 → link para Home e suporte.

---

## 📦 Organização de Pastas (Host)

```
apps/host/src/
├── components/        # Navbar, IFrameRoute, RequireRole, etc.
├── hooks/             # useCatalog, useMe
├── pages/             # Home, Layout, NotFound, Forbidden, Login
├── routes/            # Router
├── services/          # fetchers /api, /catalog
├── types/             # catalog, user
├── utils/             # rbac, breadcrumbs, bridge (postMessage)
└── App.tsx
```

---

## 🔮 Evolução

* Tema escuro (prefers-color-scheme / toggle).
* Search global de blocos.
* Telemetria de UI (erros de iframe, cliques).
* Suporte a **ui.type != iframe** com componentes nativos.
