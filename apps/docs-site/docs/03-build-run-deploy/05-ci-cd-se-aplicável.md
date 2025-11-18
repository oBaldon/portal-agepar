---
id: ci-cd-se-aplicável
title: "CI/CD (se aplicável)"
sidebar_position: 5
---

Esta página apresenta um **pipeline de CI** para build/validação do **Host (Vite/React)**, **Docs (Docusaurus)** e **BFF (FastAPI)**, além de exemplos de **CD opcional** (deploy) e a lista de **segredos** necessários.

> Padrão sugerido: **GitHub Actions**, imagens do BFF publicadas no **GHCR** e artefatos estáticos (Host/Docs) publicados via servidor de estáticos (NGINX/CDN) ou GitHub Pages (Docs).

---

## 1) Visão geral do pipeline

```mermaid
flowchart LR
  A[push or PR] --> B[host build]
  A --> C[docs build]
  A --> D[bff docker build]
  B --> E[artifact host dist]
  C --> F[artifact docs build]
  D --> G[push BFF image GHCR]
  E --> H[deploy static NGINX or CDN]
  F --> I[deploy docs to path docs]
  G --> J[deploy BFF to orchestrator]
````

* **CI**: compila Host/Docs, monta imagem do BFF e publica a imagem no registry.
* **CD (opcional)**: publica Host/Docs como estáticos e atualiza o serviço do BFF.

---

## 2) Workflow de CI — GitHub Actions (exemplo)

Arquivo: `.github/workflows/ci.yml`

```yaml
name: ci
on:
  push:
    branches: [ main ]
  pull_request:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  host:
    name: Build Host
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: apps/host/package-lock.json
      - name: Install & Build
        working-directory: apps/host
        run: |
          npm ci
          npm run build
      - uses: actions/upload-artifact@v4
        with:
          name: host-dist
          path: apps/host/dist

  docs:
    name: Build Docs
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: apps/docs-site/package-lock.json
      - name: Install & Build
        working-directory: apps/docs-site
        run: |
          npm ci
          npm run build
      - uses: actions/upload-artifact@v4
        with:
          name: docs-build
          path: apps/docs-site/build

  bff:
    name: Build & Push BFF Image
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Login GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build & Push
        run: |
          IMAGE=ghcr.io/${{ github.repository_owner }}/portal-agepar-bff
          TAG=${{ github.sha }}
          docker build \
            -t $IMAGE:$TAG \
            -f apps/bff/Dockerfile.dev apps/bff
          docker tag $IMAGE:$TAG $IMAGE:edge
          docker push $IMAGE:$TAG
          docker push $IMAGE:edge
```

> Ajuste o caminho do **Dockerfile** do BFF caso use um `Dockerfile` de produção.
> Se preferir **pnpm**, adicione `pnpm/action-setup` e troque `npm ci` por `pnpm install`/`pnpm build`.

---

## 3) CD — Exemplos (opcional)

### 3.1) Publicar **Docs** no GitHub Pages

```yaml
# adiciona este job ao workflow ou em workflow separado
deploy-docs:
  needs: [docs]
  if: github.ref == 'refs/heads/main'
  runs-on: ubuntu-latest
  permissions:
    contents: write
    pages: write
    id-token: write
  steps:
    - uses: actions/download-artifact@v4
      with:
        name: docs-build
        path: build
    - uses: actions/upload-pages-artifact@v3
      with:
        path: build
    - uses: actions/deploy-pages@v4
```

> Configure o Pages no repositório (`Settings` → `Pages`) e, se necessário, ajuste `baseUrl` do Docusaurus.

### 3.2) Publicar **Host** e **Docs** em servidor NGINX (rsync/SSH)

```yaml
deploy-static:
  needs: [host, docs]
  if: github.ref == 'refs/heads/main'
  runs-on: ubuntu-latest
  steps:
    - uses: actions/download-artifact@v4
      with: { name: host-dist, path: host-dist }
    - uses: actions/download-artifact@v4
      with: { name: docs-build, path: docs-build }
    - name: Rsync Host
      uses: burnett01/rsync-deployments@7.0.1
      with:
        switches: -avz --delete
        path: host-dist/
        remote_path: /var/www/portal-agepar/host/dist/
        remote_host: ${{ secrets.SSH_HOST }}
        remote_user: ${{ secrets.SSH_USER }}
        remote_key: ${{ secrets.SSH_KEY }}
    - name: Rsync Docs
      uses: burnett01/rsync-deployments@7.0.1
      with:
        switches: -avz --delete
        path: docs-build/
        remote_path: /var/www/portal-agepar/docs/build/
        remote_host: ${{ secrets.SSH_HOST }}
        remote_user: ${{ secrets.SSH_USER }}
        remote_key: ${{ secrets.SSH_KEY }}
```

### 3.3) Atualizar **BFF** no orquestrador (ex.: Docker Swarm/K8s)

* **Swarm**: `docker service update --image ghcr.io/<org>/portal-agepar-bff:<tag> portal_bff`
* **K8s**: `kubectl set image deploy/portal-bff bff=ghcr.io/<org>/portal-agepar-bff:<tag>`

> Aplique *healthchecks*, *readiness* e variáveis (`DATABASE_URL`, `CORS_ORIGINS`, `SESSION_SECRET`) via secrets/configmaps.

---

## 4) Segredos e permissões

* `GITHUB_TOKEN` (padrão; permissão **packages:write** para GHCR)
* (Se Docker Hub) `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`
* (Para SSH/rsync) `SSH_HOST`, `SSH_USER`, `SSH_KEY`
* (Opcional deploy cloud) credenciais do provedor (S3/CloudFront, etc.)

---

## 5) Smoke tests pós-deploy

```bash
# BFF
curl -i https://<dominio>/api/docs

# Catálogo
curl -s https://<dominio>/catalog/dev | jq .

# Docs
curl -I https://<dominio>/docs
```

---

## 6) Problemas comuns

* **Falha no push da imagem** → verifique permissões de `GITHUB_TOKEN` (packages: write) e o namespace `ghcr.io/<owner>`.
* **Assets das Docs quebrados em /docs** → alinhe `baseUrl` do Docusaurus **ou** use `alias` em NGINX conforme a estratégia de publicação.
* **Build do Host falha por basePath** → se servir sob subcaminho, use `vite build --base /portal/` e ajuste o servidor.
* **Deploy concorrente** → mantenha `concurrency` no workflow para evitar corridas em `main`.

---

## Próximos passos

* Integrar **checks** (lint/test) nos jobs de Host/Docs/BFF.
* Adicionar **deploy automatizado** para ambientes `staging`/`prod` com *environments* e *manual approvals*.
* Ativar **observabilidade** (logs/métricas/alertas) no ambiente de produção.

---

> _Criado em 2025-11-18_