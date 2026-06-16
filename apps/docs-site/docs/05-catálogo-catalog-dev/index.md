---
id: "catalogo-catalog-dev"
title: "Catálogo (/catalog/dev)"
sidebar_position: 0
---

Esta seção documenta o **catálogo JSON** servido em **`/catalog/dev`**, que descreve **categorias** e **blocos** do Portal AGEPAR.  
É a partir desse arquivo que o **Host (React/Vite/TS)** monta a navbar, aplica **RBAC** e decide **o que** e **como** mostrar para o usuário.

## Objetivos
- Descrever a estrutura geral do catálogo (`generatedAt`, `host`, `categories[]`, `blocks[]`).
- Explicar o **esquema de bloco** (`{ name, categoryId, ui, navigation, routes, ... }`) e como ele é interpretado pelo Host e pelo BFF.
- Documentar as **convenções de uso** de `icon`, `order`, `hidden`, `tags`, `requiredRoles` e outros campos opcionais.
- Apresentar **exemplos práticos** para adicionar/alterar blocos, criar categorias e evoluir o catálogo de forma segura (PRs pequenos, feature flags simples).
- Deixar claro que **campos extras são tolerados** (forward-compat) e que a **ordem do arquivo é preservada** por padrão.

## Sumário Rápido
- `01-estrutura-json-categories-blocks` — visão geral do JSON (`generatedAt`, `host`, `categories`, `blocks`) e responsabilidades de cada parte.
- `02-esquema-de-bloco-categoryid-ui-navigation-routes` — definição formal de um bloco, com exemplos de mínimo x completo.
- `03-convenções-icon-order-hidden` — boas práticas para ícones, ordenação e uso de `hidden` como feature flag simples.
- `04-exemplos-e-práticas-de-extensão` — passo a passo para criar novos blocos e evoluir o catálogo com segurança.

## Visão geral do catálogo

O arquivo **realmente versionado neste snapshot** é `catalog/catalog.dev.json`.

Ele é composto, em alto nível, por:

- `generatedAt` — timestamp de geração do catálogo.
- `host` — metadados do frontend:
  - `version` — versão esperada do Host.
  - `minBlockEngine` — versão mínima suportada dos blocos.
- `categories[]` — lista de categorias que aparecem na navbar:
  - `id`, `label`, `icon`, `hidden`, `requiredRoles`, `order` (opcional).
- `blocks[]` — blocos (automações, ferramentas, links) associados a categorias:
  - `name`, `displayName`, `version`, `categoryId`;
  - `ui` (ex.: `{ type: "iframe", url: "/api/automations/..." }`);
  - `navigation[]` (como aparece no Host);
  - `routes[]` (paths reais, usados na navegação);
  - `tags`, `requiredRoles`, `hidden`, `order` e outros campos opcionais.

O BFF expõe esse JSON em **`/catalog/dev`** e o Host o consome para:

- desenhar a árvore de navegação;
- esconder/mostrar categorias e blocos de acordo com **RBAC**;
- configurar rotas e iframes para cada automação.

## Sobre variações por ambiente

A documentação ainda discute estratégias como `catalog.base.json`, overlays e schema
formal, porque elas continuam sendo úteis como **padrão de evolução**.

Mas é importante registrar o estado atual corretamente:

- **há um arquivo versionado e ativo**: `catalog/catalog.dev.json`;
- variantes como `catalog.hml.json`, `catalog.prod.json` ou um schema formal
  dedicado **não fazem parte deste snapshot**.
