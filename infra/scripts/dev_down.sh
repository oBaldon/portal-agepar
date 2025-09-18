#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose \
  -f docker-compose.dev.yml \
  -f docker-compose.pg.yml \
  down -v

echo "🛑 Stack dev+pg derrubado e volumes removidos."
