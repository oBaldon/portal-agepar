---
id: mapeamento-de-erros-400422
title: "Mapeamento de erros (400–422)"
sidebar_position: 6
---

Esta página padroniza **como o BFF (FastAPI)** devolve erros para o Host, diferenciando **422** (quebra de esquema/validação) de **400** (regra de negócio), além de **401/403/404/409**. Inclui **modelo de erro unificado**, **exception handlers** e **cURLs** de verificação.

> Referências: `apps/bff/app/main.py`, `apps/bff/app/automations/*.py`, `apps/bff/app/auth/*`

---

## 1) Modelo de erro unificado

Use um **envelope** consistente para todas as respostas de erro:

```python
# apps/bff/app/errors.py (sugestão)
from typing import Any

def err(message: str, code: int, details: Any | None = None) -> dict:
    return {"error": message, "code": code, "details": details}
````

**Formato padrão (JSON)**

```json
{ "error": "validation failed", "code": 422, "details": [/* opcional */] }
```

Benefícios:

* Corpo previsível no Host.
* Campo `details` pode carregar `errors()` do Pydantic/RequestValidationError.

---

## 2) Handlers globais

Padronize **422** e **HTTPException** no `main.py`:

```python
# apps/bff/app/main.py (trechos)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from .errors import err

app = FastAPI(title="Portal AGEPAR BFF")

@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError):
    # 422 para erros de validação (body/query/path)
    return JSONResponse(status_code=422, content=err("validation failed", 422, exc.errors()))

@app.exception_handler(StarletteHTTPException)
async def _http_handler(request: Request, exc: StarletteHTTPException):
    # Se o detail já estiver no formato do projeto, use-o; senão, normalize
    if isinstance(exc.detail, dict) and "error" in exc.detail and "code" in exc.detail:
        payload = exc.detail
    else:
        payload = err(str(exc.detail), exc.status_code)
    return JSONResponse(status_code=exc.status_code, content=payload)
```

> **Dica**: continue levantando `HTTPException` normalmente nos handlers; o **exception handler** garante o envelope.

---

## 3) 422 vs 400 (quando usar cada um)

* **422 Unprocessable Entity**
  Erros de **esquema/validação** (tipo, formato, campo obrigatório ausente). É gerado automaticamente quando o handler recebe um **modelo Pydantic** e o payload está inválido.

* **400 Bad Request**
  **Regras de negócio** fora do esquema (ex.: data fim < data início, duplicidade de campo lógico, etc.).

Exemplo de **400**:

```python
from fastapi import APIRouter, HTTPException
from .errors import err

router = APIRouter()

@router.post("/form2json/submit")
def submit(body: SubmitPayload):
    if body.date_start and body.amount and body.amount < 0:
        raise HTTPException(status_code=400, detail=err("amount must be positive", 400))
    # ...
    return {"ok": True}
```

---

## 4) 401 e 403 (sessão e RBAC)

Use dependências para centralizar **login obrigatório** e **checar roles**:

```python
from fastapi import Depends, HTTPException
from .auth.sessions import get_user_from_session
from .errors import err

def require_login(user = Depends(get_user_from_session)):
    if not user:
        raise HTTPException(status_code=401, detail=err("unauthorized", 401))
    return user

def require_roles(required: list[str]):
    def _dep(user = Depends(require_login)):
        roles = set(user.get("roles") or [])
        if required and roles.isdisjoint(required):
            raise HTTPException(status_code=403, detail=err("forbidden", 403))
        return user
    return _dep

# Uso no router:
# @router.get("/admin-only", dependencies=[Depends(require_roles(["admin"]))])
```

---

## 5) 404 e 409 (não encontrado e conflito)

* **404 Not Found**: recurso ausente (submission inexistente, slug inválido).
* **409 Conflict**: estado que impede a operação (duplicado, já processado, bloqueio de concorrência).

```python
from fastapi import HTTPException
from .errors import err

def ensure_submission_exists(s):
    if not s:
        raise HTTPException(404, err("submission not found", 404))

def prevent_duplicate(is_dup: bool):
    if is_dup:
        raise HTTPException(409, err("duplicate submission", 409))
```

---

## 6) Exemplos de respostas

**422 (validação)**

```json
{
  "error": "validation failed",
  "code": 422,
  "details": [
    {"loc": ["body", "fullName"], "msg": "Field required", "type": "missing"}
  ]
}
```

**400 (negócio)**

```json
{ "error": "amount must be positive", "code": 400 }
```

**401**

```json
{ "error": "unauthorized", "code": 401 }
```

**403**

```json
{ "error": "forbidden", "code": 403 }
```

**404**

```json
{ "error": "submission not found", "code": 404 }
```

**409**

```json
{ "error": "duplicate submission", "code": 409 }
```

---

## 7) cURLs de diagnóstico

```bash
# 422: faltando campo obrigatório
curl -s -X POST http://localhost:8000/api/automations/form2json/submit \
  -H "Content-Type: application/json" -d '{}' | jq .

# 400: regra de negócio
curl -s -X POST http://localhost:8000/api/automations/form2json/submit \
  -H "Content-Type: application/json" \
  -d '{"fullName":"Alice","amount":"-1"}' | jq .

# 401: sem sessão
curl -s http://localhost:8000/api/me | jq .

# 403: sem role exigida (após login não-admin)
curl -s http://localhost:8000/api/automations/dfd/submissions \
  -H "X-Debug-Require-Role: admin" | jq .

# 404: resource inexistente
curl -s http://localhost:8000/api/automations/form2json/submissions/nope | jq .

# 409: conflito (exemplo)
curl -s -X POST http://localhost:8000/api/automations/form2json/submit \
  -H "Content-Type: application/json" \
  -d '{"fullName":"Alice","email":"a@x.com","_duplicate":true}' | jq .
```

> Ajuste as rotas para o módulo real. Em dev via Host, troque `8000` por `5173`.

---

## 8) Logging com contexto

Logue **eventos de erro** com **contexto mínimo** (ids e metadados não sensíveis):

```python
import logging
logger = logging.getLogger("bff")

def log_error(event: str, **ctx):
    logger.error("%s %s", event, {k: v for k, v in ctx.items() if v is not None})

# Exemplo
try:
    ensure_submission_exists(None)
except Exception as e:
    log_error("submission_not_found", submission_id="nope", user_id="u123")
    raise
```

* **INFO** para caminho feliz (submission criada, download gerado).
* **ERROR** com chaves (`submission_id`, `user_id`) para correlação.

---

## 9) Checklist de implementação

* [ ] **Handlers globais** para `RequestValidationError` (422) e `HTTPException`.
* [ ] **Envelope** `{error, code, details}` em todos os erros.
* [ ] **401/403** via dependências `require_login` e `require_roles`.
* [ ] **404/409** para ausência e conflito.
* [ ] **Mensagens claras** e estáveis (evite mudar textos sem necessidade).
* [ ] **Logs** com contexto e sem dados sensíveis.

---

## 10) Boas práticas

* Evite devolver **stacktrace** ao cliente.
* Seja **determinístico**: a mesma causa → mesma mensagem/código.
* Documente os erros no **OpenAPI** quando fizer sentido (descrição por rota).
* Testes de integração devem cobrir **erro feliz** (422) e **erro de negócio** (400) para cada rota de entrada.

---

## Próximos passos

* **Pydantic v2**: normalização e aliases (evitar 422 “bobas”).
* **Sessões mock e RBAC**: 401/403 coerentes.
* **Automations**: aplicar o contrato de erros em `/submit`, `/download` etc.

---

> _Criado em 2025-11-18_