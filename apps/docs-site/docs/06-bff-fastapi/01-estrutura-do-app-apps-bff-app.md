---
id: estrutura-do-app-apps-bff-app
title: "Estrutura do app em apps/bff/app"
sidebar_position: 1
---

## Pastas centrais

```text
apps/bff/app/
  auth/
  automations/
  games/
  utils/
  db.py
  main.py
  notifications.py
```

## `main.py`
Responsável por:
- criar o FastAPI;
- configurar CORS;
- configurar `DbSessionMiddleware` + `SessionMiddleware`;
- chamar `init_db()` no startup;
- montar routers de auth, notificações e automações;
- expor `/health`, `/version`, `/api/me`, `/catalog/dev` e utilitários.

## `auth/`
Concentra:
- `routes.py`
- `sessions.py`
- `middleware.py`
- `rbac.py`
- política de senha e saldo de férias

## `automations/`
Concentra os módulos de negócio e apoio:
- compras
- pessoas
- produtividade
- suporte
- administração

## `db.py`
No estado atual, vai além de “submissions e audits” e já inclui tarefas,
notificações, fileshare e avisos.
