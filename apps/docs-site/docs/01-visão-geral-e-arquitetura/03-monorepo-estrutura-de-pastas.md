---
id: monorepo-estrutura-de-pastas
title: "Monorepo: estrutura de pastas"
sidebar_position: 3
---

Esta página descreve a **estrutura do monorepo** do Portal AGEPAR, destacando as pastas principais e arquivos‑chave que suportam Host, BFF, Docs e Catálogo.

## Árvore (2 níveis)

```text
/
  README.md
  docusaurus-outline-mapeado.json
  docusaurus-timeline.json
  requirements.txt
apps/
apps/bff/
      Dockerfile.dev
      requirements.txt
      run_dev.sh
apps/docs-site/
      README.md
      docusaurus.config.ts
      package-lock.json
      package.json
      pnpm-lock.yaml
      sidebars.ts
      tsconfig.json
      typedoc.json
apps/host/
      index.html
      package-lock.json
      package.json
      postcss.config.js
      tsconfig.json
      vite.config.ts
catalog/
    catalog.dev.json
infra/
    docker-compose.dev.yml
    docker-compose.pg.yml
infra/scripts/
      db_smoke.sh
      dev_down.sh
      dev_fresh.sh
      dev_logs.sh
      dev_logs_purge.sh
      dev_up.sh
infra/sql/
      001_init_auth_logs.sql
      002_seed_auth_dev.sql
      099_test_auth_logs.sql
```

> A árvore acima é intencionalmente curta (até **2 níveis**) para manter a leitura objetiva.

## Pastas principais (função)

- **apps/bff/** — API **FastAPI** e módulos de **Automations**. Espera‑se `app/`, `routers/`, `automations/`, `init_db` e requisitos Python.
- **apps/host/** — **Vite/React/TS** do frontend. Lê o **Catálogo** e renderiza blocos (iframe) + RBAC.
- **apps/docs/** — **MkDocs/Material** para não‑devs, servido via **host** em `/docs`.
- **apps/docs-site/** — **Docusaurus** (este site técnico), com `docs/` em seções numeradas e sidebar autogerada.
- **catalog/** (se presente) — JSONs com `categories[]` e `blocks[]` para o Host.
- **docker-compose*.yml** — orquestração local (subir host/bff/docs, volumes, portas).

## Arquivos‑chave detectados

- Compose: —
- Vite config: ['apps/host/vite.config.ts']
- mkdocs.yml: —
- pyproject.toml: —
- package.json: ['apps/docs-site/package.json', 'apps/host/package.json']

## Boas práticas de organização

- **Automations como módulos isolados** (BFF + UI no‑build), seguindo a convenção de endpoints (`/schema`, `/ui`, `/submit`, ...).
- **Catálogo versionado** por ambiente (dev/hml/prod) e **ordem preservada** de categorias/blocos.
- **Proxies Vite** configurados para `/api`, `/catalog` e `/docs` apontando para os serviços no docker compose.
- **Logs/Auditoria**: tabelas `submissions` e `audits` + `request_id/user/automation/submission_id` nos logs.
- **Validação**: **Pydantic v2** (`populate_by_name=True`, `extra="ignore"`) para evitar `422` triviais.

## Exemplos rápidos

**Subir serviços (dev):**
```bash
docker compose up --build
```

**Conferir catálogo:**
```bash
curl -s http://localhost:8000/catalog/dev | jq .
```

---

> _Criado em 2025-10-27 12:39:04_