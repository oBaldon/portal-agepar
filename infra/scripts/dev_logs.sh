#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

docker compose \
  -f "${INFRA_DIR}/docker-compose.dev.yml" \
  -f "${INFRA_DIR}/docker-compose.pg.yml" \
  logs -f
