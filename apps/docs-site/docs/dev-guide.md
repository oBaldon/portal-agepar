---
id: dev-guide
title: Guia de Dev (setup & run)
sidebar_position: 1
---

_Criado em 2025-10-27_

Este guia descreve o _setup_ local, execução com **Docker Compose**, estrutura do monorepo e _troubleshooting_.

## Pré-requisitos

- Docker 24+ e Docker Compose 2+
- Git
- (Opcional) Node.js 18+ para rodar o host fora de container
- (Opcional) Python 3.11+ para rodar o BFF fora de container

## Subindo tudo com Docker

```bash
docker compose up --build
````

Serviços esperados:

* **host**: [http://localhost:5173](http://localhost:5173)
  Proxy para `/api`, `/catalog` e `/docs`.
* **bff** (FastAPI): [http://localhost:8000](http://localhost:8000)
  Endpoints principais: `POST /api/auth/login`, `GET /api/me`, `/catalog/dev`, `/api/automations/:kind/...`
* **docs** (MkDocs/Material): servido via **host** em `/docs` (com livereload)

> Dica: o primeiro build pode demorar por conta do cache de imagens e dependências.

## Rodando o site de documentação (Docusaurus)

> Dependendo da estrutura, o Docusaurus pode estar dentro do monorepo (`apps/docs-site`) **ou** como projeto isolado (raiz deste pacote de docs).

**Monorepo:**

```bash
cd apps/docs-site
pnpm install   # ou npm/yarn
pnpm start     # abre em http://localhost:3000
```

**Projeto isolado (somente docs):**

```bash
pnpm install   # ou npm/yarn
pnpm start     # abre em http://localhost:3000
```

## Estrutura do repositório

```text
apps/
  bff/              # FastAPI + automations (apps/bff/app/...)
  host/             # Vite/React/TS
  docs/             # MkDocs/Material
  docs-site/        # Docusaurus (este site)
docker-compose*.yml # Orquestração
```

## Estrutura das docs (Docusaurus)

As páginas estão organizadas em `docs/` com **seções numeradas**, cada uma com seu próprio `index.md`:

```
docs/
  01-visão-geral-e-arquitetura/
  02-ambiente-dev-setup/
  03-build-run-deploy/
  04-frontend-host-react-vite-ts/
  05-catálogo-catalog-dev/
  06-bff-fastapi/
  07-automations-padrão-de-módulos/
  08-banco-de-dados-persistência/
  09-segurança/
  10-observabilidade/
  11-padrões-de-erro-dx/
  12-testes/
  13-documentação-docusaurus/
  14-guias-de-produto-fluxo-compras-público/
  15-apêndices/
```

> Cada seção possui um `index.md` e páginas internas (ex.: `01-visão-geral-e-arquitetura/02-diagrama-alto-nível-host-react-vite-bff-fastapi-docs-proxy-sqlite.md`).
> A sidebar do Docusaurus organiza automaticamente essas seções.

## Convenções e Padrões

* **Validação (BFF)**: Pydantic v2 com `ConfigDict(populate_by_name=True, extra="ignore")`
* **Erros**: status claros `400/401/403/404/409/422`
* **Banco**: SQLite inicializado no startup (`init_db`) com `submissions` e `audits`
* **RBAC (Host)**: `requiredRoles` (regra ANY-of) nos blocos do catálogo
* **Catálogo**: servido em `/catalog/dev` e respeita a ordem de escrita

## Rodando cada serviço fora do Docker (opcional)

### BFF (FastAPI)

```bash
cd apps/bff
# criar venv (ex.: python -m venv .venv && source .venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Host (Vite/React/TS)

```bash
cd apps/host
pnpm install  # ou npm/yarn
pnpm dev      # inicia Vite em http://localhost:5173
```

> O Vite deve ter *proxies* configurados para `/api` e `/catalog` → `http://localhost:8000` e `/docs` → `http://localhost:8000` ou `http://docs:8000`, conforme *compose*.

## Testes rápidos (cURL)

```bash
# login mock
curl -i -X POST http://localhost:8000/api/auth/login -d '{"username":"dev","password":"dev"}' -H "Content-Type: application/json"

# me
curl -i http://localhost:8000/api/me

# catálogo
curl -s http://localhost:8000/catalog/dev | jq .

# health
curl -i http://localhost:8000/api/health
```

## Observabilidade

* Logs: nível **INFO** no caminho feliz, **ERROR** com contexto (`request_id`, `user`, `automation`, `submission_id`)
* Auditoria: tabela `audits` registra eventos relevantes
* Submissões: tabela `submissions` guarda `payload`, `status`, `result`, `error`

---

_Criado em 2025-10-27_
