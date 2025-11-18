---
id: logging-info-error
title: "Logging (INFO/ERROR)"
sidebar_position: 7
---

Esta página define **padrões de logging** para o BFF (FastAPI): como **configurar** os loggers, **o que** logar em **INFO** e **ERROR**, como incluir **contexto** (request id, usuário, submission) e **como inspecionar** os logs em dev e produção.

> Referências no repo:  
> `apps/bff/app/main.py`, `apps/bff/app/automations/*.py`, `apps/bff/app/auth/*`, `apps/bff/app/db.py`

---

## 1) Objetivos e níveis

- **INFO**: eventos do caminho feliz e marcos do fluxo  
  exemplo: app start, login ok, submission criada, download gerado.
- **ERROR**: falhas tratadas ou não, sempre com **contexto mínimo**  
  exemplo: validação de negócio, exceções internas, 5xx.
- **Sem PII**: evite dados sensíveis no texto do log. Logue **ids** e contagens.

```mermaid
flowchart LR
  Client --> BFF
  BFF -->|info,error| Logger
  Logger --> Stdout
  Logger --> Forwarder
````

---

## 2) Configuração base de logging (main.py)

Use `dictConfig` para padronizar formato e níveis. Produza para **stdout**.

```python
# apps/bff/app/main.py (trecho)
import logging
from logging.config import dictConfig

def setup_logging(level: str = "INFO"):
    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "plain": {
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s"
            }
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "formatter": "plain",
                "stream": "ext://sys.stdout",
            }
        },
        "root": {"level": level, "handlers": ["stdout"]},
        "loggers": {
            "uvicorn": {"level": level},
            "uvicorn.error": {"level": level},
            "uvicorn.access": {"level": level},
            "bff": {"level": level},  # logger da aplicação
        },
    })

setup_logging()
logger = logging.getLogger("bff")
logger.info("bff_startup")
```

> Em produção você pode alternar a formatação para JSON. Ver seção 8.

---

## 3) Contexto padronizado

Crie helpers para **INFO** e **ERROR** que aceitam contexto em kwargs.
O contexto aparece no log como string de dicionário.

```python
# apps/bff/app/logging_utils.py
import logging
from typing import Any

_log = logging.getLogger("bff")

def info(event: str, **ctx: Any) -> None:
    if ctx:
        _log.info("%s %s", event, {k: v for k, v in ctx.items() if v is not None})
    else:
        _log.info("%s", event)

def error(event: str, **ctx: Any) -> None:
    if ctx:
        _log.error("%s %s", event, {k: v for k, v in ctx.items() if v is not None})
    else:
        _log.error("%s", event)
```

**Convenções de chaves**

* `req_id`, `user_id`, `submission_id`
* `path`, `method`, `status`
* `duration_ms`, `size_bytes`

---

## 4) Correlation id por requisição

Middleware simples para gerar `request.state.req_id` e incluir nos logs.

```python
# apps/bff/app/main.py (trecho)
import uuid
from time import perf_counter
from fastapi import FastAPI, Request
from fastapi.responses import Response

app = FastAPI(title="Portal AGEPAR BFF")

@app.middleware("http")
async def request_logger(request: Request, call_next):
    req_id = uuid.uuid4().hex[:12]
    request.state.req_id = req_id
    start = perf_counter()
    try:
        response: Response = await call_next(request)
        duration = int((perf_counter() - start) * 1000)
        logging.getLogger("bff").info(
            "http_access %s",
            {
                "req_id": req_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration,
            },
        )
        return response
    except Exception as e:
        duration = int((perf_counter() - start) * 1000)
        logging.getLogger("bff").error(
            "http_error %s",
            {
                "req_id": req_id,
                "method": request.method,
                "path": request.url.path,
                "error": type(e).__name__,
                "duration_ms": duration,
            },
        )
        raise
```

---

## 5) Exemplos de uso nos handlers

### 5.1) Login ok e falha

```python
# apps/bff/app/auth/routes.py (trecho)
from fastapi import APIRouter, Response, Request, HTTPException
from .sessions import create_session
from ..logging_utils import info, error

router = APIRouter()

@router.post("/login")
def login(body: dict, request: Request, resp: Response):
    username = (body.get("username") or "").strip().lower()
    if not username:
        error("auth_login_invalid", req_id=request.state.req_id)
        raise HTTPException(400, {"error": "invalid credentials", "code": 400})
    user = {"id": username, "name": username.title(), "roles": ["viewer"]}
    sid = create_session(user)
    resp.set_cookie("session", sid, httponly=True, samesite="lax", path="/")
    info("auth_login_ok", req_id=request.state.req_id, user_id=user["id"])
    return user
```

### 5.2) Submission criada e erro de negócio

```python
# apps/bff/app/automations/form2json.py (trecho)
from fastapi import APIRouter, Request, HTTPException
from ..logging_utils import info, error

router = APIRouter()

@router.post("/form2json/submit")
def submit(body: dict, request: Request):
    if body.get("amount", 0) < 0:
        error("submit_business_error", req_id=request.state.req_id, reason="negative_amount")
        raise HTTPException(400, {"error": "amount must be positive", "code": 400})
    submission_id = "s_123"
    info("submit_created", req_id=request.state.req_id, submission_id=submission_id)
    return {"id": submission_id, "status": "queued"}
```

---

## 6) Uvicorn em dev e Compose

### 6.1) Dev local

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --log-level info
```

### 6.2) Docker Compose

No serviço do BFF, prefira logar em stdout e seguir o nível por env var.

```yaml
# docker-compose.yml (exemplo de serviço)
services:
  bff:
    build:
      context: apps/bff
      dockerfile: Dockerfile.dev
    environment:
      LOG_LEVEL: INFO
    ports:
      - "8000:8000"
    command: >
      sh -c "uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level ${LOG_LEVEL:-info}"
```

Inspecione:

```bash
docker compose logs -f bff
```

---

## 7) Campos e conteúdo: o que logar

**Sempre**

* Evento curto: `auth_login_ok`, `submit_created`, `download_generated`.
* Contexto: `req_id`, ids sintéticos (nunca tokens), tamanhos/tempos.

**Nunca**

* Senhas, tokens, cookies, documentos inteiros, dados pessoais sensíveis.
* Trazer payloads brutos em ERROR. Prefira um **hash** ou **resumo**.

---

## 8) Opcional: logs estruturados JSON

Para enviar a ferramentas tipo Loki/ELK, troque o formatter por JSON.

```python
# main.py (variante resumida)
"formatters": {
  "json": {
    "format": "{\"ts\":\"%(asctime)s\",\"level\":\"%(levelname)s\",\"logger\":\"%(name)s\",\"msg\":\"%(message)s\"}"
  }
},
"handlers": {
  "stdout": {"class": "logging.StreamHandler", "formatter": "json", "stream": "ext://sys.stdout"}
},
"root": {"level": level, "handlers": ["stdout"]}
```

> Em produção, configure o coletor do cluster para ler do stdout do container.

---

## 9) Testes manuais de logging

```bash
# 1) Subir o BFF
docker compose up --build -d bff
docker compose logs -f bff

# 2) Gerar logs INFO/ERROR
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" -d '{"username":"alice","password":"x"}' >/dev/null

curl -s -X POST http://localhost:8000/api/automations/form2json/submit \
  -H "Content-Type: application/json" -d '{"amount":-1}' >/dev/null
```

Você deve ver linhas como:

```
INFO bff auth_login_ok {'req_id': 'abcd1234ef56', 'user_id': 'alice'}
ERROR bff submit_business_error {'req_id': 'abcd1234ef56', 'reason': 'negative_amount'}
```

---

## 10) Troubleshooting

* **Nada aparece nos logs**

  * Confirme `dictConfig` foi chamado e o nível está em `INFO`.
  * Confira o `command` do Uvicorn e o nível de `uvicorn.access`.

* **Logs duplicados**

  * `disable_existing_loggers: False` e cuidado com `basicConfig` duplicado.
  * Evite `print`; use sempre `logging`.

* **Informação demais**

  * Reduza nível de `uvicorn.access` ou **amostre** logs de acesso.

* **Fuga de PII**

  * Revise mensagens, substitua valores por ids e contagens.

---

## Próximos passos

* Integrar **exception handlers** padronizados com envelope de erro.
* Enviar logs para **stack observability** (ELK, Loki, Cloud).
* Adicionar **correlação** com ids de submissão nas automations.

---

> _Criado em 2025-11-18_