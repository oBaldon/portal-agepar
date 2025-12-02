---
id: boas-práticas-para-novos-endpoints
title: "Boas práticas para novos endpoints"
sidebar_position: 4
---

Esta página é um “guia de bolso” para criar **novos endpoints** (principalmente
automations) no BFF do Portal AGEPAR, mantendo:

- DX consistente (mesmo jeito de tratar erros, payloads e responses),
- segurança previsível (auth/RBAC),
- observabilidade (logs + auditoria),
- compatibilidade com o Host (React) e com futuras UIs.

> Referências principais  
> - `apps/bff/app/automations/dfd.py`  
> - `apps/bff/app/automations/ferias.py`  
> - `apps/bff/app/automations/form2json.py`  
> - `apps/bff/app/auth/schemas.py`  
> - `apps/bff/app/auth/rbac.py`  
> - `apps/bff/app/main.py`  

---

## 1) Princípios gerais

Antes de pensar em código, vale fixar alguns princípios:

1. **Contratos de erro estáveis**
   - Usar sempre `{ code, message, details?, hint? }` para automations.
   - Reservar 422 para *validação*, 4xx para erros de uso, 5xx para erros internos.

2. **Normalizar entrada para evitar 422 “bobos”**
   - `populate_by_name=True`, `extra="ignore"`.
   - `alias` para compatibilizar `camelCase` vs `snake_case`.
   - Helpers de limpeza (`strip`, tipos) antes do `BaseModel`.

3. **Segurança por padrão**
   - Exigir sessão válida (`require_password_changed`).
   - Aplicar RBAC (`require_roles_any` / `require_roles_all`) quando fizer sentido.
   - Nunca confiar só no Host para proteger acesso (RBAC *também* no BFF).

4. **Logs e auditoria**
   - Logs em `INFO` para trilha feliz, `ERROR/exception` para erros.
   - Auditoria em `automation_audits` para ações de negócio (`submitted`, `failed`, etc.).

5. **Respostas “previsíveis” para o Host**
   - Estruturas similares a DFD/Férias: `items + limit + offset`, `sid + status` etc.
   - Nunca mudar forma da resposta sem versionar ou alinhar com o Host.

---

## 2) Estrutura base de um novo módulo de automação

Para uma nova automação (ex.: `exemplo`), o padrão é:

```python title="apps/bff/app/automations/exemplo.py (esqueleto)" showLineNumbers
from fastapi import APIRouter, Depends, Request, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Any, Dict, List
import logging

from app.auth.rbac import require_password_changed, require_roles_any
from app.db import (
    insert_submission,
    get_submission,
    list_submissions,
    add_audit,
)

logger = logging.getLogger("portal-agepar.automations.exemplo")

KIND = "exemplo"
VERSION = "1.0.0"
REQUIRED_ROLES = ("exemplo_user",)  # opcional

router = APIRouter(
    prefix="/api/automations/exemplo",
    tags=["automations", "exemplo"],
    dependencies=[Depends(require_password_changed)],
)

# --- contratos de entrada/saída ------------------------------------------------


class ExemploIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    campo_a: str = Field(..., min_length=1, max_length=100)
    campo_b: str = Field(..., alias="campoB", min_length=1, max_length=50)
    ano: str = Field(..., alias="ano", pattern=r"^\d{4}$")


def err_json(
    status: int,
    *,
    code: str,
    message: str,
    details: Any | None = None,
    hint: str | None = None,
):
    payload: Dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    if hint:
        payload["hint"] = hint
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status, content=payload)
````

Pontos importantes:

* `router.prefix` em `/api/automations/{slug}`.
* `dependencies=[Depends(require_password_changed)]` → exige sessão “válida” (sem `must_change_password`).
* `model_config` com `populate_by_name` + `extra="ignore"`.
* `err_json` local, mas com o mesmo formato de DFD/Férias (reutilizar se houver helper comum depois).

---

## 3) Contratos de entrada (DX de quem chama)

### 3.1. Use Pydantic com config padrão

Para qualquer payload mais estruturado:

```python title="Modelo de entrada recomendado" showLineNumbers
class MinhaAutomationIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    foo: str = Field(..., min_length=1, max_length=200)
    bar: str = Field(..., alias="barValue", min_length=1)
    ano: str = Field(..., alias="ano", pattern=r"^\d{4}$")
```

Regras:

* Campo exposto na UI usa `alias` (`barValue`, `ano` etc.).
* `extra="ignore"` para não estourar 422 se o front mandar algo a mais.
* Restrições (`min_length`, `pattern`) **documentam** regras de negócio.

### 3.2. Faça normalização leve antes do modelo

Evite 422 por causa de espaços ou tipos:

```python title="Normalização antes da validação" showLineNumbers
def _clean_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()

def normalize_body(raw: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(raw or {})
    data["foo"] = _clean_str(data.get("foo"))
    data["barValue"] = _clean_str(data.get("barValue"))
    ano = data.get("ano")
    if isinstance(ano, int):
        data["ano"] = f"{ano:04d}"
    elif isinstance(ano, str):
        data["ano"] = ano.strip()
    return data
```

Uso no endpoint:

```python title="Uso no POST /submit" showLineNumbers
@router.post("/submit")
def submit(body_raw: Dict[str, Any], user=Depends(require_roles_any(*REQUIRED_ROLES))):
    try:
        body = MinhaAutomationIn(**normalize_body(body_raw))
    except ValidationError as ve:
        # 422 legível
        return err_json(
            422,
            code="validation_error",
            message="Erro de validação nos campos.",
            details=ve.errors(),
        )

    # body válido → seguir fluxo
```

---

## 4) Contratos de saída (sucesso)

Recomendações:

1. **Submissões assíncronas** (como DFD/Férias):

   * resposta de `POST /submit`:

     ```json
     {
       "sid": "<uuid>",
       "status": "queued"
     }
     ```
   * downloads em `GET /submissions/{sid}/download?...`.

2. **Listagens**:

   * resposta sempre no formato:

     ```json
     {
       "items": [...],
       "limit": 50,
       "offset": 0
     }
     ```
   * usar `limit` e `offset` com `Query`:

     ```python
     limit: int = Query(default=50, ge=1, le=200)
     offset: int = Query(default=0, ge=0)
     ```

3. **Operações simples** (ex.: ações administrativas):

   * usar `{ "ok": true }` quando não precisar devolver dados,
   * ou `{ "ok": true, "id": "...", ... }` para criar recursos.

Exemplo de listagem:

```python title="Listagem padrão" showLineNumbers
@router.get("/submissions")
def list_my(
    user=Depends(require_roles_any(*REQUIRED_ROLES)),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    try:
        rows = list_submissions(kind=KIND, actor_cpf=user.get("cpf"), limit=limit, offset=offset)
    except Exception as e:
        logger.exception("list_submissions storage error")
        return err_json(
            500,
            code="storage_error",
            message="Falha ao consultar submissões.",
            details=str(e),
        )
    return {"items": rows, "limit": limit, "offset": offset}
```

---

## 5) Tratamento de erros (padrão 4xx/5xx)

### 5.1. Mapeamento sugerido (recap rápido)

* `422 validation_error` → problema de validação de campos (Pydantic / negócio).
* `400 bad_request` → parâmetros incoerentes (ex.: `fmt` inválido, falta `confirm`).
* `401 not authenticated` → use `HTTPException` global (já existe em `/api/me`).
* `403 forbidden` → usuário autenticado, mas sem permissão.
* `404 not_found` → SID/recurso não existe.
* `409`:

  * `not_ready`, `submission_in_progress`, `duplicate`, etc.
* `410 file_not_found` → arquivo antes existente, agora removido.
* `500 storage_error`, `download_error` → falhas de infra.

### 5.2. Sempre use `err_json` nas automations

Exemplos:

```python title="Erros típicos" showLineNumbers
# 400 – pedido incoerente
return err_json(
    400,
    code="bad_request",
    message="Formato de download inválido.",
    details={"allowed": ["pdf", "docx"], "fmt": fmt},
)

# 403 – permissão
return err_json(
    403,
    code="forbidden",
    message="Você não tem permissão para acessar esta submissão.",
)

# 409 – conflito de estado
return err_json(
    409,
    code="not_ready",
    message="Resultado ainda não está pronto.",
    details={"sid": sid, "status": row["status"]},
)

# 500 – infra
logger.exception("download error")
return err_json(
    500,
    code="download_error",
    message="Falha ao preparar o download.",
    details=str(e),
)
```

---

## 6) Segurança e RBAC nos endpoints

### 6.1. Sessão e troca de senha

Todos os routers de automations devem depender pelo menos de:

```python
dependencies=[Depends(require_password_changed)]
```

Isso garante:

* sessão válida,
* usuário não está com `must_change_password=True`.

### 6.2. RBAC (ANY-of) por automação

Se a automação não for “para todos”, use `require_roles_any`:

```python title="RBAC no router" showLineNumbers
REQUIRED_ROLES = ("compras", "pregoeiro")

router = APIRouter(
    prefix="/api/automations/meu_slug",
    tags=["automations", "meu_slug"],
    dependencies=[Depends(require_password_changed)],
)

@router.post("/submit")
def submit(body: MeuIn, user=Depends(require_roles_any(*REQUIRED_ROLES))):
    ...
```

No catálogo (Host), use o mesmo conjunto:

```jsonc title="Trecho de catalog.dev.json (exemplo)"
{
  "name": "meu_slug",
  "displayName": "Minha automação",
  "categoryId": "compras",
  "requiredRoles": ["compras", "pregoeiro"],
  "ui": { "type": "iframe", "url": "/api/automations/meu_slug/ui" },
  "routes": ["/automations/meu_slug"]
}
```

---

## 7) Logs e auditoria junto com as respostas

### 7.1. Logs mínimos

* Ao receber submissão: `INFO` com `sid`, `cpf`, campos principais.
* Ao processar: `INFO` no início e no final.
* Ao falhar: `logger.exception("mensagem curta")` com contexto.

### 7.2. Auditoria (`automation_audits`)

Para qualquer operação relevante:

```python title="Eventos de auditoria recomendados" showLineNumbers
add_audit(KIND, "submitted", user, {"sid": sid})
add_audit(KIND, "running", user, {"sid": sid})
add_audit(KIND, "completed", user, {"sid": sid})
add_audit(KIND, "failed", user, {"sid": sid, "error": str(exc)})
add_audit(KIND, "download", user, {"sid": sid, "fmt": fmt})
```

E lembrar:

```python
try:
    add_audit(...)
except Exception:
    logger.exception("audit failed (non-blocking)")
```

Falha em auditoria **não** deve derrubar a operação principal.

---

## 8) Exemplo completo: novo endpoint “/submit” com DX boa

```python title="Endpoint completo — POST /submit" showLineNumbers
@router.post("/submit")
def submit_exemplo(
    body_raw: Dict[str, Any],
    user=Depends(require_roles_any(*REQUIRED_ROLES)),
):
    # 1. Normalização
    data = normalize_body(body_raw)

    # 2. Validação
    try:
        body = ExemploIn(**data)
    except ValidationError as ve:
        logger.info("EXEMPLO validation_error errors=%s", ve.errors())
        return err_json(
            422,
            code="validation_error",
            message="Erro de validação nos campos.",
            details=ve.errors(),
        )

    # 3. Criação de submissão
    sid = str(uuid4())
    payload = body.model_dump(mode="json")
    try:
        logger.info(
            "EXEMPLO submit queued | sid=%s | cpf=%s",
            sid,
            user.get("cpf"),
        )
        insert_submission(
            {
                "id": sid,
                "kind": KIND,
                "version": VERSION,
                "actor_cpf": user.get("cpf"),
                "actor_nome": user.get("nome"),
                "actor_email": user.get("email"),
                "payload": payload,
                "status": "queued",
                "result": None,
                "error": None,
            }
        )
        add_audit(KIND, "submitted", user, {"sid": sid})
    except Exception as e:
        logger.exception("EXEMPLO insert_submission failed")
        return err_json(
            500,
            code="storage_error",
            message="Falha ao criar submissão.",
            details=str(e),
        )

    # 4. Resposta de sucesso
    return {"sid": sid, "status": "queued"}
```

---

## 9) Checklist final para novos endpoints

Antes de dar “PR pronto” em um novo endpoint, confira:

1. **Contratos**

   * [ ] Entrada tipada com `BaseModel` + `ConfigDict(populate_by_name=True, extra="ignore")`.
   * [ ] `alias` correto para campos usados pela UI.
   * [ ] Normalização básica antes de validar.

2. **Erros**

   * [ ] Usa `err_json(...)` com `{code, message, details}` em automations.
   * [ ] Mapeia corretamente 400/401/403/404/409/410/422/500.
   * [ ] Não expõe stack trace em responses (apenas logs).

3. **Segurança**

   * [ ] Router depende de `require_password_changed`.
   * [ ] Endpoints sensíveis usam `require_roles_any`/`require_roles_all`.
   * [ ] RBAC na automação bate com `requiredRoles` no catálogo.

4. **Observabilidade**

   * [ ] Logs `INFO` na trilha feliz, `exception` em erros.
   * [ ] Auditoria em `automation_audits` (`add_audit`/`audit_log`) com `kind`, `action`, `meta`.

5. **DX do Host**

   * [ ] Respostas seguem padrões dos endpoints existentes (DFD/Férias).
   * [ ] Página/iframe da automação retorna erros no formato esperado.
   * [ ] (Opcional) Criado helper TS no Host para chamar o endpoint com tipos corretos.

---

> _Criado em 2025-12-02_