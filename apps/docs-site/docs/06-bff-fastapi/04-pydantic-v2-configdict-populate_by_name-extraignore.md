---
id: pydantic-v2-configdict-populate_by_name-extraignore
title: "Pydantic v2 (ConfigDict populate_by_name, extra=ignore)"
sidebar_position: 4
---

Esta página consolida os **padrões de validação** usados no BFF (FastAPI) com **Pydantic v2**, destacando `ConfigDict(populate_by_name=True, extra="ignore")`, **aliases**, **normalização** de campos para evitar `422`, e **boas práticas** de serialização e tratamento de erros.

> Referências no repo (exemplos recorrentes):  
> `apps/bff/app/automations/*.py`, `apps/bff/app/auth/routes.py`

---

## 1) Por que `populate_by_name` e `extra="ignore"`

- **`populate_by_name=True`**  
  Permite mapear nomes **camelCase do JSON** para **snake_case no Python** via `Field(alias="...")`.  
  Ex.: JSON `{ "categoryId": "compras" }` → modelo com `category_id: str = Field(alias="categoryId")`.

- **`extra="ignore"`**  
  Campos **desconhecidos** no JSON **não quebram** a validação (evita `422` por ruído / forward-compatibility).

---

## 2) Modelo canônico (exemplo)

```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal, Union

class UIIframe(BaseModel):
    type: Literal["iframe"]
    url: str

class UILink(BaseModel):
    type: Literal["link"]
    href: str

CatalogBlockUI = Union[UIIframe, UILink]

class CatalogBlock(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    category_id: str = Field(alias="categoryId", min_length=1)
    ui: CatalogBlockUI
    description: Optional[str] = None
    navigation: Optional[list[str]] = None
    routes: Optional[list[str]] = None
    required_roles: Optional[list[str]] = Field(default=None, alias="requiredRoles")
    order: Optional[int] = None
    hidden: Optional[bool] = None
````

**Efeitos práticos**

* Recebe `{ "categoryId": "compras", "unknown": 123 }` **sem** falhar.
* Ao serializar, pode-se **emitir aliases** com `model_dump(by_alias=True)`.

---

## 3) Normalização para evitar `422` “bobas”

> Objetivo: **aceitar** variações inofensivas (espaços, maiúsculas) e **corrigir** antes da validação estrita.

### 3.1) `@field_validator` (v2)

```python
from pydantic import field_validator


```
```

class SubmitPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str = Field(min_length=1)
    email: str | None = None

    @field_validator("name")
    @classmethod
    def _trim_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        return v

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str | None) -> str | None:
        return v.strip().lower() if v else v
```

### 3.2) `@model_validator` (pós-processamento)

```python
from pydantic import model_validator

class SubmitPayload(BaseModel):
    # ... campos ...

    @model_validator(mode="after")
    def _post(self):
        # regras cruzadas (ex.: se email ausente, preencher com placeholder controlado)
        if self.email and "@" not in self.email:
            raise ValueError("email must contain @")
        return self
```

> Use **field validators** para normalização simples e **model validators** para regras cruzadas.

---

## 4) Uso em rotas FastAPI (padrão)

```python
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, ConfigDict, ValidationError

router = APIRouter()

class Body(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    full_name: str = Field(alias="fullName", min_length=1)
    email: str | None = None

@router.post("/form2json/submit")
def submit(body: Body, tasks: BackgroundTasks):
    try:
        # body já veio validado e normalizado pelos validators
        submission_id = "s_abc"  # persistir de verdade
        tasks.add_task(lambda: None)
        return {"id": submission_id, "status": "queued"}
    except ValidationError as ve:
        # (raro aqui, pois FastAPI já converte 422) — mantido por clareza
        raise HTTPException(status_code=422, detail=ve.errors()) from ve
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
```

**Dicas**

* Prefira receber modelos **tipados** no handler (FastAPI converte e valida automaticamente).
* Para **serializar** resposta com aliases do JSON: `model_dump(by_alias=True)`.

---

## 5) Serialização: `model_dump` e aliases

```python
obj = CatalogBlock(categoryId="compras", ui={"type":"iframe","url":"/x"})
# Serialização padrão (snake_case)
snake = obj.model_dump()
# Serialização com aliases (camelCase conforme contrato JSON)
camel = obj.model_dump(by_alias=True)
```

* Use `by_alias=True` quando a **API externa**/front **espera camelCase**.
* No OpenAPI, defina **`alias`** nos `Field` para refletir o contrato.

---

## 6) Tratamento de erros (mapa objetivo)

* **422 Unprocessable Entity (automático)**: erros de esquema/validação → FastAPI gera corpo detalhado (`loc`, `msg`, `type`).
* **400 Bad Request**: regras de negócio simples (inconsistência fora do esquema).
* **401/403**: sessão/RBAC (ver páginas de sessões).
* **404/409**: recurso não existe / estado inválido.

**Resposta amigável (sugestão)**

```python
from fastapi import Request
from fastapi.responses import JSONResponse

def format_error(message: str, code: int):
    return {"error": message, "code": code}

@router.get("/example")
def example():
    raise HTTPException(status_code=400, detail=format_error("bad payload", 400))
```

---

## 7) Tipos úteis na prática (v2)

* **`Annotated`** com constraints:

  ```python
  from typing import Annotated
  from pydantic import StringConstraints

  NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
  ```
* **`HttpUrl` / `AnyUrl`** para links.
* **`conlist`, `conint`** (v2 usa `typing` + `Annotated`, mas helpers ainda funcionam).

---

## 8) Testes rápidos (pytest)

```python
# tests/test_submit_payload.py
from pydantic import ValidationError
from app.automations.form2json import Body

def test_normalize_and_validate():
    b = Body(fullName="  Alice  ", email="  A@Example.com ")
    assert b.full_name == "Alice"
    assert b.email == "a@example.com"

def test_empty_name_fails():
    try:
        Body(fullName="  ")
    except ValidationError as e:
        assert any(err["loc"][-1] in ("fullName", "full_name") for err in e.errors())
```

---

## 9) Problemas comuns

* **422 por campo extra inesperado** → faltou `extra="ignore"`.
* **Alias não funciona** → verifique `Field(alias="...")` **e** `populate_by_name=True`.
* **Saída em snake_case quando front espera camelCase** → use `model_dump(by_alias=True)`.
* **Normalização ausente** → acrescente `@field_validator` (trim/lower etc.).

---

## 10) Checklist de implementação

* [ ] `ConfigDict(populate_by_name=True, extra="ignore")` em **todos** os modelos de entrada.
* [ ] `Field(alias="...")` para campos camelCase vindos do JSON.
* [ ] Validadores (`@field_validator` / `@model_validator`) para **normalização**.
* [ ] Uso de `model_dump(by_alias=True)` onde o contrato pede camelCase.
* [ ] Mapa claro de erros (`400/401/403/404/409/422`) com mensagens úteis.

---

## Próximos passos

* **[Rotas gerais /api e /api/automations/:kind/...](./rotas-gerais-api-e-api-automations-kind)**
* **Tratamento de erros e logging (padrões do projeto)**
* **Modelos por automação** (DFD, Férias, etc.) seguindo o mesmo padrão

---

> _Criado em 2025-11-18_