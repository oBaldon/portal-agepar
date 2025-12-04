---
id: index
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

O arquivo `catalog/catalog.dev.json` é composto, em alto nível, por:

- `generatedAt` — timestamp de geração do catálogo.
- `host` — metadados do frontend:
  - `version` — versão esperada do Host.
  - `minBlockEngine` — versão mínima suportada dos blocos.
- `categories[]` — lista de categorias que aparecem na navbar:
  - `id`, `label`, `icon`, `hidden`, `requiredRoles`, `order` (opcional).
- `blocks[]` — blocos (automations, ferramentas, links) associados a categorias:
  - `name`, `displayName`, `version`, `categoryId`;
  - `ui` (ex.: `{ type: "iframe", url: "/api/automations/..." }`);
  - `navigation[]` (links lógicos internos);
  - `routes[]` (paths reais, usados na navegação);
  - `tags`, `requiredRoles`, `hidden`, `order` e outros campos opcionais.

O BFF expõe esse JSON em **`/catalog/dev`** e o Host o consome para:

- desenhar a árvore de navegação;
- esconder/mostrar categorias e blocos de acordo com **RBAC**;
- configurar rotas e iframes para cada automação.

## Campos principais (categories e blocks)

### `categories[]`

Cada categoria representa um grupo lógico de blocos:

- `id` — identificador estável (usado nos blocos via `categoryId`).
- `label` — texto exibido na navbar.
- `icon` — ícone lógico (ex.: `ShoppingCart`, `CalendarDays`).
- `hidden` — se `true`, oculta a categoria na UI, mesmo que tenha blocos.
- `requiredRoles[]` — lista de roles necessárias para ver a categoria (regra **ANY-of**).
- `order` — quando presente, permite sobrescrever a ordem natural do arquivo.

### `blocks[]`

Cada bloco descreve uma automação ou ferramenta:

- `name` — slug técnico (usado para logs, correlacionar com BFF).
- `displayName` — nome exibido na UI.
- `version` — versão do bloco/automação.
- `categoryId` — id da categoria a que pertence.
- `ui` — como o bloco é renderizado (ex.: `type: "iframe"`, `url` para o BFF).
- `navigation[]` — “roteiro” lógico apresentado dentro da categoria.
- `routes[]` — caminhos reais utilizados na navegação do Host.
- `requiredRoles[]` — roles necessárias para ver/acessar o bloco (ANY-of).
- `hidden` — controla se o bloco aparece ou não na lista, mesmo com roles válidas.
- `tags[]`, `order`, campos extras — metadados auxiliares que o Host/BFF podem ou não usar.

## RBAC, visibilidade e ordem

- **RBAC**:
  - Se `requiredRoles` estiver definido em uma categoria ou bloco, a regra é **ANY-of**:
    - basta o usuário ter **uma** das roles para ver o item.
  - Se `requiredRoles` não estiver presente, assume-se “público autenticado” (sem filtro extra).
- **Visibilidade**:
  - `hidden: true` em categoria/bloco **esconde** o item, mesmo que o RBAC seja satisfeito.
  - Útil para:
    - feature flags simples;
    - experimentos em ambientes de dev/homologação;
    - desativar temporariamente items sem removê-los do JSON.
- **Ordem**:
  - Por padrão, o Host preserva a **ordem de escrita** do arquivo.
  - O campo `order`, quando presente, pode ser usado para forçar uma ordenação específica em algumas telas.
  - Recomendação:
    - organizar primeiro pela **ordem natural** no arquivo;
    - só usar `order` quando houver um motivo forte (ex.: obrigatoriedade regulatória, fluxo recomendado).

## Extensão e boas práticas

- Tratar o catálogo como **código versionado**:
  - PRs pequenos e descritivos;
  - commits que mexem em poucos blocos por vez;
  - revisão focada em RBAC, `hidden`, rotas e `ui.url`.
- Separar por ambiente quando necessário:
  - `catalog.dev.json`, `catalog.hml.json`, `catalog.prod.json`, ou
  - overlays específicos aplicados em build/deploy.
- Manter **nomenclatura estável** para `id` de categoria e `name` de bloco:
  - evita quebra em logs, métricas e links salvos.
- Usar `hidden` como feature flag simples:
  - primeiro subir o backend/automação;
  - depois liberar na UI mudando apenas o catálogo.

## Troubleshooting

- **`/catalog/dev` retorna 404 ou 500**
  - Verifique se o BFF está no ar e se o caminho do arquivo `catalog.dev.json` está configurado corretamente (`CATALOG_FILE`).
- **Host mostra “nenhuma categoria” ou “nenhum bloco”**
  - Confirme se o usuário tem as `roles` necessárias e se `hidden` não está ativado de forma indevida.
- **Bloco existe no JSON mas não aparece na UI**
  - Confira `categoryId`, `requiredRoles`, `hidden` e se a categoria correspondente também está visível.
- **Erro de JSON ou catálogo não carrega**
  - Valide o `catalog.dev.json` (chaves, vírgulas, aspas) antes de subir.
- **Ícone não renderiza**
  - Use nomes de ícones compatíveis com o set de ícones usado pelo Host (ex.: `lucide-react`); em caso de dúvida, reaproveite ícones já existentes.

---

> _Criado em 2025-12-04_
