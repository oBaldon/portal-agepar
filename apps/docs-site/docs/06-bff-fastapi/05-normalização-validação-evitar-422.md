---
id: normalização-validação-evitar-422
title: "Normalização/validação (evitar 422)"
sidebar_position: 5
---

Esta página reúne **padrões práticos** para **aceitar entradas “imperfeitas”** e reduzir `422 Unprocessable Entity` no BFF (FastAPI + Pydantic v2), sem abrir mão de **consistência**, **segurança** e **mensagens claras**.

> Referências no repo: `apps/bff/app/automations/*.py`, `apps/bff/app/auth/routes.py`  
> Complementa: **Pydantic v2 (ConfigDict populate_by_name, extra=ignore)**

---

## 1) Fundamentos

1. **Tolerância controlada na entrada**  
   - Use `extra="ignore"` para **desconsiderar ruído**.
   - Normalize campos (trim, lower, números em string, booleanos “sim/não”, datas ISO) **antes** da regra dura.

2. **Alias e nomes**  
   - `populate_by_name=True` + `Field(alias="...")` para casar **camelCase do JSON** com **snake_case** interno.

3. **Erro certo, lugar certo**  
   - **422**: quebras de **esquema** (tipo/formato).  
   - **400**: **regra de negócio** (ex.: data fim < data início).  
   - Trate exceções e **explique** o que o usuário deve corrigir.

---

## 2) Modelo base com normalização leve

```python
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import Optional

class SubmitPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    full_name: str = Field(alias="fullName", min_length=1)
    email: Optional[str] = None
    phone: Optional[str] = None
    accept_terms: Optional[bool] = None
    amount: Optional[float] = None
    date_start: Optional[str] = None  # aceitar string e normalizar para ISO

    # --- normalizadores de campo ---
    @field_validator("full_name")
    @classmethod
    def v_full_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("nome não pode estar vazio")
        return " ".join(p.capitalize() for p in v.split())

    @field_validator("email")
    @classmethod
    def v_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None: return v
        v = v.strip().lower()
        return v or None  # "" -> None

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v: Optional[str]) -> Optional[str]:
        if not v: return None
        digits = "".join(ch for ch in v if ch.isdigit())
        return digits or None

    @field_validator("accept_terms", mode="before")
    @classmethod
    def v_terms(cls, v):
        # aceita true/false/1/0/sim/nao
        if isinstance(v, bool): return v
        if v is None: return None
        s = str(v).strip().lower()
        return s in ("1","true","t","yes","y","sim")

    @field_validator("amount", mode="before")
    @classmethod
    def v_amount(cls, v):
        # aceita "1.234,56" / "1234.56" / "1 234,56"
        if v is None: return None
        s = str(v).strip().replace(" ", "")
        s = s.replace(".", "").replace(",", ".") if "," in s and "." in s else s.replace(",", ".")
        try:
            return float(s)
        except ValueError as e:
            raise ValueError("valor numérico inválido") from e

    @field_validator("date_start", mode="before")
    @classmethod
    def v_date(cls, v):
        if v in (None, ""): return None
        # aceite ISO curtas e completas; normalize para AAAA-MM-DD
        s = str(v).strip()
        from datetime import datetime
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ"):
            try:
                dt = datetime.strptime(s, fmt)
                return dt.date().isoformat()
            except ValueError:
                pass
        raise ValueError("data inválida; use AAAA-MM-DD")

    # --- validações cruzadas ---
    @model_validator(mode="after")
    def check_business_rules(self):
        # exemplo: termos obrigatórios
        if self.accept_terms is False:
            raise ValueError("é necessário aceitar os termos")
        return self
````

**O que isso resolve**

* Strings vazias → `None`.
* Booleans “soltos” → coerção (“sim” → `True`).
* Telefones → somente dígitos.
* Valores → floats robustos.
* Datas → ISO `YYYY-MM-DD`.

---

## 3) Uso no endpoint com mapeamento de erros

```python
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import ValidationError

router = APIRouter()

@router.post("/form2json/submit")
def submit(body: SubmitPayload, tasks: BackgroundTasks):
    try:
        # body já veio normalizado; prossiga
        sid = "s_123"  # salvar de verdade no db
        tasks.add_task(lambda: None)
        return {"id": sid, "status": "queued"}
    except ValidationError as ve:
        # FastAPI já retornaria 422 automaticamente;
        # este bloco é útil se você instanciar modelos manualmente
        raise HTTPException(status_code=422, detail=ve.errors()) from ve
    except ValueError as e:
        # regra de negócio
        raise HTTPException(status_code=400, detail=str(e)) from e
```

**Dica**: quando instanciar modelos manualmente (ex.: transformação intermediária), capture `ValidationError` e devolva **422** com `ve.errors()`.

---

## 4) Aliases e serialização para o front

```python
obj = SubmitPayload(fullName=" alice ", email="A@X.COM")
# Dump para o front (camelCase):
payload = obj.model_dump(by_alias=True)
```

* Sempre que o **contrato JSON** exigir **camelCase**, serialize com `by_alias=True`.

---

## 5) Tipos utilitários prontos para reuso

```python
from typing import Annotated
from pydantic import StringConstraints, AfterValidator, BeforeValidator

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

def _to_bool(v):
    if isinstance(v, bool): return v
    if v is None: return None
    s = str(v).strip().lower()
    return s in ("1","true","t","yes","y","sim")

LooseBool = Annotated[bool | None, BeforeValidator(_to_bool)]
```

Use esses **aliases** em vários modelos para padronizar entradas.

---

## 6) Mensagens amigáveis e consistentes

* Prefira mensagens **específicas**: “data inválida; use AAAA-MM-DD”.
* Para `422`, o corpo padrão do FastAPI já traz `loc`, `msg`, `type`.
* Opcional: padronize **envelopes** de erro:

  ```python
  def err(message: str, code: int): return {"error": message, "code": code}
  # raise HTTPException(400, err("valor numérico inválido", 400))
  ```

---

## 7) Testes rápidos (pytest)

```python
from pydantic import ValidationError

def test_trim_and_case():
    p = SubmitPayload(fullName="  maria da silva  ")
    assert p.full_name == "Maria Da Silva"

def test_amount_variants():
    assert SubmitPayload(fullName="a", amount="1.234,56").amount == 1234.56
    assert SubmitPayload(fullName="a", amount="1234.56").amount == 1234.56

def test_phone_digits():
    assert SubmitPayload(fullName="a", phone="(41) 9 9999-0000").phone == "41999990000"

def test_terms_required():
    try:
        SubmitPayload(fullName="a", accept_terms=False)
        assert False, "deveria falhar"
    except ValidationError as e:
        # mensagem vem de model_validator
        assert any("é necessário aceitar os termos" in (err.get("msg") or str(err)) for err in e.errors())
```

---

## 8) cURLs úteis para sanidade

```bash
# Payload “solto” aceito após normalização
curl -s -X POST http://localhost:8000/api/automations/form2json/submit \
  -H "Content-Type: application/json" \
  -d '{
    "fullName": "  alice  ",
    "email": "  ALICE@EXAMPLE.COM ",
    "phone": "(41) 9 9999-0000",
    "accept_terms": "sim",
    "amount": "1.234,56",
    "date_start": "18/11/2025"
  }' | jq .
```

A resposta deve **aceitar** e **normalizar** sem `422`.

---

## 9) Checklist de implementação

* [ ] `ConfigDict(populate_by_name=True, extra="ignore")` em **toda entrada**.
* [ ] **Normalizadores** (`field_validator` com `mode="before"` quando precisar coercer).
* [ ] **Validações cruzadas** em `model_validator(mode="after")`.
* [ ] **Aliases** em `Field(alias="...")` + `model_dump(by_alias=True)` quando emitir.
* [ ] **Mapeamento de erros**: `422` (esquema) vs `400` (regra de negócio).
* [ ] **Testes** cobrindo variações reais (vazios, maiúsculas, formatos locais).

---

## 10) Problemas comuns

* **`422` por campo extra** → faltou `extra="ignore"`.
* **Snake vs camel** → defina `alias` e habilite `populate_by_name`.
* **Booleanos em texto** → adicione normalizador (`LooseBool`).
* **Datas variadas** → aceite formatos locais e normalize para **ISO**.
* **Números com vírgula** → trate separadores antes de converter.

---

## Próximos passos

* **Pydantic v2 (ConfigDict populate_by_name, extra=ignore)**
* **Rotas gerais e automations** com o contrato completo
* **Tratamento de erros e logging** (padrões do projeto)

---

> _Criado em 2025-11-18_