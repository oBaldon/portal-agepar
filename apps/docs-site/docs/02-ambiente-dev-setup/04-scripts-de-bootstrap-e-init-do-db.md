---
id: scripts-de-bootstrap-e-init-do-db
title: "Scripts de bootstrap e init do banco"
sidebar_position: 4
---

## Script operacional principal

Arquivo:
- `infra/scripts/dev.sh`

Ações suportadas:
- `up`
- `restart`
- `stop`
- `down`
- `reset`
- `logs`
- `ps`
- `migrate-init`
- `menu`

## Por que esse script importa

Ele resolve a realidade atual do projeto:
- compose dividido em dois arquivos;
- necessidade de `.env` da raiz;
- presença obrigatória do serviço `postgres`;
- desejo de não apagar volumes por engano.

## Inicialização do banco

Há duas camadas complementares:

### 1. `infra/sql/init_db.sql`
Schema consolidado:
- users
- roles
- user_roles
- auth_sessions
- avisos
- estruturas auxiliares

### 2. `apps/bff/app/db.py`
No startup do BFF, `init_db()` garante tabelas operacionais da aplicação:
- submissions
- automation_audits
- fileshare_items
- notifications
- platform_alerts
- tasks e eventos

## Comando útil

```bash
./infra/scripts/dev.sh migrate-init
```

Use esse caminho quando quiser reaplicar o SQL consolidado no banco atual sem
destruir volumes.
