# Página: Home (Dashboard)

A página **Home** do Host é o **painel inicial** após login.  
Ela lista os **blocos disponíveis** agrupados por categoria, aplicando **RBAC** e respeitando a ordem definida no catálogo.

---

## 🎯 Objetivos

- Exibir as categorias (`categories[]`) em ordem (`order` → ordem de escrita).
- Renderizar **cards** para cada bloco visível (`blocks[]`).
- Aplicar **RBAC** com `userCanSeeBlock`.
- Fornecer links de navegação para a primeira rota (`routes[0]`) de cada bloco.
- Ser **responsiva** e **acessível**.

---

## 📐 Layout

- **Título da categoria** (`h2`).
- **Grid de cards** (`md:grid-cols-2`, `lg:grid-cols-3`).
- Cada card contém:
  - Nome (`label`)
  - Descrição (`description`, opcional)
  - Link (`routes[0]`)

---

## 🔧 Implementação (TSX)

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
                <Link
                  to={b.routes[0]}
                  key={b.id}
                  className="rounded-2xl border shadow-sm p-4 hover:shadow-md transition"
                >
                  <div className="text-lg font-medium">{b.label}</div>
                  {b.description && (
                    <p className="text-sm text-gray-600 mt-1 line-clamp-2">{b.description}</p>
                  )}
                </Link>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
````

---

## ♿ Acessibilidade

* **Contraste** suficiente nos textos (`text-gray-600` ≥ AA).
* Foco visível nos cards (`hover:shadow-md` + `focus:outline`).
* Cards têm **texto descritivo** (não apenas ícones).

---

## 🧪 Testes (Vitest + RTL)

* Renderiza categorias em ordem (`order` ou escrita).
* Filtra blocos com `hidden: true`.
* RBAC: blocos só aparecem se `userCanSeeBlock(user, block) === true`.
* Links apontam para `routes[0]`.

Exemplo:

```tsx
import { render, screen } from "@testing-library/react";
import Home from "../src/pages/Home";

test("renderiza card visível de bloco", () => {
  const catalog: any = {
    categories: [{ id: "c1", label: "Compras" }],
    blocks: [
      { id: "b1", label: "DFD", categoryId: "c1", ui: { type: "iframe", url: "/dfd" }, routes: ["/dfd"] },
    ],
  };
  render(<Home catalog={catalog} user={{ id: "u", username: "x", roles: [] }} />);
  expect(screen.getByText("DFD")).toBeInTheDocument();
});
```

---

## 🔮 Futuro

* **Busca rápida** de blocos diretamente na Home.
* **Favoritos/recentes** do usuário.
* **Cards ricos** com ícones e status (última execução, pendências).