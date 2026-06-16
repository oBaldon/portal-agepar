---
id: "notificacoes-inbox"
title: "Notificações (Inbox)"
sidebar_position: 9
---

## Objetivo

O Portal AGEPAR possui uma **aba de Notificações** vinculada à **conta** do usuário e aos seus **cargos/papéis (roles)**.

Você pode enviar uma notificação para:

- **uma pessoa específica** (por `user_id`), e/ou
- **todas as pessoas com um cargo específico** (por role efetiva, ex.: `compras`, `rh`, `ferias`).

> A “role efetiva” considera: roles do BD + `AUTH_DEFAULT_ROLES` + superuser ⇒ `admin`.

---


## Estado atual implementado

- router em `apps/bff/app/notifications.py`, com prefixo `/api/notifications`;
- persistência em Postgres;
- envio para `userIds` e `roleNames`;
- contagem de não lidas no Host via `getUnreadNotificationCount()`;
- integração opcional de e-mail via Expresso descrita na página seguinte.

## Modelo de dados (Postgres)

Tabelas criadas no startup do BFF (`apps/bff/app/db.py`):

- `notifications` — mensagem canônica (título, corpo, nível, ação e meta)
- `notification_recipients` — entrega por usuário (lida/não lida via `read_at`)

---

## Rotas HTTP

### Listar minhas notificações

`GET /api/notifications`

Query params:

- `unread_only` (bool) — somente não lidas
- `limit` (1–200), `offset`

### Contagem de não lidas

`GET /api/notifications/unread-count`

Resposta:

```json
{ "unread": 3 }
```

### Marcar como lida

`POST /api/notifications/{id}/read` → `204`

### Marcar todas como lidas

`POST /api/notifications/read-all` → `204`

### Enviar (admin)

`POST /api/notifications/send`

Payload (exemplo):

```json
{
  "title": "DFD aprovado",
  "message": "O DFD 123 foi aprovado e pode seguir para a próxima etapa.",
  "level": "success",
  "actionUrl": "/dfd",
  "targets": {
    "userIds": ["11111111-1111-1111-1111-111111111111"],
    "roleNames": ["compras"]
  },
  "meta": { "kind": "dfd", "submissionId": "..." }
}
```

---

## Integração server-side (automations)

Automations no BFF podem enviar notificações diretamente via import:

```py
from app.notifications import send_notification

send_notification(
    actor=session_user,                 # request.session["user"]
    title="Pendência",
    message="Há uma pendência para você.",
    role_names=["compras"],
    user_ids=["11111111-1111-1111-1111-111111111111"],
    action_url="/dfd",
    meta={"kind": "dfd"},
)
```

