---
id: monorepo-estrutura-de-pastas
title: "Monorepo: estrutura de pastas"
sidebar_position: 3
---

## Árvore de alto nível

```text
apps/
  bff/
    app/
      auth/
      automations/
      games/
      utils/
      main.py
      db.py
    Dockerfile.dev
    run_dev.sh

  host/
    src/
      auth/
      components/
      lib/
      pages/
      App.tsx
      types.ts
    vite.config.ts

  docs-site/
    docs/
    blog/
    src/
    static/
    docusaurus.config.ts
    sidebars.ts

catalog/
  catalog.dev.json

infra/
  docker-compose.dev.yml
  docker-compose.pg.yml
  scripts/dev.sh
  sql/init_db.sql
```

## Papel de cada raiz

### `apps/bff`
Backend de fronteira:
- auth
- catálogo
- automações
- auditoria
- notificações
- tarefas
- integração de sessão com Postgres

### `apps/host`
Frontend principal:
- login e rotas protegidas
- dashboard e categorias
- chamadas ao BFF
- regras de visibilidade de catálogo
- renderização iframe

### `apps/docs-site`
Documentação técnica em Docusaurus:
- `docs/`
- `blog/`
- `sidebars.ts`
- `docusaurus.config.ts`

### `catalog`
Metadados dos blocos visíveis no Host.

### `infra`
Compose, scripts operacionais e SQL consolidado de bootstrap.

## Observações arquiteturais úteis

- o repositório usa **Docusaurus**, não MkDocs;
- a documentação de dev é publicada em **`/devdocs/`** no estado atual;
- o banco de dev é **PostgreSQL**, não SQLite;
- a composição completa depende de dois arquivos YAML.
