#!/usr/bin/env bash
set -euo pipefail

export UVICORN_RELOAD="true"
export UVICORN_HOST="${UVICORN_HOST:-0.0.0.0}"
export UVICORN_PORT="${UVICORN_PORT:-8000}"

# Valores padrão de dev
export ENV="${ENV:-dev}"
export AUTH_MODE="${AUTH_MODE:-mock}"
export EP_MODE="${EP_MODE:-mock}"
export SESSION_SECRET="${SESSION_SECRET:-dev-secret}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:5173}"
export CATALOG_FILE="${CATALOG_FILE:-/catalog/catalog.dev.json}"

exec uvicorn app.main:APP --reload --host "$UVICORN_HOST" --port "$UVICORN_PORT"
