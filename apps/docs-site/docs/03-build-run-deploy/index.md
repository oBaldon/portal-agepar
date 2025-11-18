---
id: index
title: "Build, Run & Deploy"
sidebar_position: 0
---

Esta seção cobre **modos de execução** (Compose e execução direta), **builds de produção** (Host e Docs estáticos; BFF em container), **proxies do Vite** e um **checklist de deploy** com cURLs de verificação.

## Pré-requisitos

- Docker 24+ e Docker Compose 2+
- Git
- Node.js 20+ (build do Host e das Docs)
- Python 3.11+ (execução local do BFF, se fora de containers)
- Acesso a um container registry (para publicar imagem do BFF em prod)

## Modos de execução

- **Desenvolvimento (Compose)** — Host (Vite/React), BFF (FastAPI) e Docs (Docusaurus) sob `docker compose up --build`.
- **Execução direta** — Host via `npm run dev`, BFF via `uvicorn`, Docs via `npm run start`.
- **Produção (build + deploy)** — Host e Docs servidos como **estáticos**; BFF empacotado em **container** atrás de um reverse proxy/TLS.

## Serviços e portas (resumo)

- **host (Vite/React)** → `5173`  
  Proxies para **`/api`**, **`/catalog`** e **`/docs`**.
- **bff (FastAPI)** → `8000`  
  Endpoints de catálogo/automations; requer **Postgres** via `DATABASE_URL`.
- **db (Postgres)** → `5432` (Compose)
- **docs (Docusaurus)** → servido via Host em **`/docs`** (dev) e como estático em prod.

> `DATABASE_URL` típico em Compose: `postgresql://agepar:agepar@db:5432/agepar`.

## Builds & artefatos

- **Host**: `npm ci && npm run build` → `apps/host/dist/`
- **Docs**: `npm ci && npm run build` → `apps/docs-site/build/`
- **BFF**: imagem Docker (ex.: `ghcr.io/<org>/portal-agepar-bff:<tag>`)

## cURLs úteis

```bash
# BFF OpenAPI (confirma BFF no ar)
curl -i http://localhost:8000/api/docs

# Catálogo direto do BFF
curl -s http://localhost:8000/catalog/dev | jq .

# Proxies via Host (dev)
curl -i http://localhost:5173/api/docs
curl -s http://localhost:5173/catalog/dev | jq .
curl -i http://localhost:5173/docs
````

## Troubleshooting

* **/docs retorna 404** → verifique se as Docs estão ativas no dev ou publicadas como estático no prod; ajuste o proxy/rewrite.
* **SPA do Host quebra em refresh** → configure `try_files` (NGINX/Apache) ou `fallback` para a rota base.
* **CORS/Sessão** → alinhe `CORS_ORIGINS` no BFF (`http://localhost:5173` e `http://host:5173` em Compose).
* **BFF não inicia** → valide `DATABASE_URL` e se o Postgres está saudável.

---

> _Criado em 2025-11-18_

