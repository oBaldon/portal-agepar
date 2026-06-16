---
id: sqlite-no-startup-init_db
title: "Startup do banco com `init_db()` (Postgres no estado atual)"
sidebar_position: 1
---

> O nome do arquivo é histórico. O conteúdo abaixo descreve o estado atual:
> **PostgreSQL + `init_db()`**.

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
- `task_comments`

## Implicação prática

O BFF hoje depende de `DATABASE_URL` já no import-time de `db.py`. Portanto, a
stack não representa mais um cenário em que o backend sobe “sem banco” e cria um
SQLite local automaticamente.
