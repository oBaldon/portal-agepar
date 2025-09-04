# Autenticação — Modelagem & Banco (dev)

Este documento descreve o esquema Postgres usado para **login/registro**, **sessões**, **RBAC** e **logs**.

## Tabelas principais

- `users`: dados do servidor (CPF/e-mail únicos, `status`, `source=local|eprotocolo`, `is_superuser`, `attrs`).
- `roles` / `user_roles`: RBAC simples (ANY-of no host).
- `auth_sessions`: sessões server-side; o cookie no navegador conterá apenas um `session_id` opaco.
- `login_attempts`: tentativas (sucesso/erro) para auditoria e antifraude.
- `audit_events`: trilha de auditoria (ações relevantes de segurança/negócio).
- `app_logs`: logs estruturados de aplicação (futuro: integrar handler de logging).

## Decisões

- **E-mail `CITEXT`** (case-insensitive) e **CPF `CHAR(11)`** com *check* de formato.
- **Índices únicos parciais** para aceitar `NULL` em e-mail/CPF.
- **Extensão `pgcrypto`** para geração de UUIDs no banco.
- `VIEW audits` facilita migração do BFF que ainda usa `audits` no SQLite.

## Próximos passos

1. Implementar endpoints no BFF (`/api/auth/register`, `/api/auth/login`, `/api/auth/logout`, `/api/me`) com Argon2id.
2. Gerar cookie `session_id` (HTTPOnly, SameSite=Lax; `Secure` em produção) e persistir em `auth_sessions`.
3. Registrar eventos em `audit_events` e `login_attempts`.
4. RBAC: preencher `roles` e `user_roles`; integrar ao helper `requiredRoles` no host.

