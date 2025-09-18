#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEV_YML="${ROOT_DIR}/docker-compose.dev.yml"
PG_YML="${ROOT_DIR}/docker-compose.pg.yml"

if [[ ! -f "$DEV_YML" ]]; then
  echo "❌ Não encontrei ${DEV_YML}"; exit 1
fi
if [[ ! -f "$PG_YML" ]]; then
  echo "❌ Não encontrei ${PG_YML}"; exit 1
fi

echo "ℹ️  Validando serviços presentes na composição..."
docker compose -f "$DEV_YML" -f "$PG_YML" config --services
echo

if ! docker compose -f "$DEV_YML" -f "$PG_YML" config --services | grep -q '^postgres$'; then
  echo "❌ O serviço 'postgres' não entrou na composição."
  echo "   Verifique o arquivo ${PG_YML} (nome do serviço deve ser 'postgres' e sem 'profiles')."
  exit 1
fi

docker compose -f "$DEV_YML" -f "$PG_YML" up -d --build

echo
echo "✅ Stack dev+pg no ar."
echo " • Host    : http://localhost:5173"
echo " • BFF     : http://localhost:8000"
echo " • Docs    : http://localhost:5173/docs (proxy)"
echo " • Postgres: localhost:${PGPORT_MAP:-5432}  (db=${PGDATABASE:-portal}, user=${PGUSER:-portal})"