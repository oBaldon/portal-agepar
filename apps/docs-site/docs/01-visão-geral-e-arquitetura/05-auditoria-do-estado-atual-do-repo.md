---
id: auditoria-estado-atual-do-repositorio
title: "Auditoria do estado atual do repositório"
sidebar_position: 5
---

Esta página consolida o que o código realmente implementa hoje e os principais
passivos observáveis sem depender de premissas antigas.

## Stack real do monorepo

- **BFF**: FastAPI em `apps/bff`
- **Host**: React 18 + Vite 6 + TypeScript em `apps/host`
- **Docs**: Docusaurus v3 em `apps/docs-site`
- **Banco**: PostgreSQL em dev
- **Orquestração**: `infra/docker-compose.dev.yml` + `infra/docker-compose.pg.yml`

## Contratos observados no código

### Host
- proxy de `/api` e `/catalog` para `http://bff:8000`
- proxy de `/devdocs` para `http://docs:8000`
- catálogo em `catalog/catalog.dev.json`
- blocos iframe renderizados pelo Host com regras de RBAC de vitrine

### BFF
- `APP = FastAPI(..., docs_url="/api/docs", redoc_url="/api/redoc")`
- `init_db()` roda no startup
- autenticação local com sessão persistida em banco
- `AUTH_LEGACY_MOCK=1` mantém o atalho legado de mock
- módulos ativos para DFD, ETP, férias, tarefas, fileshare, suporte, avisos, usuários e outros

### Banco
- `infra/sql/init_db.sql` inicializa o domínio base de auth/RBAC/auditoria/RH
- `apps/bff/app/db.py` garante tabelas operacionais como `submissions`,
  `automation_audits`, `notifications`, `tasks` e `fileshare_items`

## Principais passivos ainda observáveis

- quickstart alternativo fora de `infra/scripts/dev.sh` ainda é fácil de errar,
  porque o BFF depende do compose com Postgres;
- o Host continua embutindo módulos em `iframe` sem `sandbox`;
- o repositório continua sem suíte de testes automatizados versionada;
- coexistem `package-lock.json` e `pnpm-lock.yaml` no projeto `apps/docs-site`;
- ainda existem nomes históricos em alguns arquivos da documentação.

## O que mudou em relação à revisão anterior

- `.env.example` deste snapshot está **sanitizado**, com placeholders vazios para
  integrações externas;
- a principal divergência restante na doc não é mais segredo versionado, mas sim
  trechos históricos e páginas novas que precisavam voltar ao padrão editorial.

## Leitura relacionada

- `../../dev-guide`
- `../../02-ambiente-dev-setup`
- `../../08-banco-de-dados-persistência`
- `../../14-guias-de-produto-fluxo-compras-público`
