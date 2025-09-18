# Página: Category View

A página **Category View** exibe todos os **blocos** de uma **categoria específica**, permitindo ao usuário navegar por uma visão detalhada além da Home.

---

## 🎯 Objetivos

- Receber `categoryId` via rota (ex.: `/categoria/:id`).
- Mostrar informações da categoria (`label`, `icon`, etc.).
- Listar **blocos visíveis** (respeitando RBAC e `hidden`).
- Preservar **ordem de escrita** ou `order`.
- Exibir mensagem clara quando **não houver blocos**.

---

## 📐 Layout

- **Título** da categoria.
- **Grid de cards** para blocos.
- **Mensagem de vazio** quando não houver blocos visíveis.
- Integração com **breadcrumbs** (ex.: `Home / Compras`).

---

## 🔧 Implementação (TSX)

```tsx
// apps/host/src/pages/CategoryView.tsx
import { useParams, Link } from "react-router-dom";
import type { Catalog } from "../types/catalog";
import { userCanSeeBlock, User } from "../utils/rbac";

export default function CategoryView({ catalog, user }: { catalog: Catalog; user: User | null }) {
  const { id } = useParams<{ id: string }>();
  const category = catalog.categories.find((c) => c.id === id);

  if (!category) {
    return <div className="p-6">Categoria não encontrada.</div>;
  }

  const blocks = catalog.blocks
    .filter((b) => b.categoryId === id && !b.hidden && userCanSeeBlock(user, b))
    .sort((a, b) => (a.order ?? 999) - (b.order ?? 999));

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold mb-6">{category.label}</h1>

      {blocks.length === 0 ? (
        <div className="text-gray-600">Nenhum bloco disponível nesta categoria.</div>
      ) : (
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
      )}
    </div>
  );
}
````

---

## 🧵 Breadcrumbs

A navegação deve refletir a localização:

```txt
Home / Compras
```

Implementação baseada em `navigation[]` ou categoria ativa.

---

## ♿ Acessibilidade

* Foco visível nos cards (`hover:shadow-md focus:outline`).
* Texto descritivo para cada link.
* Contraste mínimo em descrições.

---

## 🧪 Testes (Vitest + RTL)

* Categoria inválida → renderiza mensagem “Categoria não encontrada”.
* Categoria válida sem blocos → renderiza “Nenhum bloco disponível”.
* RBAC aplicado: blocos não visíveis para usuários sem roles.
* Links de cards apontam para `routes[0]`.

Exemplo:

```tsx
import { render, screen } from "@testing-library/react";
import CategoryView from "../src/pages/CategoryView";

test("renderiza mensagem quando categoria não encontrada", () => {
  const catalog: any = { categories: [], blocks: [] };
  render(<CategoryView catalog={catalog} user={null} />);
  expect(screen.getByText(/Categoria não encontrada/)).toBeInTheDocument();
});
```

---

## 🔮 Futuro

* Suporte a **filtros de busca** dentro da categoria.
* Exibir **ícones** das categorias/blocos.
* Ordenação customizável pelo usuário.