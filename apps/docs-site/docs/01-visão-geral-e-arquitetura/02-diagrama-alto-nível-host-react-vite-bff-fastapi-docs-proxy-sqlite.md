---
id: diagrama-alto-nível-host-react-vite-bff-fastapi-devdocs-postgres
title: "Diagrama alto nível — Host, BFF, Docs e Postgres"
sidebar_position: 2
slug: /01-visão-geral-e-arquitetura/02-diagrama-alto-nível-host-react-vite-bff-fastapi-docs-proxy-sqlite
---

Esta página descreve o estado atual do monorepo:
**Docusaurus + PostgreSQL + `/devdocs/`**.

## Diagrama alto nível

```mermaid
flowchart LR
  Browser[(Browser)]
  subgraph Front["Camada Web"]
    Host["Host React/Vite :5173"]
    Docs["Docs Docusaurus :8000"]
  end
  BFF["FastAPI BFF :8000"]
  PG[(PostgreSQL :5432)]

  Browser --> Host
  Host -->|/api| BFF
  Host -->|/catalog| BFF
  Host -->|/devdocs| Docs
  BFF --> PG
```

## Fluxo principal

1. o navegador acessa o Host em `:5173`;
2. o Host encaminha:
   - `/api` para o BFF;
   - `/catalog` para o BFF;
   - `/devdocs` para o site Docusaurus;
3. o BFF persiste o estado em PostgreSQL.

## Onde isso aparece no repo

- `apps/host/vite.config.ts`
- `apps/bff/app/main.py`
- `apps/bff/app/db.py`
- `infra/docker-compose.dev.yml`
- `infra/docker-compose.pg.yml`
- `apps/docs-site/docusaurus.config.ts`
