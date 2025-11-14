#!/usr/bin/env bash
set -euo pipefail
shopt -s extglob

# Dev helper para operar a stack dev+pg sem perder dados por engano.
# Comportamentos-chave replicados do seu "up":
# - validação de arquivos
# - docker compose config --services
# - checagem do serviço 'postgres'
# - up -d --build --pull always --remove-orphans
# - impressão de URLs e docker compose images
#
# Ações: up | restart | stop | down | reset | logs | ps | menu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEV_YML="${INFRA_DIR}/docker-compose.dev.yml"
PG_YML="${INFRA_DIR}/docker-compose.pg.yml"

# Variáveis de ambiente com defaults para exibição
PGPORT_MAP="${PGPORT_MAP:-5432}"
PGDATABASE="${PGDATABASE:-portal}"
PGUSER="${PGUSER:-portal}"

# Resolve docker compose vs docker-compose
dc() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    echo "Erro: nem 'docker compose' nem 'docker-compose' encontrados no PATH." >&2
    exit 127
  fi
}

compose_cmd() {
  dc -f "$DEV_YML" -f "$PG_YML" "$@"
}

# Helper: acrescenta EXTRA_COMPOSE_ARGS apenas se houver itens
compose_with_extra() {
  if (( ${#EXTRA_COMPOSE_ARGS[@]} )); then
    compose_cmd "$@" "${EXTRA_COMPOSE_ARGS[@]}"
  else
    compose_cmd "$@"
  fi
}

confirm() {
  local msg="${1:-Confirma?}"
  read -r -p "$msg [y/N] " ans
  [[ "${ans:-N}" =~ ^[Yy]$ ]]
}

usage() {
  cat <<'USAGE'
Uso:
  dev.sh [acao] [opcoes] [-- ARGS_DO_COMPOSE...]

Ações:
  up           Valida e sobe a stack (build + pull always + remove-orphans).
  restart      Recria containers (mantém volumes; build + remove-orphans).
  stop         Para containers (mantém volumes).
  down         Derruba containers (mantém volumes).
  reset        Derruba e REMOVE volumes (apaga dados). Pede confirmação.
  logs         Segue logs agregados (-f).
  ps           Lista containers.
  menu         Modo interativo.

Opções:
  -y, --yes    Confirma automaticamente operações destrutivas (reset).
  -h, --help   Ajuda.

Observação:
  Argumentos após '--' são passados ao Docker Compose, ex.: dev.sh up -- --scale bff=2
USAGE
}

# --------- Parsing básico de flags ----------
YES=0
ACTION="${1:-menu}"
shift || true

EXTRA_COMPOSE_ARGS=()
POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --) shift; EXTRA_COMPOSE_ARGS=("$@"); break ;;
    -y|--yes) YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) POSITIONAL+=("$1"); shift ;;
  esac
done
set -- "${POSITIONAL[@]}"

# --------- Validações comuns ----------
validate_files() {
  [[ -f "$DEV_YML" ]] || { echo "❌ Não encontrei ${DEV_YML}"; exit 1; }
  [[ -f "$PG_YML"  ]] || { echo "❌ Não encontrei ${PG_YML}"; exit 1; }
}

print_services() {
  echo "ℹ️  Validando serviços presentes na composição..."
  compose_cmd config --services
  echo
}

check_postgres() {
  if ! ( compose_cmd config --services | tr -d '\r' | grep -Fxq 'postgres' ); then
    echo "❌ O serviço 'postgres' não entrou na composição."
    echo "   Verifique o arquivo ${PG_YML}."
    exit 1
  fi
}

print_urls() {
  echo
  echo "✅ Stack dev+pg no ar."
  echo " • Host    : http://localhost:5173"
  echo " • BFF     : http://localhost:8000"
  echo " • Postgres: localhost:${PGPORT_MAP}  (db=${PGDATABASE}, user=${PGUSER})"
}

print_images() {
  echo
  echo "ℹ️  Imagens em uso (com tamanhos):"
  compose_cmd images
}

# --------- Ações ----------
action_up() {
  validate_files
  print_services
  check_postgres
  # pontos principais: build + pull always + remove-orphans
  compose_with_extra up -d --build --pull always --remove-orphans
  print_urls
  print_images
}

action_restart() {
  validate_files
  print_services
  check_postgres
  # Reinício sem forçar pull always (mantém semântica distinta do "up" original),
  # mas com build e remove-orphans; ajuste se preferir igual ao up.
  compose_with_extra up -d --build --remove-orphans
  print_urls
}

action_stop() {
  validate_files
  compose_with_extra stop
  echo "OK: containers parados (volumes preservados)."
}

action_down() {
  validate_files
  compose_with_extra down
  echo "OK: containers derrubados (volumes preservados)."
}

action_reset() {
  validate_files
  if [[ $YES -ne 1 ]]; then
    echo "ATENÇÃO: esta operação removerá volumes e apagará dados persistidos (ex.: banco)."
    confirm "Prosseguir com RESET (down -v)?" || { echo "Cancelado."; return 1; }
  fi
  compose_with_extra down -v
  echo "🛑 Stack dev+pg derrubado e volumes removidos."
}

action_logs() {
  validate_files
  compose_with_extra logs -f
}

action_ps() {
  validate_files
  compose_with_extra ps
}

action_menu() {
  echo "Selecione a operação:"
  echo "  1) up        - subir (build + pull always)"
  echo "  2) restart   - recriar containers (sem perder dados)"
  echo "  3) stop      - parar containers"
  echo "  4) down      - derrubar (manter volumes)"
  echo "  5) reset     - derrubar e remover volumes (APAGA dados)"
  echo "  6) logs      - seguir logs"
  echo "  7) ps        - listar"
  echo "  0) sair"
  read -r -p "> " opt
  case "$opt" in
    1) action_up ;;
    2) action_restart ;;
    3) action_stop ;;
    4) action_down ;;
    5) action_reset ;;
    6) action_logs ;;
    7) action_ps ;;
    0) exit 0 ;;
    *) echo "Opção inválida."; exit 1 ;;
  esac
}

# --------- Dispatcher ----------
case "$ACTION" in
  up) action_up ;;
  restart) action_restart ;;
  stop) action_stop ;;
  down) action_down ;;
  reset) action_reset ;;
  logs) action_logs ;;
  ps) action_ps ;;
  menu) action_menu ;;
  *) echo "Ação inválida: $ACTION"; echo; usage; exit 2 ;;
esac
