# Portal AGEPAR

Documentação e monorepo do **Portal AGEPAR** — plataforma modular com **BFF FastAPI**, **Host React/Vite** e **Docs Docusaurus**. Foco em automações para o fluxo de compras público (DFD → PCA → ETP → TR → Cotação/Dispensa/Licitação → Contrato → Execução).

> Público-alvo: **desenvolvedores** que irão programar na plataforma.

---

## ✨ Features

* **BFF (FastAPI)**: sessões mock/real, RBAC **ANY-of**, automations modulares em `/api/automations/{slug}`.
* **Host (Vite + React/TS)**: catálogo por **categorias** e **cards**, renderização de blocos via `<iframe>`.
* **Docs (Docusaurus v3)**: portal de devs servido via proxy em **`/devdocs`**.
* **Banco**: **PostgreSQL** no ambiente dev (produção-ready).
* **Observabilidade**: logs INFO/ERROR, erros HTTP claros (400/401/403/404/409/422).

---

## 🧱 Stack

* **Backend**: Python 3.11, FastAPI, Pydantic v2, psycopg
* **Frontend**: React 18, Vite, TypeScript, Tailwind
* **Docs**: Docusaurus v3 (Mermaid), TypeDoc, pdoc, OpenAPI
* **Infra (dev)**: Docker Compose, Postgres 16

---

## 📦 Estrutura do monorepo

```
apps/
  bff/                # FastAPI (API + automations)
  host/               # React/Vite (catálogo + UI)
  docs-site/          # Docusaurus (portal dev)
catalog/
  catalog.dev.json    # Catálogo de blocos e categorias
infra/
  docker-compose.dev.yml  # bff, host, docs, postgres
README.md
```

---

## 🚀 Quickstart (dev)

Pré-requisitos: **Docker** e **Docker Compose**, **Node 20+** (opcional local), **Python 3.11** (opcional local).

```bash
# 1) Subir o stack de desenvolvimento
cd infra
docker compose -f docker-compose.dev.yml up -d --build
```

URLs:

* **Host (UI)**: [http://localhost:5173/](http://localhost:5173/)
* **Docs de Dev** (via Host): [http://localhost:5173/devdocs/](http://localhost:5173/devdocs/)
  (direto no container: [http://localhost:9000/devdocs/](http://localhost:9000/devdocs/))
* **BFF API**: [http://localhost:8000/](http://localhost:8000/)

  * OpenAPI (JSON): `/api/openapi.json`
  * Saúde/ping: (conforme implementado)

Primeiro login (mock, em dev): consulte as credenciais de teste ou crie via `AUTH_MODE=mock`.

---

## 🔐 Autenticação e RBAC

* **Login**: `POST /api/auth/login` com `{ identifier, password }`.
* **Sessão atual**: `GET /api/me`.
* **RBAC (ANY-of)**: blocos/categorias podem exigir `requiredRoles` — basta **uma** combinar para liberar.
  Exemplo no catálogo:

  ```json
  { "requiredRoles": ["compras", "ferias"] }
  ```

---

## 🗂️ Catálogo (blocos e categorias)

* Servido pelo BFF (proxyado pelo Host).
* Arquivo de referência (dev): `catalog/catalog.dev.json`.
* Cada bloco descreve UI/rotas/roles, ex.:

  ```json
  {
    "categoryId": "compras",
    "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" },
    "routes": ["/automations/dfd"],
    "requiredRoles": ["compras"],
    "description": "DFD - Demonstração de Fluxo de Despesa"
  }
  ```

---

## ⚙️ Variáveis de ambiente (principais)

**BFF** (`infra/docker-compose.dev.yml` → serviço `bff`):

* `ENV=dev`, `AUTH_MODE=mock`, `SESSION_SECRET`,
  `CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`
* `CATALOG_FILE=/catalog/catalog.dev.json`
* Rate limit de login (dev): `AUTH_RATE_LIMIT_*`
* `LOG_LEVEL=INFO`

**Host** (`host`):

* `VITE_CATALOG_URL=/catalog/dev`
* `VITE_API_BASE=/api`
* `VITE_ENABLE_SELF_REGISTER=false`

**Docs** (`docs`):

* Docusaurus v3 servindo em `http://docs:8000` e proxyado pelo Host em `/devdocs`.

---

## 🧪 Testes rápidos (cURL)

Login (mock):

```bash
curl -i -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"dev@example.com","password":"dev"}'
```

Sessão atual:

```bash
curl -i http://localhost:8000/api/me
```

Form2JSON (exemplo de automação):

```bash
curl -i -X POST http://localhost:8000/api/automations/form2json/submit \
  -H 'Content-Type: application/json' \
  -d '{"payload":{"hello":"world"}}'
```

---

## 📚 Docs de Dev

O portal de documentação para devs fica em:

* **[http://localhost:5173/devdocs/](http://localhost:5173/devdocs/)** (via Host)
* **[http://localhost:9000/devdocs/](http://localhost:9000/devdocs/)** (direto no serviço de docs)

Geração de referências (opcional, rodar no host local):

```bash
# dentro de apps/docs-site
npm run gen:openapi   # baixa /api/openapi.json para static/openapi/bff.json
npm run gen:typedoc   # gera docs TS do host
# 'gen:py' requer pdoc instalado no seu Python local:
# pip install pdoc
npm run gen:py        # gera docs Python do BFF (Markdown)
```

---

## 🧩 Fluxo de desenvolvimento

1. **Automations** (BFF): cada automação fica em `apps/bff/app/automations/<slug>.py`
   Checklist recomendado por módulo:

   * `GET /schema` (opcional)
   * `GET /ui` (HTML/JS/CSS simples, sem bundler)
   * `POST /submit` (cria submission e dispara BackgroundTasks)
   * `GET /submissions`
   * `GET /submissions/{id}`
   * `POST /submissions/{id}/download`

2. **Catálogo**: adicione um bloco apontando para `ui.url` da automação; se precisar **roles**, use `requiredRoles`.

3. **Host**: não precisa buildar; lê o catálogo e renderiza os blocos (iframe) respeitando RBAC.

4. **Docs**: adicione/atualize páginas em `apps/docs-site/docs/**` e navegação em `sidebars.ts`.

---

## 🔎 Solução de problemas

* **Proxy `/devdocs` dá erro `EAI_AGAIN docs`**
  Verifique se o serviço `docs` está **UP** e com o nome **`docs`** no compose.
  Reinicie `host` após subir `docs`.

* **`pnpm not found` ou `pnpm ERR_*` no docs**
  Esta stack usa **npm** no container do `docs` para simplificar (sem pnpm).
  Se usar pnpm localmente, mantenha o lock coerente.

* **`npm ci` falhou (EUSAGE)**
  O `package-lock.json` diverge. Gere um lock novo:
  `rm -f apps/docs-site/package-lock.json && (cd apps/docs-site && npm install)`.

* **Login 404/401**
  Confira `AUTH_MODE=mock` no BFF (em dev) e tente `/api/auth/login` + `/api/me`.

---

## 🛡️ Segurança (resumo)

* **Sem segredos no repositório** — use variáveis de ambiente.
* **Cookies de sessão** e CORS restrito às origens do Host.
* **Erros claros** com códigos HTTP apropriados.

---

## 📍 Roadmap curto

* [ ] Completar checklist dos 6 endpoints em **todas** as automations
* [ ] Exemplos TypeDoc/pdoc integrados na doc
* [ ] Pagina **/api** a partir do OpenAPI (Docusaurus plugin)
* [ ] Testes de fumaça cURL automatizados

---

## 🤝 Contribuindo

* Abra PRs pequenos e focados.
* Mantenha Pydantic v2 com `ConfigDict(populate_by_name=True, extra="ignore")`.
* Inclua logs úteis (INFO/ERROR) e mensagens claras de erro.

---

## 📄 Licença

Defina a licença do projeto (ex.: MIT, Apache-2.0). Coloque o arquivo `LICENSE` na raiz.

---