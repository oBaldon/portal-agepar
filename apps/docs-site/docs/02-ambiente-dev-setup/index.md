---
id: index
title: "Ambiente Dev — Setup"
sidebar_position: 0
---

_Criado em 2025-10-27 13:37:46_

Esta seção cobre **pré-requisitos**, **subida com Docker Compose**, **proxies do Vite**, variáveis de ambiente (incl. `DATABASE_URL` do Postgres) e **troubleshooting** para o ambiente de desenvolvimento.

## Pré-requisitos

- Docker 24+ e Docker Compose 2+
- Git
- (Opcional) Node.js 18+ (para rodar o Host localmente)
- (Opcional) Python 3.11+ (para rodar o BFF localmente)

## Serviços e portas (dev)

- **host (Vite/React)** → `5173`  
  Proxies para **`/api`**, **`/catalog`** e **`/docs`**.
- **bff (FastAPI)** → `8000`  
  Endpoints de catálogo e automations; usa **Postgres** via `DATABASE_URL`.
- **db (Postgres)** → `5432` (Compose)

> No Compose padrão: `DATABASE_URL=postgresql://agepar:agepar@db:5432/agepar`.

## Subir tudo com Docker

```bash
docker compose up --build
````

> O primeiro build pode demorar por causa de cache de imagens e dependências.

## Proxies do Vite (Host)

* `/api` e `/catalog` → `http://localhost:8000`
* `/docs` → `http://localhost:8000` (via host)
* Em Compose, se o Host estiver no container `host`, inclua ambas as origens no BFF:
  `CORS_ORIGINS=http://localhost:5173,http://host:5173`

## cURLs úteis

```bash
# Documentação OpenAPI (confirma BFF no ar)
curl -i http://localhost:8000/api/docs

# Catálogo consumido pelo Host
curl -s http://localhost:8000/catalog/dev | jq .

# Ping de integração exposto no BFF
curl -s http://localhost:8000/api/eprotocolo/ping
```

> Observação: endpoints de **login mock** podem estar desativados por padrão (controle por `AUTH_MODE`/`AUTH_LEGACY_MOCK`). Use apenas se habilitados.

## Troubleshooting

* **Mermaid em MDX**: evite `[]` no título do `subgraph` e chaves `{}` em rótulos; prefira `:kind` ou escape HTML.
* **CORS/Sessão**: alinhe `CORS_ORIGINS` no BFF (inclua `http://localhost:5173` **e** `http://host:5173` em Compose). Cookies precisam de `allow_credentials=True`.
* **Banco de dados**: confirme `DATABASE_URL` válido para Postgres; o BFF não sobe sem ele.

---

*Esta seção será detalhada com base nos artefatos do repositório principal.*

_Criado em 2025-10-27 13:37:46_