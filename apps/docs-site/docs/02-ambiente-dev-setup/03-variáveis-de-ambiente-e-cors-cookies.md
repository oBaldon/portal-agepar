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

## Situação do `.env.example`

O arquivo existe para bootstrap e, neste snapshot, já está sanitizado:

- `EXPRESSO_API_USER` e `EXPRESSO_API_PASSWORD` vêm vazios;
- `SESSION_SECRET=dev-secret` e `PGPASSWORD=portaldev` são defaults de laboratório;
- cada ambiente continua responsável por injetar seus próprios segredos fora do versionamento.

A regra continua a mesma: **segredos reais não entram no repositório**.
