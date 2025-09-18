#!/usr/bin/env bash
set -euo pipefail

# Uso:
#   ./infra/scripts/dev_fresh.sh           # zera tudo, inclusive DB (pg_data)
#   ./infra/scripts/dev_fresh.sh --keep-db # preserva DB, zera containers e imagens

KEEP_DB="no"
if [[ "${1:-}" == "--keep-db" ]]; then
  KEEP_DB="yes"
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEV_YML="${ROOT_DIR}/docker-compose.dev.yml"
PG_YML="${ROOT_DIR}/docker-compose.pg.yml"

echo "🧹 Limpando stack (containers, logs e imagens locais do projeto)..."

if [[ "$KEEP_DB" == "yes" ]]; then
  docker compose -f "$DEV_YML" -f "$PG_YML" down --remove-orphans
else
  docker compose -f "$DEV_YML" -f "$PG_YML" down --remove-orphans --volumes
fi

# Remove apenas imagens construídas localmente pelo compose atual (se existirem)
# Ignora imagens de bases oficiais (node, postgres, etc.)
set +e
COMPOSE_PROJECT_NAME=$(basename "$ROOT_DIR" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9-_')
docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' | grep "$COMPOSE_PROJECT_NAME" | awk '{print $2}' | xargs -r docker rmi -f
set -e

# Limpa cache de build (para garantir rebuild 100% novo)
docker builder prune -f >/dev/null

echo "🚀 Subindo novamente (build do zero)..."
docker compose -f "$DEV_YML" -f "$PG_YML" up -d --build

echo
echo "✅ Pronto. Logs começaram do zero."
echo " • Host    : http://localhost:5173"
echo " • BFF     : http://localhost:8000"
echo " • Docs    : http://localhost:5173/docs"
