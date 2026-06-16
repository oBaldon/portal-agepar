---
id: "ambiente-dev-setup"
title: "Ambiente Dev — Setup"
sidebar_position: 0
---

Esta seção descreve o setup que realmente sobe a stack hoje.

## Resumo rápido

- há **dois** arquivos de compose;
- o recomendado é usar `infra/scripts/dev.sh`;
- as docs são servidas em **`/devdocs/`**;
- o banco é **PostgreSQL**;
- `.env.example` está sanitizado, mas continua sendo apenas base de laboratório.

## Serviços esperados

- `host` → `5173`
- `bff` → `8000`
- `docs` → `8000` interno, `9000` direto
- `postgres` → `5432`
