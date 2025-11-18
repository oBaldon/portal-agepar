---
id: post-submit-backgroundtasks
title: "POST /submit (BackgroundTasks)"
sidebar_position: 3
---

Esta página define o **contrato de submissão** das automations e o uso de **`BackgroundTasks`** no FastAPI para processar o trabalho **assíncrono** após a resposta. Cobre **validação Pydantic v2**, **persistência** em `submissions`/`audits`, **estados**, **erros** e **cURLs**.

> Referências no repo:  
> `apps/bff/app/automations/*.py`, `apps/bff/app/db.py`, `apps/bff/app/main.py`

---

## 1) Fluxo resumido

1. **Recebe** `POST /api/automations/{slug}/submit` com JSON.  
2. **Valida** e **normaliza** (Pydantic v2, `extra="ignore"`, aliases).  
3. **Cria** uma `submission` com estado **queued** e audita o evento.  
4. **Agenda** um `BackgroundTasks` que faz o processamento real.  
5. **Responde** imediatamente com `202 Accepted` (ou `200 OK`) contendo `{ id, status }`.  
6. Cliente consulta **status** em `GET /api/automations/{slug}/submissions/{id}` e baixa o artefato em `POST /api/automations/{slug}/submissions/{id}/download`.

---

## 2) Modelo de entrada (exemplo)

```python
# apps/bff/app/automations/example.py (trecho)
from pydantic import BaseModel, Field, ConfigDict, field_validator

class SubmitBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    full_name: str = Field(alias="fullName", min_length=1)
    email: str | None = None

    @field_validator("full_name")
    @classmethod
    def _norm_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("nome vazio")
        return " ".join(p.capitalize() for p in v.split())
````

**Pontos-chave**

* `populate_by_name=True` + `alias` → aceita camelCase do JSON.
* `extra="ignore"` → campos desconhecidos não causam 422.
* Validadores para **evitar 422 “bobas”** (trim/case).

---

## 3) Endpoint `POST /submit` (padrão)

```python
# apps/bff/app/automations/example.py (trecho)
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status
from uuid import uuid4
from ..errors import err
from ..logging_utils import info, error
from ..db import create_submission, set_submission_status, add_audit  # exemplos

router = APIRouter()
SLUG = "example"

@router.post(f"/{SLUG}/submit", status_code=status.HTTP_202_ACCEPTED)
def submit(body: SubmitBody, tasks: BackgroundTasks, request: Request, response: Response):
    payload = body.model_dump(by_alias=True)
    sid = f"s_{uuid4().hex[:10]}"

    create_submission(kind=SLUG, submission_id=sid, payload=payload, status="queued")
    add_audit(kind=SLUG, submission_id=sid, event="queued")

    response.headers["Location"] = f"/api/automations/{SLUG}/submissions/{sid}"
    tasks.add_task(_process_submission, sid)

    info("submit_created", submission_id=sid)
    return {"id": sid, "status": "queued"}
```

---

## 4) Worker de processamento (executa em background)

```python
# apps/bff/app/automations/example.py (trecho)
from time import sleep

def _process_submission(sid: str):
    try:
        set_submission_status(sid, "processing")
        add_audit(kind=SLUG, submission_id=sid, event="processing")

        # trabalho “real”
        sleep(0.2)
        result = {"artifact": f"/downloads/{sid}.pdf"}

        set_submission_status(sid, "done", result=result)
        add_audit(kind=SLUG, submission_id=sid, event="done", meta=result)
        info("submit_done", submission_id=sid)
    except Exception as e:
        set_submission_status(sid, "failed", error=str(e))
        add_audit(kind=SLUG, submission_id=sid, event="failed", meta={"error": type(e).__name__})
        error("submit_failed", submission_id=sid, exc=type(e).__name__)
```

**Observações**

* `BackgroundTasks` roda **depois** da resposta; registre logs e audite.

---

## 5) Estados e respostas (convenção)

Use estes **estados canônicos**:

```
queued -> processing -> done
                  \-> failed
```

**Resposta do submit**

```json
{ "id": "s_abcdef1234", "status": "queued" }
```

**Status (`GET /api/automations/{slug}/submissions/{id}`)**

```json
{ "id": "s_abcdef1234", "status": "processing", "result": null, "error": null }
```

**Finalizado**

```json
{ "id": "s_abcdef1234", "status": "done", "result": { "artifact": "/downloads/s_abcdef1234.pdf" } }
```

---

## 6) Erros e códigos de retorno

* **422** → quebra de **validação** (Pydantic).
* **400** → **regra de negócio**.
* **409** → **duplicado** (idempotência).
* **404** → `GET /api/automations/{slug}/submissions/{id}` inexistente.

Exemplo 400:

```python
if some_business_rule_fails:
    raise HTTPException(400, err("invalid state for submit", 400))
```

---

## 7) Idempotência (opcional)

* Gere um **dedupe key** (hash do payload + user id).
* Se houver submission recente igual → retorne **409** com o `id` existente ou `200` apontando a mesma.

---

## 8) Persistência e auditoria (API sugerida)

```python
# create_submission(kind, submission_id, payload, status)
# set_submission_status(submission_id, status, result=None, error=None)
# add_audit(kind, submission_id, event, meta: dict | None = None)
```

---

## 9) cURLs úteis

```bash
# Submit
curl -s -X POST http://localhost:8000/api/automations/example/submit \
  -H "Content-Type: application/json" \
  -d '{"fullName":"Alice","email":"a@example.com"}' | jq .

# Status
curl -s http://localhost:8000/api/automations/example/submissions/s_abcdef1234 | jq .

# Via Host (proxy Vite)
curl -s http://localhost:5173/api/automations/example/submissions/s_abcdef1234 | jq .
```

---

## 10) Boas práticas

* **Responda rápido** com `202 Accepted` e `Location`.
* **Logue** `submit_created` → `processing` → `done/failed`.
* **Fila real** (RQ/Celery) para CPU pesado.
* **Sanitize** erros antes de gravar em `error`.
* **RBAC** e **limites** (payload/rate).

---

## 11) Problemas comuns

* **Task não roda** → confirme `tasks.add_task` e ausência de `return` anterior.
* **Sessão some** no fetch do UI → `credentials: "include"` + CORS `allow_credentials=True`.
* **Arquivo ausente** no download → gere no worker e grave em `result.artifact`.
* **422 inesperado** → `extra="ignore"` + validadores.

---

## 12) Próximos passos

* **[GET /submissions e detalhes](./get-submissions-get-submissions-id)**
* **[POST /submissions/`{id}`/download](./post-submissions-id-download)**
* **Observabilidade**: métricas de fila/tempo de processamento

---

> _Criado em 2025-11-18_