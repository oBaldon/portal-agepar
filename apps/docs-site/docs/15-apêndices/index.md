---
id: index
title: "Apêndices"
sidebar_position: 0
---

Esta seção reúne os **apêndices técnicos** do Portal AGEPAR — material de apoio que
não se encaixa em um único componente (BFF, Host, catálogo), mas que é essencial para
trabalhar bem no projeto:

- tipos TS e modelos Pydantic,
- esquema formal do catálogo em JSON Schema,
- convenções de commit/branch/versionamento,
- roadmap e backlog técnico,
- guia de estilo de código e playgrounds React/TSX.

## Objetivos
- Descrever como **Tipos TS e modelos Pydantic** se alinham para manter um contrato
  JSON estável entre Host (React/TS) e BFF (FastAPI/Pydantic).
- Documentar o **esquema formal do catálogo** em **JSON Schema**, servindo de fonte de
  verdade para tooling, validação e evolução do `catalog.dev`.
- Consolidar as **convenções de commit/branch/versionamento** usadas no monorepo:
  - Conventional Commits,
  - fluxo de branches,
  - *semver* por serviço.
- Registrar o **roadmap e backlog técnico**, ajudando a organizar prioridades de
  produto, plataforma e qualidade.
- Agrupar guias utilitários:
  - **Guia de estilo de código** para snippets (cURL, TS/TSX, Python),
  - **Playground React/TSX** com exemplos interativos em Docusaurus.

## Sumário Rápido
- `01-tipos-ts-e-modelos-pydantic`  
  como Host e BFF representam os mesmos conceitos com tipos diferentes, mantendo um
  contrato JSON consistente.
- `02-esquema-formal-do-catálogo-json-schema`  
  JSON Schema do catálogo (`host`, `categories[]`, `blocks[]`) e dicas para manter
  o schema em sincronia com o código.
- `03-convenções-de-commit-branch-versionamento`  
  regras de commits (Conventional Commits), branches e versionamento (*semver*).
- `04-roadmap-e-backlog-técnico`  
  visão de roadmap técnico e backlog organizado (produto, plataforma, qualidade).
- `estilo-de-codigo.mdx`  
  guia de estilo para exemplos de código (linguagens, títulos, line numbers, tabs).
- `playground-react.mdx`  
  exemplos de playground ao vivo em React/TSX com `live` codeblocks.
- `99-referencias.mdx`  
  mapa dos arquivos do repositório relacionados a esta seção.

## Visão geral dos apêndices

Os apêndices funcionam como um **“cinto de utilidades”** para quem trabalha no
Portal AGEPAR:

- Não descrevem um único componente (como o BFF ou o Host),
- mas **costuram** conceitos entre as seções:
  - Tipos (TS/Pydantic) ↔ Catálogo ↔ Convenções ↔ Roadmap.

Sempre que surgir uma dúvida do tipo:

- “Como tipar isso em TS para bater com o modelo Pydantic?”
- “Onde está o schema oficial do catálogo?”
- “Qual o padrão de commit/branch mesmo?”
- “O que é prioritário no roadmap técnico?”
- “Como escrever snippets bonitos e copiáveis na doc?”

…a resposta provavelmente está aqui.

## Conteúdos principais

### Tipos TS e modelos Pydantic

Na página **“Tipos TS e modelos Pydantic”** você encontra:

- o espelho entre:
  - `User` e outros tipos TS do Host,
  - modelos Pydantic de auth/automations no BFF;
- exemplos de como usar:
  - `alias`, `Field` e `ConfigDict` para alinhar nomes de campos;
  - tipos literais/union em TS para refletir enums do backend.

Essa página é a referência para evitar **divergência silenciosa** entre front e back.

### Esquema formal do Catálogo (JSON Schema)

Na página de **JSON Schema do catálogo**:

- o objeto raiz (`host`, `categories[]`, `blocks[]`) é descrito em detalhes;
- são apresentados:
  - tipos, campos obrigatórios/opcionais,
  - enums e restrições básicas;
- há recomendações para:
  - gerar documentação,
  - validar arquivos de catálogo em pipelines,
  - manter o schema atualizado sempre que o catálogo evoluir.

### Convenções de commit/branch/versionamento

A página de **convenções** padroniza:

- tipos de commit (feat, fix, docs, chore, refactor, etc.);
- formato `type(scope): descrição` com exemplos reais do monorepo;
- fluxo de branches:
  - `main` como linha principal,
  - branches curtas de feature/fix;
- versionamento:
  - *semver* por serviço (BFF, Host, Docs),
  - monorepo em modo **rolling**.

Ela inclui um **checklist rápido** para revisar antes de abrir PR.

### Roadmap e backlog técnico

O **roadmap técnico** organiza prioridades em três grandes eixos:

- **Produto** (fluxo de compras público + automações paralelas),
- **Plataforma** (BFF, Host, catálogo, docs),
- **Qualidade & Operação** (testes, observabilidade, segurança, DX).

A página sugere como:

- transformar esse roadmap em **épicos/issues**,
- evitar que o backlog vire uma lista solta sem contexto.

### Estilo de código & Playground React

Por fim, dois utilitários:

- **Guia de Estilo — Exemplos de Código**
  - define como criar snippets de:
    - cURL (`bash`/`sh`),
    - TS/TSX (`ts`, `tsx`),
    - Python (`python`),
    - JSON/diff;
  - recomenda uso de:
    - `title="..."`,
    - `showLineNumbers`,
    - Tabs/TabItem em `.mdx`,
    - exemplos copiáveis.

- **Playground React/TSX**
  - mostra como usar ` ```tsx live` com o tema `@docusaurus/theme-live-codeblock`;
  - exemplos com:
    - componente simples (`ButtonDemo`),
    - `noInline` + `render(<Counter />)` para exemplos mais elaborados.

## Quando consultar esta seção

Use os Apêndices quando você estiver:

- definindo **novos tipos** no Host ou novos **modelos Pydantic** no BFF;
- evoluindo o **catálogo** e querendo garantir que o JSON Schema acompanhe;
- organizando um **ciclo de desenvolvimento** (branching, commits, releases);
- planejando **próximos passos** (roadmap) com produto/gestão;
- escrevendo **nova documentação** com exemplos de código e quer seguir o padrão.

## Troubleshooting

- **Tipos TS e modelos Pydantic não batem (erro de runtime ou 422 inesperado)**  
  - Revise a página de **“Tipos TS e modelos Pydantic”**  
    e alinhe nomes de campos, enums e formatos (datas, números).

- **Catálogo com campos novos, mas JSON Schema desatualizado**  
  - Atualize a página de **Esquema formal do Catálogo (JSON Schema)**  
    junto com a mudança em `catalog.dev.json`.

- **Commits e branches fora do padrão em PRs recentes**  
  - Reforce o uso da página de **Convenções de commit/branch/versionamento**  
    e use o checklist antes de abrir novos PRs.

- **Backlog técnico confuso ou desalinhado com produto**  
  - Use a página de **Roadmap e backlog técnico** como referência para reorganizar
    issues/épicos.

- **Snippets quebrados ou inconsistentes na doc**  
  - Consulte o **Guia de Estilo — Exemplos de Código**  
    e ajuste linguagem, títulos, `showLineNumbers` e estrutura MDX.

---

> _Criado em 2025-12-04_
