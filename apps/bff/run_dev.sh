#!/usr/bin/env bash
set -euo pipefail

# ----------------------------
# Uvicorn (dev)
# ----------------------------
export UVICORN_RELOAD="true"
export UVICORN_HOST="${UVICORN_HOST:-0.0.0.0}"
export UVICORN_PORT="${UVICORN_PORT:-8000}"

# ----------------------------
# Ambiente (dev)
# ----------------------------
export ENV="${ENV:-dev}"

# 🔐 Autenticação real (sem mock por padrão)
export AUTH_MODE="${AUTH_MODE:-local}"

# Permite dev@local com qualquer senha no ENV=dev (útil em desenvolvimento)
export AUTH_DEV_ALLOW_ANY_PASSWORD="${AUTH_DEV_ALLOW_ANY_PASSWORD:-1}"

# TTLs de sessão
export SESSION_TTL_HOURS="${SESSION_TTL_HOURS:-8}"
export REMEMBER_ME_TTL_DAYS="${REMEMBER_ME_TTL_DAYS:-30}"

# Sliding session (renova antes de expirar) + janela de renovação
export SESSION_SLIDING="${SESSION_SLIDING:-1}"
export SESSION_RENEW_BEFORE_MINUTES="${SESSION_RENEW_BEFORE_MINUTES:-30}"

# Revogar sessão atual efetua auto-logout do cliente (zera cookie)
export AUTH_REVOKE_AUTO_LOGOUT_CURRENT="${AUTH_REVOKE_AUTO_LOGOUT_CURRENT:-1}"

# eProtocolo continua mockado em dev (sem impacto na auth)
export EP_MODE="${EP_MODE:-mock}"

# Sessão HTTP (cookie)
export SESSION_SECRET="${SESSION_SECRET:-dev-secret}"

# CORS p/ o Vite host
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:5173}"

# Catálogo (dev)
export CATALOG_FILE="${CATALOG_FILE:-/catalog/catalog.dev.json}"

# OBS: DATABASE_URL deve vir do docker-compose/.env; não definimos default aqui.

exec uvicorn app.main:APP --reload --host "$UVICORN_HOST" --port "$UVICORN_PORT"
