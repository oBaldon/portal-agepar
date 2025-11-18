---
id: execução-direta-vite-uvicorn
title: "Execução direta (Vite + Uvicorn)"
sidebar_position: 2
---

Esta página descreve como rodar **sem Docker**: **Host (Vite/React)**, **BFF (FastAPI/Uvicorn)** e **Docs (Docusaurus)** diretamente na sua máquina.

> Requisitos mínimos recomendados: **Node.js 18+ (com pnpm)** e **Python 3.11+**. Para o BFF, é necessário um **Postgres** acessível via `DATABASE_URL`.

---

## 1) Serviços e portas (local)

- **host (Vite/React)** → `5173`  
  Proxies para **`/api`**, **`/catalog`** e **`/docs`**.
- **bff (FastAPI)** → `8000`  
  Endpoints de catálogo/automations; requer **Postgres** (`DATABASE_URL`).
- **docs (Docusaurus)** → `8000` (dev server local; em produção vira estático).

---

## 2) Banco de dados (Postgres)

Você pode usar:
- **Postgres local** (rodando na sua máquina), ou
- **Postgres do Compose** (publicado em `localhost:5432`).

### `DATABASE_URL` típicos
- Local: `postgresql://agepar:agepar@localhost:5432/agepar`
- Compose publicado: `postgresql://agepar:agepar@localhost:5432/agepar`

> Se usar o Postgres **dentro do Compose** **e** rodar o BFF **fora** do Compose, **exponha** a porta `5432` no Compose para acessá-lo via `localhost`.

---

## 3) Rodando o BFF (FastAPI/Uvicorn)

No diretório `apps/bff`:

```bash
python -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows

pip install -r requirements.txt

export ENV=dev
export CORS_ORIGINS=http://localhost:5173
export SESSION_SECRET=dev-secret
export DATABASE_URL=postgresql://agepar:agepar@localhost:5432/agepar
# (opcional) export CATALOG_FILE=$(pwd)/../../catalog/catalog.dev.json

uvicorn app.main:APP --reload --host 0.0.0.0 --port 8000
# se a sua versão exportar "app" minúsculo:
# uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
````

> Confirme no código se o objeto ASGI exportado é `APP` ou `app`.

---

## 4) Rodando o Host (Vite/React)

No diretório `apps/host`:

```bash
pnpm install   # ou: npm ci
pnpm dev -- --host 0.0.0.0 --port 5173
# ou: npm run dev -- --host 0.0.0.0 --port 5173
```

O Host proxia automaticamente:

* **`/api`** e **`/catalog`** → `http://localhost:8000`
* **`/docs`** → `http://localhost:8000` (servidas pelo Host/Docs em dev)

---

## 5) Rodando as Docs (Docusaurus)

No diretório `apps/docs-site`:

```bash
pnpm install   # ou: npm ci
pnpm start -- --host 0.0.0.0 --port 8000
# ou: npm run start -- --host 0.0.0.0 --port 8000
```

> Em dev, acesse as docs **via Host** em `http://localhost:5173/docs`.

---

## 6) Verificações rápidas

* Host: `http://localhost:5173`
* BFF OpenAPI: `http://localhost:8000/api/docs`
* Docs via Host: `http://localhost:5173/docs`

### cURLs úteis

```bash
# BFF (OpenAPI)
curl -i http://localhost:8000/api/docs

# Catálogo direto do BFF
curl -s http://localhost:8000/catalog/dev | jq .

# Proxies via Host (dev)
curl -i http://localhost:5173/api/docs
curl -s http://localhost:5173/catalog/dev | jq .
curl -i http://localhost:5173/docs
```

---

## 7) Problemas comuns

* **`Connection refused` ao conectar no Postgres**
  Verifique se o Postgres está rodando e se a porta `5432` está publicada; revise `DATABASE_URL`.

* **CORS/Sessão falhando**
  Inclua `http://localhost:5173` em `CORS_ORIGINS` no BFF e habilite `allow_credentials=True` no middleware de CORS.

* **`ModuleNotFoundError` ou objeto ASGI não encontrado**
  Use `uvicorn app.main:APP` **ou** `uvicorn app.main:app` conforme o export real no código.

* **Portas já em uso (5173/8000/5432)**
  Libere as portas ou altere-as nos comandos/arquivos de configuração.

* **Refresh quebra rotas no Host (SPA)**
  Em produção, configure `try_files`/fallback; em dev, o Vite já trata.

---

## Próximos passos

* **[Proxies do Vite (/api, /catalog, /docs)](./proxies-do-vite-api-catalog-docs)**
* **[Estratégia de build (prod) e artefatos](./estratégia-de-build-prod-e-artefatos)**
* **[CI/CD (se aplicável)](./ci-cd-se-aplicável)**

---

> _Criado em 2025-11-18_
