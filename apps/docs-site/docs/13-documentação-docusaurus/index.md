---
id: index
title: "Documentação (Docusaurus)"
sidebar_position: 0
---

Esta seção documenta o **portal de documentação de dev** do Portal AGEPAR, 
baseado em **Docusaurus** e localizado em `apps/docs-site/`.  
Aqui entram: estrutura de `docs/` (MD/MDX), `sidebars.ts`, `docusaurus.config.ts`,
padrões de snippets, diagramas (Mermaid), assets e estratégias de **build & deploy**.

## Objetivos
- Descrever a estrutura do projeto de docs em `apps/docs-site/`:
  - pastas `docs/`, `static/`, `src/`,
  - arquivos principais (`docusaurus.config.ts`, `sidebars.ts`, `package.json`).
- Explicar como a **organização por seções (1–12)** é refletida em:
  - pastas `NN-*` dentro de `docs/`,
  - `_category_.json` e `index.md` de cada seção.
- Definir os padrões de **snippets**:
  - cURL (BFF),
  - TypeScript/TSX (Host),
  - Python (scripts/integrações),
  - uso de `title`, `showLineNumbers` e MDX (Tabs/TabItem).
- Documentar o uso de **diagramas (Mermaid)** e **assets estáticos**:
  - onde colocar imagens (`static/img`),
  - como referenciar em MD/MDX,
  - boas práticas para diagramas claros e fáceis de manter.
- Descrever o fluxo de **build & deploy da doc**:
  - execução local (`npm start`/`npm run build`),
  - publicação via **proxy do Host** (`/docs` ou `/devdocs`),
  - ou como **site dedicado** (subdomínio próprio).

## Sumário Rápido
- `01-estrutura-docs-mdx-sidebars-e-docusaurusconfig` — visão de `apps/docs-site/`, organização de `docs/`, `sidebars.ts` e `docusaurus.config.ts`.
- `02-organização-por-seções-112` — mapeamento das seções 01–12 e como elas formam um “livro” sobre o portal.
- `03-snippets-curl-ts-tsx-python` — guia de estilo para exemplos de código (cURL, TS/TSX, Python, JSON, diff).
- `04-diagramas-mermaid-e-assets` — como usar Mermaid e organizar assets em `static/img`.
- `05-build-deploy-da-doc-docs-via-proxy-ou-site-dedicado` — opções de publicação das docs (proxy do Host ou site dedicado).

## Visão geral do projeto de docs

O projeto de documentação fica em `apps/docs-site/` e é responsável por:

- expor a **doc de dev** em um site Docusaurus,
- organizar o conteúdo em seções numeradas (01 a 12),
- servir como referência oficial para:
  - arquitetura,
  - ambiente de dev,
  - BFF, Host, automations,
  - banco, segurança, observabilidade, erros & DX, testes.

Componentes principais:

- `apps/docs-site/docs/` — conteúdo em `.md` e `.mdx`.
- `apps/docs-site/static/` — assets estáticos (imagens, favicons, social cards).
- `apps/docs-site/docusaurus.config.ts` — configuração global (title, baseUrl, tema, plugins).
- `apps/docs-site/sidebars.ts` — definição da navegação lateral, baseada nas pastas `docs/`.

## Organização por seções (1–12)

Cada seção segue o padrão:

- pasta `NN-nome-da-seção/` dentro de `docs/`,
- arquivo `index.md` com:
  - frontmatter (`id`, `title`, `sidebar_position`),
  - contexto da seção (Objetivos, Sumário Rápido, Troubleshooting, data),
- arquivos numerados (`01-*`, `02-*`, …) para tópicos específicos,
- opcionalmente, um `99-referencias.mdx` com links para arquivos do repositório.

A seção 13 (esta) explica **como manter e evoluir** essa estrutura.

## Snippets (cURL, TS/TSX, Python)

Os exemplos de código:

- seguem as orientações de estilo em  
  `apps/docs-site/docs/15-apêndices/estilo-de-codigo.mdx`;
- usam blocos de código com linguagem correta:
  - `bash`/`sh` para cURL,
  - `ts`/`tsx` para Host,
  - `python` para scripts,
  - `json`, `diff` quando fizer sentido;
- adotam:
  - `title="..."` com caminho/descrição útil,
  - `showLineNumbers` em blocos mais longos,
  - separação clara entre **comando** e **saída** (sem misturar tudo no mesmo bloco);
- para exemplos multi-linguagem, preferem `.mdx` com Tabs/TabItem.

## Diagramas (Mermaid) e assets

- Diagramas usam **Mermaid** com blocos ` ```mermaid`:
  - `flowchart`, `sequenceDiagram` e outros tipos suportados.
- Padrões:
  - labels curtos e claros (`"Host (React/Vite)"`, `"BFF (FastAPI)"`),
  - evitar `\n` dentro de labels (problemas de parsing),
  - diagramas devem **ajudar** o entendimento (não apenas decorar a página).

Assets estáticos:

- vivem em `apps/docs-site/static/img/` (nomes em `kebab-case`);
- são referenciados como `/img/nome-do-arquivo.ext` nas páginas;
- alterações em favicon, logo ou social card precisam ser refletidas em `docusaurus.config.ts`.

## Build & deploy da documentação

A doc pode ser executada de duas formas principais:

- **Ambiente de desenvolvimento**
  - via Docker Compose (`infra/docker-compose.dev.yml`),
  - ou rodando `npm install` + `npm start` em `apps/docs-site/`.
- **Build & deploy**
  - `npm run build` gera artefatos estáticos (`build/`),
  - publicação:
    - via proxy do Host (ex.: `/docs` ou `/devdocs`),
    - ou em um host dedicado (subdomínio, outro servidor).

A seção de build & deploy descreve:

- as variáveis de ambiente relevantes,
- como alinhar `baseUrl` do Docusaurus com o proxy do Host,
- checklist de smoke tests após cada publicação.

## Troubleshooting

- **Docs não sobem no ambiente de dev**
  - Verificar container `docs` no `docker-compose.dev.yml` e logs de `apps/docs-site`.
- **Sidebar ou títulos aparecendo fora de ordem**
  - Conferir `sidebar_position`, `_category_.json` e nomenclatura `NN-*` das pastas.
- **Snippets quebrando ou sem highlight**
  - Revisar linguagem do bloco (`bash`, `ts`, `tsx`, `python`, `json`, `diff`) e uso de crases.
- **Diagrama Mermaid não renderiza**
  - Verificar sintaxe (` ```mermaid`), tipo de diagrama (`flowchart`, etc.) e labels (sem `\n`).
- **Rota final das docs está incorreta**
  - Ajustar `baseUrl` em `docusaurus.config.ts` e o proxy configurado no Host (ex.: `/devdocs`).

---

> _Criado em 2025-12-04_
