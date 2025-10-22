#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEV_COMPOSE="${INFRA_DIR}/docker-compose.dev.yml"
PG_COMPOSE="${INFRA_DIR}/docker-compose.pg.yml"
SQL_DIR="${INFRA_DIR}/sql"

[[ -f "${DEV_COMPOSE}" ]] || { echo "ERRO: não encontrei ${DEV_COMPOSE}"; exit 1; }
[[ -f "${PG_COMPOSE}"  ]] || { echo "ERRO: não encontrei ${PG_COMPOSE} (override do Postgres)"; exit 1; }
for f in 001_init_auth_logs.sql 002_seed_auth_dev.sql 099_test_auth_logs.sql; do
  [[ -f "${SQL_DIR}/${f}" ]] || { echo "ERRO: não encontrei ${SQL_DIR}/${f}"; exit 1; }
done

COMPOSE="docker compose -f ${DEV_COMPOSE} -f ${PG_COMPOSE}"

echo "[0/4] Stack:"
${COMPOSE} ps || true

echo "[1/4] Verificando versão do Postgres..."
${COMPOSE} exec -T postgres psql -v ON_ERROR_STOP=1 -U "${PGUSER:-portal}" -d "${PGDATABASE:-portal}" -c "SELECT version();"

echo "[2/4] Aplicando (idempotente) 001_init_auth_logs.sql..."
${COMPOSE} exec -T postgres psql -v ON_ERROR_STOP=1 -U "${PGUSER:-portal}" -d "${PGDATABASE:-portal}" \
  -f /docker-entrypoint-initdb.d/001_init_auth_logs.sql

echo "[3/4] Aplicando seeds de dev..."
${COMPOSE} exec -T postgres psql -v ON_ERROR_STOP=1 -U "${PGUSER:-portal}" -d "${PGDATABASE:-portal}" \
  -f /docker-entrypoint-initdb.d/002_seed_auth_dev.sql

echo "[4/4] Smoke tests..."
${COMPOSE} exec -T postgres psql -v ON_ERROR_STOP=1 -U "${PGUSER:-portal}" -d "${PGDATABASE:-portal}" \
  -f /docker-entrypoint-initdb.d/099_test_auth_logs.sql

echo "✅ Banco OK (schema + operações básicas)."
