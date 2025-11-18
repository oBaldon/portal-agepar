---
id: checklist-para-criar-nova-automação
title: "Checklist para criar nova automação"
sidebar_position: 6
---

Esta página traz um **passo a passo objetivo** para criar uma nova automação no BFF seguindo o padrão do projeto (router isolado + UI HTML para `<iframe>` + persistência de submissions/audits + RBAC e erros padronizados).

> Referências:  
> `apps/bff/app/automations/*.py`, `apps/bff/app/automations/templates/*/ui.html`, `apps/bff/app/db.py`, `apps/bff/app/main.py`  
> Relacionado:  
> **[Local: apps/bff/app/automations/`{slug}`.py](./local-apps-bff-app-automations-slugpy)** ·
> **[GET /schema (opcional), GET /ui](./get-schema-opcional-get-ui)** ·
> **[POST /submit (BackgroundTasks)](./post-submit-backgroundtasks)** ·
> **[GET /submissions, GET /submissions/`{id}`](./get-submissions-get-submissions-id)** ·
> **[POST /submissions/`{id}`/download](./post-submissions-id-download)**

---

## 1) Estrutura de arquivos

- [ ] Criar o módulo: `apps/bff/app/automations/<slug>.py`  
- [ ] Criar a UI: `apps/bff/app/automations/templates/<slug>/ui.html` (HTML/JS/CSS simples, sem build)  
- [ ] (Opcional) `history.html` ou outros templates auxiliares

```text
apps/bff/app/automations/
├─ <slug>.py
└─ templates/
   └─ <slug>/
      └─ ui.html
````

---

## 2) Endpoints obrigatórios do módulo

* [ ] `GET /api/automations/<slug>/schema` *(opcional, mas recomendado)*
* [ ] `GET /api/automations/<slug>/ui` (HTML para `<iframe>`)
* [ ] `POST /api/automations/<slug>/submit` (cria submission + `BackgroundTasks`)
* [ ] `GET /api/automations/<slug>/submissions`
* [ ] `GET /api/automations/<slug>/submissions/<id>`
* [ ] `POST /api/automations/<slug>/submissions/<id>/download`

> Use **Pydantic v2** com `ConfigDict(populate_by_name=True, extra="ignore")` e **validadores** para normalização (evitar `422` “bobas”).

---

## 3) Registro no app (BFF)

* [ ] Importar e registrar o router no `apps/bff/app/main.py`:

```python
# apps/bff/app/main.py (trecho)
from .automations.<slug> import router as <slug>_router
app.include_router(<slug>_router, prefix="/api/automations", tags=["automations"])
```

* [ ] Confirmar **CORS** com `allow_credentials=True` e origens do Host (`http://localhost:5173`, `http://host:5173`).

---

## 4) Persistência e auditoria

* [ ] Usar funções do `db.py` (ou equivalentes) para:

  * criar submission: `create_submission(kind, submission_id, payload, status="queued")`
  * mudar estado: `set_submission_status(id, "processing"|"done"|"failed", result?, error?)`
  * auditar eventos: `add_audit(kind, submission_id, event, meta?)`

**Estados canônicos**:

```
queued -> processing -> done
                  \-> failed
```

---

## 5) UI para `<iframe>`

* [ ] Implementar `GET /ui` retornando **HTML válido** (via `HTMLResponse` lendo `templates/<slug>/ui.html`).
* [ ] As chamadas da UI ao BFF devem usar `credentials: "include"` (cookies).
* [ ] Evitar cabeçalhos que **bloqueiem** embedding (`X-Frame-Options: DENY`).
* [ ] Simplicidade: HTML/JS/CSS direto, sem bundlers.

---

## 6) RBAC e sessão

* [ ] Se a automação exigir login/roles:

  * **Login**: usar sessão mock existente (`/api/auth/login`, `/api/me`).
  * **RBAC**: checar roles (ANY-of) nas rotas sensíveis (ex.: `submit`/`download`).
* [ ] Em erros de permissão, devolver `401/403` com envelope `{ "error": "...", "code": ... }`.

---

## 7) Mapeamento de erros e mensagens

* [ ] **422**: erros de validação (automático pelo FastAPI/Pydantic).
* [ ] **400**: regra de negócio (ex.: combinação inválida).
* [ ] **404**: submission ou artefato inexistente.
* [ ] **409**: conflito (ex.: não finalizado para download, duplicado).
* [ ] Padronizar corpo de erro: `{ "error": "msg", "code": 4xx, "details": [...] }`.

---

## 8) Logging (INFO/ERROR)

* [ ] **INFO**: `submit_created`, `processing`, `done`, `download_ok` (com `submission_id`).
* [ ] **ERROR**: falhas com contexto mínimo (sem PII).
* [ ] Middleware de **request id** ativo para correlação (quando disponível).

---

## 9) Integração no Catálogo

* [ ] Adicionar **bloco** em `catalog.dev.json` apontando para a UI:

```json
{
  "categoryId": "compras",
  "ui": { "type": "iframe", "url": "/api/automations/<slug>/ui" },
  "description": "Descrição da automação",
  "requiredRoles": ["editor"]  // opcional
}
```

> O Host exibirá a **categoria** se houver **ao menos um bloco visível** (RBAC/hidden aplicados) e **preservará a ordem** do catálogo.

---

## 10) Testes rápidos (cURL)

```bash
# UI (HTML)
curl -i http://localhost:8000/api/automations/<slug>/ui

# Schema (opcional)
curl -s http://localhost:8000/api/automations/<slug>/schema | jq .

# Submit
curl -s -X POST http://localhost:8000/api/automations/<slug>/submit \
  -H "Content-Type: application/json" \
  -d '{"fullName":"Alice"}' | jq .

# Lista
curl -s http://localhost:8000/api/automations/<slug>/submissions | jq .

# Detalhe
curl -s http://localhost:8000/api/automations/<slug>/submissions/s_123 | jq .

# Download
curl -s -X POST -OJ http://localhost:8000/api/automations/<slug>/submissions/s_123/download
```

> Via Host, troque `8000` por `5173`.

---

## 11) Qualidade e segurança

* [ ] Validar e **normalizar** campos de entrada (trim, case, números, datas).
* [ ] Sanitizar erros antes de gravar em `error` (sem dados sensíveis).
* [ ] Evitar **path traversal** no download; normalizar caminhos.
* [ ] Definir `Content-Type`/`Content-Disposition` corretos; usar `no-store` quando necessário.

---

## 12) Prontos para produção (quando aplicável)

* [ ] Idempotência no `submit` (dedupe por hash de payload + usuário).
* [ ] Retenção/limpeza de artefatos (TTL).
* [ ] Observabilidade: métricas de tempo de fila/processamento.
* [ ] Fila real (RQ/Celery) para cargas pesadas (em vez de `BackgroundTasks`).

---

## 13) Próximos passos

* **[Local: apps/bff/app/automations/`{slug}`.py](./local-apps-bff-app-automations-slugpy)**
* **[GET /schema (opcional), GET /ui](./get-schema-opcional-get-ui)**
* **[POST /submit (BackgroundTasks)](./post-submit-backgroundtasks)**
* **[GET /submissions, GET /submissions/`{id}`](./get-submissions-get-submissions-id)**
* **[POST /submissions/`{id}`/download](./post-submissions-id-download)**

---

> _Criado em 2025-11-18_