---
id: variáveis-de-ambiente-e-cors-cookies
title: "Variáveis de ambiente, CORS e cookies"
sidebar_position: 3
---

## Variáveis mais relevantes do BFF

- `DATABASE_URL`
- `SESSION_SECRET`
- `CORS_ORIGINS`
- `AUTH_MODE`
- `AUTH_LEGACY_MOCK`
- `AUTH_DEFAULT_ROLES`
- `AUTH_ENABLE_SELF_REGISTER`
- `ACCOUNTS_CREATE_LEGACY_ENABLED`
- `EP_MODE`
- `LOG_LEVEL`

## CORS

Em `apps/bff/app/main.py`:
- `allow_credentials=True`
- origens vindas de `CORS_ORIGINS`
- default prático: `http://localhost:5173`

No compose dev:
- `http://localhost:5173`
- `http://127.0.0.1:5173`

## Cookie de sessão

O `SessionMiddleware` hoje está configurado com:

- cookie `portal_agepar_session`
- `same_site="lax"`
- `https_only=False`

Isso documenta o que o código faz hoje; não é um hardening completo para produção.

## Situação de segurança do `.env.example`

O arquivo existe para bootstrap, mas no estado atual contém valores sensíveis
versionados. A documentação registra isso para evitar que o comportamento seja
interpretado como prática aceitável.
