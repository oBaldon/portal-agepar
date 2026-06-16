---
id: startup-do-banco-init_db-postgres
title: "Startup do banco com `init_db()` (Postgres no estado atual)"
sidebar_position: 1
slug: /08-banco-de-dados-persistência/01-sqlite-no-startup-init_db
---

Esta página descreve o estado atual do monorepo:
**PostgreSQL + `init_db()`**.

## Onde fica

- `apps/bff/app/db.py`

## Quando roda

No startup do BFF, em `apps/bff/app/main.py`:
- `init_db()`
- `ensure_user_vacation_columns(...)`

## Tabelas garantidas pelo BFF

- `submissions`
- `automation_audits`
- `fileshare_items`
- `notifications`
- `notification_recipients`
- `platform_alerts`
- `platform_alert_recipients`
- `tasks`
- `task_events`
- `auth_users`
- `auth_sessions`
- `auth_audit_logs`
- `vacation_requests`
- `vacation_balances`
- `vacation_holidays`
- `vacation_attachments`

## Dependência de ambiente

O estado atual depende de `DATABASE_URL` apontando para PostgreSQL. Em dev, isso é
injetado via `infra/docker-compose.pg.yml` ou pelos scripts em `infra/scripts/`.
