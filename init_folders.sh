#!/usr/bin/env bash
set -euo pipefail

# raiz assume que você está em portal-agepar/
mkdir -p apps/host/src
mkdir -p apps/bff/app
mkdir -p catalog
mkdir -p infra
mkdir -p packages/design-system
mkdir -p packages/shared-schemas
mkdir -p packages/sdk-ts
mkdir -p packages/sdk-py
mkdir -p .github/workflows

# arquivos “marcadores” para manter diretórios no git
touch apps/host/src/.gitkeep
touch apps/bff/app/.gitkeep
touch catalog/.gitkeep
touch infra/.gitkeep
touch packages/design-system/.gitkeep
touch packages/shared-schemas/.gitkeep
touch packages/sdk-ts/.gitkeep
touch packages/sdk-py/.gitkeep
touch .github/workflows/.gitkeep

# arquivos base vazios
: > .env.example
cat > README.md <<'MD'
# Portal AGEPAR 2.0
Fundação do portal modular (Host + BFF) com catálogo de blocos zero-touch.
MD

# .gitignore mínimo
cat > .gitignore <<'GI'
# Node
node_modules/
dist/
.cache/
*.log

# Python
__pycache__/
*.pyc
.venv/

# Env & local
.env
.DS_Store

# Builds
build/
GI

echo "Estrutura criada."
