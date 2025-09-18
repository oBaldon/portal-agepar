# Testes – Frontend com Vitest

Este documento descreve a estratégia e exemplos de **testes de frontend** usando **Vitest** e **React Testing Library** no Host (React + Vite).

---

## 🎯 Objetivos

- Garantir que componentes renderizem corretamente com diferentes entradas.  
- Validar regras de **RBAC** no cliente.  
- Confirmar integração com o catálogo (navbar, home, rotas).  
- Automatizar em pipeline CI.  

---

## 🛠️ Configuração

### Instalação

```bash
npm install -D vitest @testing-library/react @testing-library/jest-dom
````

### Configuração em `vite.config.ts`

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/tests/setup.ts",
  },
});
```

### Arquivo `setup.ts`

```ts
import "@testing-library/jest-dom";
```

---

## 📚 Exemplos de Testes

### Navbar respeita RBAC

```tsx
import { render, screen } from "@testing-library/react";
import Navbar from "../components/Navbar";
import type { Catalog } from "../types/catalog";

const catalog: Catalog = {
  categories: [{ id: "c1", label: "Compras" }],
  blocks: [
    { id: "b1", label: "DFD", categoryId: "c1", ui: { type: "iframe", url: "/a" }, routes: ["/dfd"], requiredRoles: ["compras"] },
  ],
};

test("oculta blocos sem permissão", () => {
  render(<Navbar catalog={catalog} user={{ id: "u", username: "x", roles: [] }} />);
  expect(screen.queryByText("DFD")).not.toBeInTheDocument();
});

test("exibe blocos com permissão", () => {
  render(<Navbar catalog={catalog} user={{ id: "u", username: "x", roles: ["compras"] }} />);
  expect(screen.getByText("DFD")).toBeInTheDocument();
});
```

---

### Home lista blocos visíveis

```tsx
import { render, screen } from "@testing-library/react";
import Home from "../pages/Home";
import type { Catalog } from "../types/catalog";

const catalog: Catalog = {
  categories: [{ id: "c1", label: "Gestão" }],
  blocks: [
    { id: "b2", label: "Form2JSON", categoryId: "c1", ui: { type: "iframe", url: "/b" }, routes: ["/f2j"], hidden: false },
  ],
};

test("renderiza card do bloco", () => {
  render(<Home catalog={catalog} user={{ id: "u", username: "test" }} />);
  expect(screen.getByText("Form2JSON")).toBeInTheDocument();
});
```

---

### Componente de Sessão

```tsx
import { render, screen } from "@testing-library/react";
import SessionInfo from "../components/SessionInfo";

test("mostra usuário logado", () => {
  render(<SessionInfo user={{ id: "1", username: "alice" }} />);
  expect(screen.getByText(/alice/)).toBeInTheDocument();
});
```

---

## 📦 Execução

Rodar todos os testes:

```bash
npm run test
```

Rodar com watcher:

```bash
npm run test -- --watch
```

Gerar cobertura:

```bash
npm run test -- --coverage
```

---

## 🔮 Futuro

* Adicionar **mocks de catálogo** para diferentes cenários (roles, hidden, etc.).
* Testes E2E com **Playwright** integrados ao CI.
* Snapshots para validar renderizações estáveis.
