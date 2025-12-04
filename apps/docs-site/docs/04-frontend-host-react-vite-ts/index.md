---
id: index
title: "Frontend (Host – React/Vite/TS)"
sidebar_position: 0
---

Esta seção documenta o **Host** do Portal AGEPAR — a SPA em **React/Vite/TS** que consome o **catálogo**, aplica **RBAC** e renderiza as automations via **iframe**.

## Objetivos
- Descrever a estrutura de `src/` (páginas, componentes, libs e tipos compartilhados).
- Explicar como o Host lê o **catálogo** (`/catalog/dev`) e monta a **navbar por categorias**.
- Detalhar como os **blocos** são filtrados (RBAC, `hidden`) e renderizados (iframe `ui.url`).
- Documentar as regras de **ordem** de categorias/blocos (ordem de escrita vs. campo `order`).
- Registrar como o **Vite** é configurado (proxies `/api`, `/catalog`, `/docs`, base, build em containers).

## Sumário Rápido
- `01-estrutura-src-pages-components` — visão geral dos arquivos principais e layout da aplicação.
- `02-navbar-por-categorias-e-leitura-do-catálogo` — fluxo catálogo → navbar → `CategoryView`.
- `03-renderização-de-blocos-iframe-uiurl` — como cada bloco vira um iframe isolado.
- `04-rbac-simples-requiredroles-any-of` — regra de visibilidade com `requiredRoles` (ANY-of).
- `05-ordem-de-categorias-blocos` — definição da ordem final de exibição de categorias e blocos.
- `06-vite-config-e-plugins` — configuração do `vite.config.ts`, proxies e dicas de build.

## Visão geral do Host

O `Host` é uma **SPA** em React que:

- autentica o usuário via `AuthProvider` e endpoints `/api/auth/*`;
- carrega o catálogo assim que o usuário está logado;
- exibe categorias e blocos conforme **roles** e metadados do catálogo;
- renderiza cada automação em um **iframe**, isolando o módulo backend.

## Principais arquivos

- `apps/host/src/main.tsx` — bootstrap do React com `BrowserRouter` e `AuthProvider`.
- `apps/host/src/App.tsx` — definição das rotas, guards de autenticação e redirecionamentos.
- `apps/host/src/auth/AuthProvider.tsx` — contexto de autenticação e sessão do usuário.
- `apps/host/src/lib/api.ts` — cliente HTTP com tratamento de 401/403 e helpers para `/api`.
- `apps/host/src/lib/catalog.ts` — leitura de `/catalog/dev`, helpers de RBAC e filtros.
- `apps/host/src/pages/*.tsx` — páginas como `HomeDashboard`, `CategoryView`, `Login`, `AccountSessions`.
- `apps/host/src/types.ts` — tipos de catálogo, usuário e helpers de ordenação/RBAC.

## Navegação por categorias e catálogo

- O Host busca o catálogo em `/catalog/dev` **após o login** bem-sucedido.
- A navbar mostra somente **categorias visíveis** (respeitando `hidden` e `requiredRoles`).
- Cada categoria leva à `CategoryView`, que:
  - aplica filtros de **RBAC** (ANY-of) e `hidden`;
  - preserva a **ordem de escrita** do JSON, exceto quando `order` é definido.

## Renderização de blocos

- Cada bloco com `ui.type === "iframe"` é renderizado via `<iframe src={block.ui.url} />`.
- O iframe mantém a automação **isolada**, permitindo que cada módulo evolua de forma independente.
- Há espaço para:
  - responsividade mínima dos iframes;
  - fallback amigável para erros de carregamento;
  - integração opcional via `postMessage` entre Host e automations.

## RBAC simples no frontend

- `requiredRoles` pode aparecer em:
  - categorias do catálogo;
  - blocos individuais.
- A regra é **ANY-of**:
  - se o usuário tiver **qualquer** role de `requiredRoles`, o item fica visível/acessível.
- A ausência de `requiredRoles` significa “público autenticado” (não restringir além do login).

## Vite, proxies e build

- `apps/host/vite.config.ts` define:
  - `base` (quando necessário para deploy em subcaminho);
  - proxies:
    - `/api` e `/catalog` → BFF;
    - `/docs` → Docs (Docusaurus);
  - ajustes úteis para rodar em **Docker** (host/port, HMR).
- Em produção, o Host é buildado e servido por um servidor web que:
  - entrega os estáticos da SPA;
  - encaminha `/api`, `/catalog` e `/docs` para os serviços corretos.

## Troubleshooting

- **Navbar vazia ou categorias faltando**
  - Verifique se `/catalog/dev` está acessível e se o usuário tem as `roles` esperadas.
- **Bloco não aparece**
  - Confirme `hidden`, `requiredRoles` e se o bloco está associado à categoria correta.
- **Iframe não carrega**
  - Teste a URL `ui.url` diretamente no navegador e verifique CORS/autenticação.
- **Erro de CORS ou sessão ao chamar `/api`**
  - Garanta que o BFF está com `CORS_ORIGINS` configurado para o host do frontend.
- **Build em subcaminho quebra assets**
  - Ajuste `base` no `vite.config.ts` e a configuração do servidor web.

---

> _Criado em 2025-12-04_
