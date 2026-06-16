---
id: sessões-mock-post-api-auth-login-get-api-me
title: "Auth local, sessões persistidas e mock legado"
sidebar_position: 2
---

> O nome do arquivo é histórico. O fluxo principal do repositório atual já não é
> “sessão mock”; é **auth local com sessão persistida em banco**.

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
2. o ID da sessão é espelhado em `request.session["db_session_id"]`;
3. o snapshot do usuário é espelhado em `request.session["user"]`;
4. o cookie `portal_agepar_session` carrega a sessão web assinada;
5. `DbSessionMiddleware` verifica se a sessão do banco ainda é válida.

## Modo legado de mock

Há um atalho legado:
- `GET /api/auth/login`

Mas ele só é montado quando:
- `AUTH_LEGACY_MOCK=1`

## Importante para dev

O repositório hoje mistura dois sinais:
- `run_dev.sh` default → `AUTH_MODE=local`
- `docker-compose.dev.yml` → `AUTH_MODE=mock`

Por isso, ao depurar autenticação, sempre confira:
```bash
curl -s http://localhost:8000/version | jq .
```
