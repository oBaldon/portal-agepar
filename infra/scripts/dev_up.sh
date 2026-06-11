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

echo "ℹ️  Validando serviços presentes na composição..."
compose config --services
echo

if ! ( compose config --services | tr -d '\r' | grep -Fxq 'postgres' ); then
  echo "❌ O serviço 'postgres' não entrou na composição."
  echo "   Verifique o arquivo ${PG_YML}."
  exit 1
fi

compose up -d --build --pull always --remove-orphans

echo
echo "✅ Stack dev+pg no ar."
echo " • Host    : http://localhost:5173"
echo " • BFF     : http://localhost:8000"
echo " • Postgres: localhost:${PGPORT_MAP:-5432}  (db=${PGDATABASE:-portal}, user=${PGUSER:-portal})"

echo
echo "ℹ️  Imagens em uso (com tamanhos):"
compose images
