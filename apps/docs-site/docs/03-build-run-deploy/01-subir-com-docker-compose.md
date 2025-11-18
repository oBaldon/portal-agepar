---
id: subir-com-docker-compose
title: "Subir com Docker Compose"
sidebar_position: 1
---

Esta página mostra como subir **Host (Vite/React)**, **BFF (FastAPI)** e **Docs (Docusaurus)** usando **Docker Compose** para desenvolvimento.

> No Compose padrão: `DATABASE_URL=postgresql://agepar:agepar@db:5432/agepar`.

---

## 1) Serviços e portas (dev)

- **host (Vite/React)** → `5173`  
  Proxies para **`/api`**, **`/catalog`** e **`/docs`**.
- **bff (FastAPI)** → `8000`  
  Endpoints de catálogo/automations; usa **Postgres** via `DATABASE_URL`.
- **db (Postgres)** → `5432` (Compose)
- **docs (Docusaurus)** → servido via Host em **`/docs`** no ambiente de dev.

---

## 2) Variáveis de ambiente (Compose)

- `DATABASE_URL` — conexão Postgres (ex.: `postgresql://agepar:agepar@db:5432/agepar`)
- `CORS_ORIGINS` — inclua `http://localhost:5173` **e** `http://host:5173` (quando em Compose)
- `ENV=dev` — habilita modo de desenvolvimento no BFF
- (Opcional) `SESSION_SECRET` — segredo de sessão para cookies

> Em Compose, defina `CORS_ORIGINS=http://localhost:5173,http://host:5173`.

---

## 3) Subir tudo com Docker

Na raiz do projeto:

```bash
docker compose up --build
````

> O primeiro build pode demorar por causa do cache de imagens e dependências.

---

## 4) Verificações rápidas

* Host: `http://localhost:5173`
* Docs via Host: `http://localhost:5173/docs`
* BFF (OpenAPI): `http://localhost:8000/api/docs`

### cURLs úteis

```bash
# Documentação OpenAPI (confirma BFF no ar)
curl -i http://localhost:8000/api/docs

# Catálogo exposto pelo BFF
curl -s http://localhost:8000/catalog/dev | jq .

# Proxies via Host (dev)
curl -i http://localhost:5173/api/docs
curl -s http://localhost:5173/catalog/dev | jq .
curl -i http://localhost:5173/docs
```

---

## 5) Comandos práticos (Compose)

```bash
# Logs contínuos (todas as services)
docker compose logs -f

# Logs do BFF
docker compose logs -f bff

# Rebuild apenas do Host
docker compose up -d --build host

# Subir em primeiro plano (útil para debug)
docker compose up

# Parar e remover containers
docker compose down

# Parar e remover containers + volumes (apaga banco)
docker compose down -v
```

---

## Problemas comuns

* **BFF não inicia / erro de banco**
  Verifique `DATABASE_URL` e o status da service `db` (Postgres). Confira `docker compose ps` e se a coluna `STATE` está “healthy”.

* **`/docs` retorna 404**
  Confirme se as **Docs** estão ativas e se o proxy do Host aponta para o caminho correto.

* **CORS/Sessão**
  Ajuste `CORS_ORIGINS` no BFF para incluir `http://localhost:5173` e `http://host:5173`. Cookies exigem `allow_credentials=True`.

* **Portas ocupadas (5173/8000/5432)**
  Finalize processos em conflito ou mapeie portas alternativas no Compose/Vite/uvicorn.

---

## Próximos passos

* **[Execução direta (Vite + Uvicorn)](./execução-direta-vite-uvicorn)**
* **[Proxies do Vite (/api, /catalog, /docs)](./proxies-do-vite-api-catalog-docs)**
* **[Estratégia de build (prod) e artefatos](./estratégia-de-build-prod-e-artefatos)**

---

> _Criado em 2025-11-18_