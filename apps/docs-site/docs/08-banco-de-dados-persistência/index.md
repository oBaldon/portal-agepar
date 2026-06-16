---
id: "banco-de-dados-persistencia"
title: "Banco de Dados & Persistência"
sidebar_position: 0
---

O repositório atual usa **PostgreSQL** no runtime de desenvolvimento e já não é
mais compatível com a narrativa antiga de SQLite.

## O que esta seção cobre

- `init_db()` do BFF
- `infra/sql/init_db.sql`
- tabelas operacionais
- tabela de sessão e identidade
- limites e passivos de backup/migração
