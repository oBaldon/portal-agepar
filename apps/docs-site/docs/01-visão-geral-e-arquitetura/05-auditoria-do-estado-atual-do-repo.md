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

### Docs
- `baseUrl: "/devdocs/"`
- sidebar principal em `sidebars.ts`
- mix atual de `package-lock.json` e `pnpm-lock.yaml`

## Passivos documentados

- `.env.example` ainda contém variáveis sensíveis que não deveriam estar versionadas;
- `docker-compose.dev.yml` e `run_dev.sh` comunicam sinais diferentes sobre `AUTH_MODE`;
- o Host embute iframes sem `sandbox`;
- o repositório ainda não possui suíte automatizada consolidada para BFF e Host.

## Como usar esta página

Use esta auditoria como referência rápida quando houver dúvida entre:
- documentação histórica,
- comportamento realmente implementado,
- ou débito técnico explicitamente conhecido.
