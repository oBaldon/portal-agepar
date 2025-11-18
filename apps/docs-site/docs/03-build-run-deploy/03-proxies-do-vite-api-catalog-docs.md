---
id: proxies-do-vite-api-catalog-docs
title: "Proxies do Vite (/api, /catalog, /docs)"
sidebar_position: 3
---

Esta página documenta como o **Host (Vite/React)** encaminha as requisições para o **BFF (FastAPI)** e para as **Docs (Docusaurus)** durante o desenvolvimento, usando o recurso de **proxy** do Vite.

> Padrão adotado: **`/api`** e **`/catalog`** → BFF, **`/docs`** → Docs.  
> Em Compose, o Host fala com os serviços pelos **nomes dos containers**; em execução local, usa **`localhost`**.

---

## 1) Serviços e rotas (resumo)

- **`/api`** → BFF (FastAPI)
- **`/catalog`** → BFF (catálogo `catalog.dev.json`)
- **`/docs`** → Docs (Docusaurus)

```mermaid
flowchart LR
  Client -->|/api, /catalog| Host[Vite :5173]
  Client -->|/docs| Host
  Host -->|/api, /catalog| BFF[FastAPI :8000]
  Host -->|/docs| DOCS[Docs dev server]
````

> Portas típicas: **BFF `:8000`**, **Docs dev `:8000` (Compose) ou `:3000` (local)**, **Host `:5173`**.

---

## 2) Configuração do Vite — Compose (containers)

Arquivo: `apps/host/vite.config.ts`

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api":     { target: "http://bff:8000",  changeOrigin: true },
      "/catalog": { target: "http://bff:8000",  changeOrigin: true },
      "/docs":    { target: "http://docs:8000", changeOrigin: true },
    },
  },
});
```

> **CORS**: no BFF, inclua `http://localhost:5173` **e** `http://host:5173` em `CORS_ORIGINS`.

---

## 3) Configuração do Vite — Execução local (sem Docker)

Se você roda tudo **fora** de containers, ajuste os targets para `localhost`.
Lembre que **BFF** e **Docs** não podem usar a **mesma porta**. Exemplo: BFF em `8000`, Docs em `3000`.

```ts
// apps/host/vite.config.ts (variante local)
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api":     { target: "http://localhost:8000", changeOrigin: true },
      "/catalog": { target: "http://localhost:8000", changeOrigin: true },
      "/docs":    { target: "http://localhost:3000", changeOrigin: true }, // Docusaurus
    },
  },
});
```

> Se você iniciar o Docusaurus em outra porta (ex.: `8001`), atualize o `target` de `/docs` para essa porta.

---

## 4) Testes rápidos (cURL)

```bash
# Via proxy do Host (dev)
curl -i http://localhost:5173/api/docs
curl -s http://localhost:5173/catalog/dev | jq .
curl -i http://localhost:5173/docs
```

> As respostas devem ser equivalentes às dos serviços de origem.
> Se algum endpoint **não** responder via Host, verifique a seção de troubleshooting.

---

## 5) Variáveis relacionadas (BFF)

* `CORS_ORIGINS=http://localhost:5173,http://host:5173`
* `ENV=dev`
* Cookies/sessão: garanta `allow_credentials=True` no CORS do BFF quando usar cookies.

---

## 6) Problemas comuns

* **`/docs` retorna 404**

  * Verifique se o serviço de **Docs** está no ar (porta/host corretos).
  * Confirme se a chave do proxy (`"/docs"`) está definida no `vite.config.ts`.

* **CORS/Sessão não funcionando**

  * Inclua as origens `http://localhost:5173` e `http://host:5173` no BFF.
  * Habilite `allow_credentials=True` se usar cookies.

* **Colisão de portas em execução local**

  * Não use a mesma porta para BFF e Docs. Ajuste `target` no Vite e a porta de `npm run start` do Docusaurus.

* **Resposta diferente via Host e direto no serviço**

  * Cheque `changeOrigin: true` e se existe algum rewrite ausente (não necessário para as rotas padrão deste projeto).

---

## Próximos passos

* **[Execução direta (Vite + Uvicorn)](./execução-direta-vite-uvicorn)**
* **[Subir com Docker Compose](./subir-com-docker-compose)**
* **[Estratégia de build (prod) e artefatos](./estratégia-de-build-prod-e-artefatos)**

---

> _Criado em 2025-11-18_