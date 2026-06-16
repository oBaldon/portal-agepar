---
id: auth-local-sessões-persistidas-e-mock-legado
title: "Auth local, sessões persistidas e mock legado"
sidebar_position: 2
slug: /06-bff-fastapi/02-sessões-mock-post-api-auth-login-get-api-me
---

O fluxo principal do repositório atual é **auth local com sessão persistida em
banco**, mantendo um modo mock legado por configuração para cenários de
desenvolvimento e compatibilidade.

## Endpoints implementados

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/change-password`
- `POST /api/auth/logout`
- `GET /api/auth/sessions`
- `POST /api/auth/sessions/{session_id}/revoke`
- `GET /api/me`

## Como a sessão funciona

1. login válido cria uma linha em `auth_sessions`;
2. o ID da sessão é associado ao cookie assinado do navegador;
3. `GET /api/me` resolve o usuário atual a partir da sessão persistida;
4. `logout` e `revoke` invalidam a sessão no backend.

## Modos suportados

- `AUTH_MODE=local`: fluxo principal do estado atual.
- `AUTH_MODE=mock`: modo legado para desenvolvimento ou troubleshooting.

## Onde isso aparece no repo

- `apps/bff/app/auth/routes.py`
- `apps/bff/app/auth/service.py`
- `apps/bff/app/auth/models.py`
- `apps/bff/app/main.py`
