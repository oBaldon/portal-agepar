#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROOT_DIR="$(cd "${INFRA_DIR}/.." && pwd)"
ROOT_ENV="${ROOT_DIR}/.env"
DEV_YML="${INFRA_DIR}/docker-compose.dev.yml"
PG_YML="${INFRA_DIR}/docker-compose.pg.yml"

[[ -f "$DEV_YML" ]] || { echo "❌ Não encontrei ${DEV_YML}"; exit 1; }
[[ -f "$PG_YML"  ]] || { echo "❌ Não encontrei ${PG_YML}"; exit 1; }
[[ -f "$ROOT_ENV" ]] || { echo "❌ Não encontrei ${ROOT_ENV}. Copie .env.example para .env e ajuste os valores."; exit 1; }

compose() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose --project-directory "$ROOT_DIR" --env-file "$ROOT_ENV" -f "$DEV_YML" -f "$PG_YML" "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose --project-directory "$ROOT_DIR" --env-file "$ROOT_ENV" -f "$DEV_YML" -f "$PG_YML" "$@"
  else
    echo "Erro: nem 'docker compose' nem 'docker-compose' encontrados no PATH." >&2
    exit 127
  fi
}

compose down -v

echo "🛑 Stack dev+pg derrubado e volumes removidos."
