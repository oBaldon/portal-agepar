#!/usr/bin/env bash
set -euo pipefail

# Uso:
#   ./infra/scripts/dev_fresh.sh           # zera tudo, inclusive DB (pg_data)
#   ./infra/scripts/dev_fresh.sh --keep-db # preserva DB, zera containers e imagens

KEEP_DB="no"
if [[ "${1:-}" == "--keep-db" ]]; then
  KEEP_DB="yes"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEV_YML="${INFRA_DIR}/docker-compose.dev.yml"
PG_YML="${INFRA_DIR}/docker-compose.pg.yml"

[[ -f "$DEV_YML" ]] || { echo "❌ Não encontrei ${DEV_YML}"; exit 1; }
[[ -f "$PG_YML"  ]] || { echo "❌ Não encontrei ${PG_YML}"; exit 1; }

echo "🧹 Limpando stack (containers, logs e imagens locais do projeto)..."

if [[ "$KEEP_DB" == "yes" ]]; then
  docker compose -f "$DEV_YML" -f "$PG_YML" down --remove-orphans
else
  docker compose -f "$DEV_YML" -f "$PG_YML" down --remove-orphans --volumes
fi

# Remove imagens locais do projeto (prefixadas com o nome do diretório infra/)
set +e
COMPOSE_PROJECT_NAME="$(basename "$(cd "${INFRA_DIR}/.." && pwd)")"
COMPOSE_PROJECT_NAME="$(echo "$COMPOSE_PROJECT_NAME" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9-_')"
docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' | grep "$COMPOSE_PROJECT_NAME" | awk '{print $2}' | xargs -r docker rmi -f
set -e

docker builder prune -f >/dev/null

echo "🚀 Subindo novamente (build do zero)..."
docker compose -f "$DEV_YML" -f "$PG_YML" up -d --build

echo
echo "✅ Pronto. Logs começaram do zero."
echo " • Host    : http://localhost:5173"
echo " • BFF     : http://localhost:8000"
