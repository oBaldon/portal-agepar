# Host (Frontend) – Visão Geral

O **Host** é a aplicação **frontend** do Portal AGEPAR, construída com **React + Vite + TypeScript**.  
Ele consome o **catálogo** para montar a navegação e renderiza as automações via **iframes** integrados ao BFF.

---

## 🎯 Objetivos

- Fornecer uma **interface única** para acesso às automações.  
- Renderizar blocos dinamicamente conforme catálogo.  
- Garantir **segurança no acesso** via RBAC.  
- Integrar documentação técnica (`/docs`) e backend (`/api`).  
- Oferecer UI responsiva e consistente com padrões modernos.  

---

## 📦 Stack Tecnológica

- **Framework:** React 18 + Vite  
- **Linguagem:** TypeScript  
- **UI Kit:** [ShadCN/UI](https://ui.shadcn.com/) + [TailwindCSS](https://tailwindcss.com/)  
- **Proxies Vite:**  
  - `/api` → BFF (FastAPI, porta 8000)  
  - `/catalog` → BFF (FastAPI, porta 8000)  
  - `/docs` → MkDocs (porta 8000, container docs)  

---

## 📂 Estrutura do Código

```

apps/host/
├── src/
│   ├── components/     # componentes reutilizáveis
│   ├── hooks/          # hooks customizados
│   ├── pages/          # páginas principais
│   ├── routes/         # definição de rotas
│   ├── services/       # comunicação com /api e /catalog
│   ├── types/          # tipos globais (TS)
│   └── App.tsx         # ponto de entrada principal
├── public/             # assets estáticos
└── vite.config.ts      # configuração do Vite

````

---

## 📊 Fluxo de Funcionamento

```mermaid
flowchart TD
    U[Usuário] --> H[Host (React + Vite)]
    H --> C[/catalog/*]
    H --> A[/api/*]
    H --> D[/docs/*]

    C --> H: JSON com categorias e blocos
    H --> IF[Iframes]
    IF --> A
````

1. O **Host** carrega o catálogo (`/catalog/dev` ou `/catalog/prod`).
2. Monta a **navbar com categorias** e os **blocos disponíveis**.
3. Cada bloco com `ui.type=iframe` é renderizado via `<iframe src={block.ui.url} />`.
4. O usuário navega e interage com a automação no iframe.

---

## 🔑 RBAC (Role-Based Access Control)

* O frontend usa o helper `userCanSeeBlock(user, block)`:

  * Se `requiredRoles` existir, o usuário precisa ter **pelo menos uma role**.
  * Se não houver `requiredRoles`, o bloco é público.

* Blocos ocultos não aparecem na UI, mas o backend reforça restrições (defesa em profundidade).

---

## 🎨 UI/UX

* Layout baseado em **navbar por categorias**.
* **Cards** exibem os blocos dentro de cada categoria.
* **Iframe isolado** garante que falhas de uma automação não afetem o Host.
* Responsividade garantida por Tailwind + Grid.

---

## 🚀 Futuro

* Implementar **dark mode** global.
* Adicionar **busca por blocos** na navbar.
* Cache de catálogo em **localStorage** para melhorar tempo de carregamento.
* Logs de UI (ex.: cliques, erros de iframe).

---

📖 Próximo: [Estrutura de Rotas](roteamento-e-rotas.md)

