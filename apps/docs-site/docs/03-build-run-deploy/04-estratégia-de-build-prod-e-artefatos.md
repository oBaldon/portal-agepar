---
id: estratégia-de-build-prod-e-artefatos
title: "Estratégia de build (prod) e artefatos"
sidebar_position: 4
---

Esta página descreve como gerar **artefatos de produção** para **Host (Vite/React)**, **Docs (Docusaurus)** e **BFF (FastAPI)**, além de exemplos de **publicação** (Nginx/static) e **empacotamento** (Docker).

> Requisitos mínimos para build: **Node.js 18+** (com **pnpm** ou **npm**) e **Python 3.11+** (para o BFF).  
> Rota final recomendada das docs via Host: **`/docs`**.

---

## 1) Artefatos de produção (saídas)

- **Host (Vite/React)**  
  - Build: `apps/host/dist/` (arquivos estáticos — SPA)
  - BasePath (se necessário): `vite build --base /portal/`

- **Docs (Docusaurus)**  
  - Build: `apps/docs-site/build/` (arquivos estáticos — site de documentação)

- **BFF (FastAPI)**  
  - Container Docker publicado em registry (ex.: `ghcr.io/<org>/portal-agepar-bff:<tag>`)

```mermaid
flowchart LR
  subgraph Static
    H[Host /dist]:::s
    D[Docs /build]:::s
  end
  subgraph Runtime
    BFF[(BFF - FastAPI)]:::r
    PG[(Postgres)]:::r
  end
  CDN[CDN/NGINX] --> H
  CDN --> D
  Client --> CDN
  Client -->|/api| BFF
  BFF --> PG

  classDef s fill:#eef,stroke:#99f;
  classDef r fill:#efe,stroke:#9c9;
````

---

## 2) Como gerar os builds (local)

### Host (Vite/React)

```bash
cd apps/host
pnpm install        # ou: npm ci
pnpm build          # ou: npm run build
# artefato: apps/host/dist/
```

### Docs (Docusaurus)

```bash
cd apps/docs-site
pnpm install        # ou: npm ci
pnpm build          # ou: npm run build
# artefato: apps/docs-site/build/
```

### BFF (FastAPI) — imagem Docker

```bash
# a partir da raiz ou apps/bff (ajuste o caminho do Dockerfile se necessário)
docker build -t ghcr.io/<org>/portal-agepar-bff:<tag> -f apps/bff/Dockerfile.dev apps/bff
docker push ghcr.io/<org>/portal-agepar-bff:<tag>
```

> Em produção, prefira **gunicorn + uvicorn workers** e *healthchecks* do orquestrador.

---

## 3) Publicação estática (Nginx)

Exemplo de configuração para servir o **Host** em `/` e as **Docs** em `/docs`, com fallback de SPA:

```nginx
server {
  listen 80;
  server_name _;

  # Host (SPA)
  root /var/www/portal-agepar/host/dist;
  index index.html;

  # Docs (Docusaurus) em /docs
  location /docs/ {
    alias /var/www/portal-agepar/docs/build/;
    try_files $uri $uri/ /docs/index.html;
  }

  # SPA fallback do Host
  location / {
    try_files $uri $uri/ /index.html;
  }

  # Proxy para o BFF (FastAPI)
  location /api/ {
    proxy_pass http://bff:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }
}
```

> Ajuste paths (`/var/www/...`) e upstream do BFF conforme sua infraestrutura (Docker, K8s, VM).

---

## 4) Imagem de produção do BFF (exemplo de Dockerfile)

```dockerfile
# apps/bff/Dockerfile
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# deps
COPY apps/bff/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# código
COPY apps/bff/app ./app

# variáveis padrão (ajuste em runtime)
ENV ENV=prod
EXPOSE 8000

# gunicorn + uvicorn workers (ex.: 2 workers, ajuste conforme CPU)
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8000", "app.main:APP"]
```

> Para **healthcheck**, exponha um **GET /health** no BFF ou use `/api/docs` como verificação de *readiness* (não recomendado para produção).

---

## 5) Variáveis de ambiente (produção)

* **BFF**

  * `ENV=prod`
  * `DATABASE_URL=postgresql://<user>:<pass>@<host>:5432/<db>`
  * `CORS_ORIGINS=https://<host-do-portal>` (e outros domínios necessários)
  * `SESSION_SECRET=<segredo>` (sem segredos no repositório)
* **Host/Docs** (estáticos)

  * Se atrás de subcaminho, **defina base** no build (`vite --base` ou `docusaurus.config` `baseUrl`).

---

## 6) Checklist de release

* [ ] **Host** buildado (`apps/host/dist/`) e publicado
* [ ] **Docs** buildadas (`apps/docs-site/build/`) e publicadas em **`/docs`**
* [ ] **BFF** com imagem publicada no registry e configurado atrás de proxy/TLS
* [ ] **Banco** provisionado e acessível (`DATABASE_URL` válido)
* [ ] **CORS** e **cookies** revisados (origens corretas; `allow_credentials=True` se necessário)
* [ ] **Logs/monitoramento** configurados (stdout estruturado, métricas e alertas)
* [ ] **Healthchecks**/readiness no orquestrador

---

## 7) Smoke tests (pós-deploy)

```bash
# OpenAPI (BFF)
curl -i https://<dominio>/api/docs

# Catálogo
curl -s https://<dominio>/catalog/dev | jq .

# Docs
curl -I https://<dominio>/docs
```

Se o Host for SPA em subcaminho, teste um refresh direto numa rota interna (ex.: `/app/etapas`) para validar `try_files`.

---

## 8) Problemas comuns

* **Refresh de rota SPA retorna 404**
  Configure `try_files` no Nginx/Apache (fallback para `index.html`).

* **`/docs` quebra assets (404/403)**
  Confirme `alias`/`root` corretos e que `baseUrl` do Docusaurus está **`/`** (quando servido em `/docs` via `alias`) **ou** ajuste para subcaminho.

* **CORS/Sessão em produção**
  Alinhe `CORS_ORIGINS` com o domínio público; ative `allow_credentials=True` se usar cookies de sessão.

* **Performance do BFF**
  Ajuste **workers** no gunicorn; habilite *keep-alive* no proxy e configure limites de conexão no Postgres.

---

## Próximos passos

* **[CI/CD (se aplicável)](./ci-cd-se-aplicável)** para automatizar build e publicação.
* **Observabilidade**: adicionar métricas, dashboards e alertas.
* **Segurança**: revisar cabeçalhos HTTP, TLS e política de cookies.

---

> _Criado em 2025-11-18_