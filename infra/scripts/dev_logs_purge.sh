#!/usr/bin/env bash
set -euo pipefail

# Trunca os arquivos de log JSON do Docker (Linux).
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "⚠️ Script pensado para Linux (/var/lib/docker/containers)."
  echo "Use o dev_fresh.sh para limpar via recriação em macOS/Windows."
  exit 1
fi

CONTAINERS=$(docker ps -a --format '{{.ID}}\t{{.Names}}' | grep 'portal-agepar-' || true)
if [[ -z "$CONTAINERS" ]]; then
  echo "ℹ️ Nenhum container com prefixo portal-agepar- encontrado."
  exit 0
fi

echo "$CONTAINERS" | while IFS=$'\t' read -r ID NAME; do
  LOG_FILE="/var/lib/docker/containers/${ID}/${ID}-json.log"
  if [[ -f "$LOG_FILE" ]]; then
    echo "🧽 Truncando log de ${NAME} (${ID})..."
    sudo truncate -s 0 "$LOG_FILE"
  else
    echo "ℹ️ Arquivo de log não encontrado para ${NAME} (${ID})."
  fi
done

echo "✅ Logs truncados."
