#!/usr/bin/env bash
set -euo pipefail

# scripts em infra/scripts ; compose em infra/
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEV_YML="${INFRA_DIR}/docker-compose.dev.yml"
PG_YML="${INFRA_DIR}/docker-compose.pg.yml"

[[ -f "$DEV_YML" ]] || { echo "❌ Não encontrei ${DEV_YML}"; exit 1; }
[[ -f "$PG_YML"  ]] || { echo "❌ Não encontrei ${PG_YML}"; exit 1; }

echo "ℹ️  Validando serviços presentes na composição..."
docker compose -f "$DEV_YML" -f "$PG_YML" config --services
echo

# Confere se 'postgres' entrou na composição (nega o pipeline inteiro)
if ! (
  docker compose -f "$DEV_YML" -f "$PG_YML" config --services \
  | tr -d '\r' \
  | grep -Fxq 'postgres'
); then
  echo "❌ O serviço 'postgres' não entrou na composição."
  echo "   Verifique o arquivo ${PG_YML}."
  exit 1
fi

# 👍 Ponto principal: garantir bases atualizadas e rebuildar o bff com base nova
docker compose -f "$DEV_YML" -f "$PG_YML" up -d --build --pull always --remove-orphans

echo
echo "✅ Stack dev+pg no ar."
echo " • Host    : http://localhost:5173"
echo " • BFF     : http://localhost:8000"
echo " • Postgres: localhost:${PGPORT_MAP:-5432}  (db=${PGDATABASE:-portal}, user=${PGUSER:-portal})"

echo
echo "ℹ️  Imagens em uso (com tamanhos):"
docker compose -f "$DEV_YML" -f "$PG_YML" images
