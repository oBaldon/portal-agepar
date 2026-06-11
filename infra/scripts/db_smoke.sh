#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROOT_DIR="$(cd "${INFRA_DIR}/.." && pwd)"
ROOT_ENV="${ROOT_DIR}/.env"
DEV_COMPOSE="${INFRA_DIR}/docker-compose.dev.yml"
PG_COMPOSE="${INFRA_DIR}/docker-compose.pg.yml"
SQL_DIR="${INFRA_DIR}/sql"

[[ -f "${DEV_COMPOSE}" ]] || { echo "ERRO: não encontrei ${DEV_COMPOSE}"; exit 1; }
[[ -f "${PG_COMPOSE}"  ]] || { echo "ERRO: não encontrei ${PG_COMPOSE} (override do Postgres)"; exit 1; }
[[ -f "${ROOT_ENV}" ]] || { echo "ERRO: não encontrei ${ROOT_ENV}. Copie .env.example para .env e ajuste os valores."; exit 1; }
for f in 001_init_auth_logs.sql 002_seed_auth_dev.sql 099_test_auth_logs.sql; do
  [[ -f "${SQL_DIR}/${f}" ]] || { echo "ERRO: não encontrei ${SQL_DIR}/${f}"; exit 1; }
done

compose() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose --project-directory "$ROOT_DIR" --env-file "$ROOT_ENV" -f "$DEV_COMPOSE" -f "$PG_COMPOSE" "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose --project-directory "$ROOT_DIR" --env-file "$ROOT_ENV" -f "$DEV_COMPOSE" -f "$PG_COMPOSE" "$@"
  else
    echo "ERRO: nem 'docker compose' nem 'docker-compose' encontrados no PATH." >&2
    exit 127
  fi
}

echo "[0/4] Stack:"
compose ps || true

echo "[1/4] Verificando versão do Postgres..."
compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "${PGUSER:-portal}" -d "${PGDATABASE:-portal}" -c "SELECT version();"

echo "[2/4] Aplicando (idempotente) 001_init_auth_logs.sql..."
compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "${PGUSER:-portal}" -d "${PGDATABASE:-portal}" \
  -f /docker-entrypoint-initdb.d/001_init_auth_logs.sql

echo "[3/4] Aplicando seeds de dev..."
compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "${PGUSER:-portal}" -d "${PGDATABASE:-portal}" \
  -f /docker-entrypoint-initdb.d/002_seed_auth_dev.sql

echo "[4/4] Smoke tests..."
compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "${PGUSER:-portal}" -d "${PGDATABASE:-portal}" \
  -f /docker-entrypoint-initdb.d/099_test_auth_logs.sql

echo "✅ Banco OK (schema + operações básicas)."
