---
id: rotas-gerais-api-e-api-automations-kind
title: "Rotas gerais /api e /api/automations/:kind/..."
sidebar_position: 3
---

Esta página documenta as **rotas públicas do BFF (FastAPI)** sob **`/api`** e o **padrão de rotas** das automations sob **`/api/automations/:kind/...`**. Inclui exemplos de implementação, cURLs e respostas esperadas.

> Referências no repo:  
> `apps/bff/app/main.py`, `apps/bff/app/automations/*.py`, `apps/bff/app/db.py`, `apps/bff/app/auth/*`

---

## 1) Mapa das rotas (visão geral)

**Rotas gerais**
- `GET  /api` → ping/saúde simples (opcional).
- `GET  /api/docs` → atalho para documentação (pode devolver link do OpenAPI).
- `GET  /api/me` → usuário atual (mock; depende de sessão).
- `POST /api/auth/login` / `POST /api/auth/logout` → sessão mock (ver seção de Sessões).

**Automations (`:kind`) – contrato base**
- `GET  /api/automations/:kind/schema` *(opcional)* → esquema de entrada.
- `GET  /api/automations/:kind/ui` → página HTML embutível (iframe).
- `POST /api/automations/:kind/submit` → cria submission e inicia processamento.
- `GET  /api/automations/:kind/submissions` → lista.
- `GET  /api/automations/:kind/submissions/:id` → detalhe.
- `POST /api/automations/:kind/submissions/:id/download` → gera/baixa artefato.

```mermaid
flowchart LR
  Host[Host React] -->|/api| BFF[FastAPI]
  Host -->|/api/automations/*| Auto[Automation routers]
  Auto --> DB[Submissions Audits]
  Auto --> UI[HTML UI]
````

---

## 2) Montagem de routers (FastAPI)

```python
# apps/bff/app/main.py (trechos)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db import init_db
from .auth.routes import router as auth_router

# automations
from .automations.form2json import router as form2json
from .automations.dfd import router as dfd
from .automations.ferias import router as ferias
# ...demais módulos

app = FastAPI(title="Portal AGEPAR BFF")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://host:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# rotas gerais
@app.get("/api")
def api_root():
    return {"ok": True}

@app.get("/api/docs")
def docs_hint():
    return {"openapi": "/openapi.json"}

# sessão/auth mock
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

# automations
app.include_router(form2json, prefix="/api/automations", tags=["automations"])
app.include_router(dfd,        prefix="/api/automations", tags=["automations"])
app.include_router(ferias,     prefix="/api/automations", tags=["automations"])
# ...

@app.on_event("startup")
def _startup():
    init_db()
```

---

## 3) Contrato por automation (roteador típico)

Cada arquivo em `app/automations/:kind.py` expõe um `APIRouter` com o **mesmo conjunto de rotas**, mudando apenas o **slug**.

```python
# apps/bff/app/automations/form2json.py (exemplo resumido)
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()

class SubmitBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    name: str = Field(min_length=1)
    email: str | None = None

@router.get("/form2json/schema")
def schema():
    return {"fields": {"name": "string", "email": "string?"}}

@router.get("/form2json/ui")
def ui():
    # retorna HTML (string) ou TemplateResponse
    return "<!doctype html><html><body>Form2JSON UI</body></html>"

@router.post("/form2json/submit")
def submit(body: SubmitBody, tasks: BackgroundTasks):
    # cria submission, agenda processamento
    submission_id = "s_123"  # persistir de verdade em db.py
    tasks.add_task(lambda: None)
    return {"id": submission_id, "status": "queued"}

@router.get("/form2json/submissions")
def list_submissions():
    return {"items": []}

@router.get("/form2json/submissions/{id}")
def get_submission(id: str):
    if id != "s_123":
        raise HTTPException(status_code=404, detail="submission not found")
    return {"id": id, "status": "done", "result": {}}

@router.post("/form2json/submissions/{id}/download")
def download_submission(id: str):
    return {"ok": True, "file": f"/downloads/{id}.zip"}
```

> **Padrões Pydantic v2**: `ConfigDict(populate_by_name=True, extra="ignore")` e **normalização** de campos antes do processamento.

---

## 4) Exemplos de cURL

**Rotas gerais**

```bash
# saúde
curl -i http://localhost:8000/api

# docs hint / openapi
curl -s http://localhost:8000/api/docs | jq .
curl -s http://localhost:8000/openapi.json | jq '.info.title'
```

**Automation :kind (substitua pelo slug real)**

```bash
# UI HTML (para embutir no Host)
curl -i http://localhost:8000/api/automations/form2json/ui

# Schema (opcional)
curl -s http://localhost:8000/api/automations/form2json/schema | jq .

# Submit
curl -s -X POST http://localhost:8000/api/automations/form2json/submit \
  -H "Content-Type: application/json" \
  -d '{"name":"Alice","email":"alice@example.com"}' | jq .

# Lista
curl -s http://localhost:8000/api/automations/form2json/submissions | jq .

# Detalhe
curl -s http://localhost:8000/api/automations/form2json/submissions/s_123 | jq .

# Download
curl -s -X POST http://localhost:8000/api/automations/form2json/submissions/s_123/download | jq .
```

Via **Host (proxy Vite)** troque `8000` por `5173`.

---

## 5) Respostas e códigos de erro

* `200 OK` → sucesso.
* `201 Created` → quando criar recursos (opcional nas submissions).
* `400 Bad Request` → payload inconsistente (fora da validação de esquema).
* `401 Unauthorized` → sessão ausente/expirada (rotas que exigem login).
* `403 Forbidden` → RBAC falhou (roles insuficientes).
* `404 Not Found` → slug inválido, submission inexistente.
* `409 Conflict` → submissão duplicada/estado incompatível.
* `422 Unprocessable Entity` → falha de validação Pydantic.

**Dica**: padronize o corpo de erro `{ "error": "msg", "code": 422 }` para facilitar o front.

---

## 6) Observações de segurança e CORS

* Ative CORS com **ambas** as origens em dev Compose:
  `http://localhost:5173` **e** `http://host:5173`.
* Se usar **cookies de sessão**, mantenha `allow_credentials=True`.
* **Não** exponha segredos via rotas públicas.
* No `/ui`, garanta **conteúdo estático simples** e cabeçalhos adequados para embutir em `iframe` (evite `X-Frame-Options: DENY` quando for first-party).

---

## 7) Boas práticas de automations

* Cada automation é um **módulo isolado** (router + UI + validações).
* **Log**: INFO no caminho feliz; ERROR com contexto (`submission_id`, `user_id`).
* **DB**: registre em `submissions` e **audite** eventos (criação, processamento, download).
* **Timeouts**: processe pesado em **BackgroundTasks** ou fila (Celery/RQ) se necessário.

---

## 8) Checklist rápido

* [ ] Slug consistente (`/api/automations/:kind/...`).
* [ ] `GET /ui` responde HTML válido.
* [ ] Validação Pydantic v2 com `extra="ignore"`.
* [ ] Persistência mínima em `submissions` + `audits`.
* [ ] Erros mapeados com mensagens úteis.
* [ ] CORS alinhado com o Host.

---

## 9) Próximos passos

* **[Sessões mock: POST /api/auth/login, GET /api/me](./sessões-mock-post-api-auth-login-get-api-me)**
* **Pydantic v2: modelos e normalização**
* **Tratamento de erros e logging**

---

> _Criado em 2025-11-18_