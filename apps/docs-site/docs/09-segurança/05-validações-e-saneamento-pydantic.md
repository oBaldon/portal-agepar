---
id: validações-e-saneamento-pydantic
title: "Validações e saneamento (Pydantic)"
sidebar_position: 5
---

No BFF do Portal AGEPAR, **Pydantic v2** é a base para:

- validar **entrada** de automações e endpoints (/api/**),
- **sanear** dados (strings, datas, enums) antes de salvar em `submissions`,
- montar DTOs de saída mais previsíveis para o Host.

A regra é:

> Deixar o máximo possível de validação e saneamento no **modelo Pydantic**,  
> reduzindo `if/else` de validação espalhado em endpoints.

> Referências principais no repositório:  
> `apps/bff/app/automations/form2json.py`  
> `apps/bff/app/automations/dfd.py`  
> `apps/bff/app/automations/ferias.py`  
> `apps/bff/app/automations/controle.py`  
> `apps/bff/app/auth/schemas.py`  
> `apps/bff/app/db.py`  

---

## 1) Configuração padrão dos modelos (Pydantic v2)

Os modelos Pydantic seguem um padrão recorrente de configuração:

- **`populate_by_name=True`**  
  → aceita tanto o nome Python (`modelo_slug`) quanto o alias JSON (`modeloSlug`).
- **`extra="ignore"`**  
  → campos extras vindos do frontend são ignorados (não geram 422).
- Campos com **restrições declarativas**:
  - `min_length`, `max_length`,
  - `pattern` (regex),
  - tipos específicos (`EmailStr`, `conint`, etc.).

Exemplo típico de modelo de automação:

```python title="Exemplo de modelo Pydantic em automação" showLineNumbers
from pydantic import BaseModel, Field, ConfigDict

class DfdIn(BaseModel):
    """
    Modelo de entrada do DFD, alinhado com o formulário em iframe.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",  # Campos extras NÃO quebram com 422.
    )

    modelo_slug: str = Field(..., alias="modeloSlug")
    numero: str = Field(..., min_length=1, max_length=50)
    assunto: str = Field(..., min_length=1, max_length=200)
    pca_ano: str = Field(..., alias="pcaAno", pattern=r"^\d{4}$")
    protocolo: str = Field(..., min_length=1, max_length=50)
    # ... outros campos específicos da automação
````

Benefícios imediatos:

* O frontend pode evoluir o payload (campos novos) sem quebrar versões antigas do BFF.
* 422 acontecem **somente** quando:

  * faltam campos obrigatórios, ou
  * algum campo viola uma regra de negócio “declarada” (regex, tamanho, etc.).
* Input sempre chega às automações em um formato **coerente** (`payload` normalizado).

---

## 2) Saneamento de dados de entrada

Mesmo com tipos fortes, quase todo input “bruto” precisa de alguma limpeza:

* `strip()` em strings (tirar espaços antes/depois),
* normalizar caixa (`upper()` para códigos, `lower()` para e-mails),
* converter flags “sim/não” → booleano (`True/False`),
* garantir datas em formato ISO.

Existem dois jeitos principais usados no projeto:

1. **Pré-processamento manual** (antes do `BaseModel`).
2. **Validadores Pydantic** (`@field_validator`, `@model_validator`).

### 2.1. Pré-processamento manual (mais comum nas automações)

Exemplo simplificado (form2json):

```python title="Pré-processamento manual em automação" showLineNumbers
def _clean_str(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip()

class Form2JsonIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    nome: str
    email: str
    comentario: str | None = None

def normalize_body(raw: dict) -> Form2JsonIn:
    """
    Aplica strip e outros ajustes antes de validar.
    """
    raw = dict(raw or {})
    raw["nome"] = _clean_str(raw.get("nome") or "")
    raw["email"] = _clean_str(raw.get("email") or "")
    raw["comentario"] = _clean_str(raw.get("comentario"))
    return Form2JsonIn(**raw)
```

Padrão nas automações (DFD, Férias, form2json):

1. Ler `raw: dict` do request.
2. Fazer um `normalize_body(raw)` com:

   * pods de limpeza (`_clean_str`, `_clean_date`, `_clean_bool`),
   * normalização de campos que vêm de `<select>` ou `<checkbox>`.
3. Só então instanciar o `BaseModel`.

### 2.2. Validadores Pydantic (`field_validator`, `model_validator`)

Para regras de saneamento **mais ligadas à semântica do campo**, usar validadores é mais limpo:

```python title="Validadores em Pydantic v2" showLineNumbers
from pydantic import BaseModel, ConfigDict, field_validator

class UsuarioIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    nome: str
    email: str
    cpf: str

    @field_validator("nome")
    @classmethod
    def nome_strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("email")
    @classmethod
    def email_normalize(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("cpf")
    @classmethod
    def cpf_digits_only(cls, v: str) -> str:
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 11:
            raise ValueError("CPF deve ter 11 dígitos")
        return digits
```

Vantagens:

* Toda entrada desse modelo sempre estará “limpa”, independentemente de onde for usada.
* Erros de validação aparecem já no 422 padrão do FastAPI, com mensagens Pydantic.

---

## 3) Evitando 422 “bobos”: `extra="ignore"` + aliases

Um objetivo explícito do projeto é **minimizar 422 triviais** (mudanças evolutivas do front):

* O Host e as UIs em iframe podem enviar campos extras ou renomear coisas pouco a pouco.
* O BFF não deve “travar” por causa disso — principalmente em automações já estáveis.

O combo usado é:

1. `extra="ignore"` → campos extras simplesmente **somem**.
2. `populate_by_name=True` + `alias` → aceita tanto `snake_case` quanto `camelCase`.

Exemplo (login):

```python title="apps/bff/app/auth/schemas.py — Login" showLineNumbers
class LoginIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    identifier: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    remember_me: bool = Field(False, alias="rememberMe")
```

Isso permite:

* O Host enviar `{ "identifier": "foo", "password": "bar", "rememberMe": true }`.
* Futuras UIs (ex.: mobile) enviarem o mesmo payload, sem risco de 422 por `rememberMe`.

---

## 4) Validação de entrada nas rotas (FastAPI + Pydantic)

### 4.1. Corpo tipado no endpoint

Em boa parte das rotas, o body já é tipado com `BaseModel`:

```python title="Exemplo de endpoint com body tipado" showLineNumbers
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/api/automations/form2json", tags=["form2json"])

class Form2JsonIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    nome: str
    email: str
    comentario: str | None = None

@router.post("/submit")
def submit_form(
    body: Form2JsonIn,
    user = Depends(require_auth),  # obtém user da sessão
):
    """
    Recebe e valida o formulário JSON.
    """
    # body já está validado e saneado aqui.
    payload = body.model_dump(mode="json")
    # ... cria submission, dispara background task, etc.
    return {"ok": True}
```

Se algo estiver errado no payload:

* O FastAPI responde 422 automaticamente com a estrutura padrão de erro Pydantic:

  * `{"detail": [{"loc": ..., "msg": ..., "type": ...}, ...]}`.
* Não é necessário escrever `if not body.campo` à mão.

### 4.2. Camada de erro legível: `err_json(...)`

Para erros de negócio (não de validação Pydantic), várias automações usam um helper:

```python title="Padrão de erro JSON nas automações" showLineNumbers
def err_json(
    error: str,
    message: str,
    status_code: int = 400,
    details: Any | None = None,
    hint: str | None = None,
) -> JSONResponse:
    """
    Constrói resposta de erro padronizada para as automações.
    """
    payload: dict[str, Any] = {"error": error, "message": message}
    if details is not None:
        payload["details"] = details
    if hint:
        payload["hint"] = hint
    return JSONResponse(status_code=status_code, content=payload)
```

Uso típico:

* **Validação Pydantic** lida com estrutura e tipo → 422 automático.
* **`err_json(...)`** lida com regras de negócio:

  * duplicidade de DFD (`numero`/`protocolo`),
  * não encontrar submissão,
  * usuário sem permissão específica, etc.

---

## 5) Saneamento pós-validação: preparando `payload` e `result`

Depois que o modelo Pydantic é aceito, as automações costumam:

1. Gerar `payload` “bonito” via `model_dump`.
2. Guardar esse payload em `submissions.payload` (JSONB).
3. Usar os dados saneados para montar `result`.

Exemplo (DFD):

```python title="DFD — usando modelo validado para construir payload" showLineNumbers
body = DfdIn(**raw_normalizado)

payload = body.model_dump(mode="json")

insert_submission(
    {
        "id": sid,
        "kind": KIND,
        "version": DFD_VERSION,
        "actor_cpf": user.get("cpf"),
        "actor_nome": user.get("nome"),
        "actor_email": user.get("email"),
        "payload": payload,   # já saneado
        "status": "queued",
        "result": None,
        "error": None,
    }
)
```

Ao fazer isso, o que vai para o banco tem as seguintes propriedades:

* campos desnecessários/“lixo” do frontend já foram descartados,
* formatos estão normalizados (datas, números, booleans, strings),
* eventuais convenções (ex.: `pca_ano` com 4 dígitos) já foram garantidas.

Isso facilita:

* consultas futuras (`payload->>'numero'`, `payload->>'protocolo'`),
* deduplicação (`exists_submission_payload_value`),
* interpretação dos dados em relatórios.

---

## 6) Validações de negócio além do Pydantic

Pydantic cuida da **camada estrutural**; o BFF ainda aplica validações de negócio, por exemplo:

* **Duplicidade de DFD**:

  ```python title="Checando duplicidade por payload" showLineNumbers
  if db.exists_submission_payload_value(KIND, "numero", body.numero):
      return err_json(
          "duplicate_numero",
          f"Já existe DFD com número {body.numero}.",
          status_code=409,
      )
  ```

* **Período de férias incompatível**:

  ```python title="Validação de período em férias" showLineNumbers
  if body.inicio > body.fim:
      return err_json(
          "invalid_period",
          "Data de início não pode ser maior que a data de fim.",
          status_code=400,
      )
  ```

* **Campos obrigatórios condicionais** (ex.: se tipo X, então campo Y é obrigatório):

  * às vezes feitos com `model_validator(mode="after")`,
  * às vezes diretamente no endpoint, com `err_json`.

Padrão recomendado:

* **Tudo que é “forma”** (tipo, regex, presença de campo) → Pydantic.
* **Tudo que é “regra de negócio”** (duplicidade, período, workflow) → lógica da automação.

---

## 7) Diretrizes para novas automações / endpoints

Quando você criar uma nova automação ou endpoint, siga este checklist:

1. **Crie um modelo Pydantic de entrada**

   * Com `ConfigDict(populate_by_name=True, extra="ignore")`.
   * Campos com `min_length`, `max_length`, `pattern` onde fizer sentido.
   * Use tipos adequados (`EmailStr`, `AnyUrl`, `conint`, etc.).

2. **Faça saneamento básico**

   * Funções de limpeza (`_clean_str`, `_clean_date`) **ou** validadores Pydantic.
   * Evite guardar no banco strings com espaços sobrando ou caixas inconsistentes.

3. **Use o modelo como tipo do body no endpoint**

   * Deixe o FastAPI/Pydantic responder 422 quando a estrutura estiver errada.
   * Evite revalidar coisas óbvias manualmente (`if not body.campo`).

4. **Construa o `payload` a partir do modelo**

   * Nunca use diretamente o `raw` da requisição em `submissions`.
   * Use `body.model_dump(mode="json")` (ou `model_dump` equivalente) para gerar o JSON.

5. **Trate erros de negócio com `err_json`**

   * 400 / 409 / 403/404, sempre com:

     * `error` (código estável),
     * `message` (texto legível),
     * `hint` opcional (como o usuário pode resolver).

6. **Mantenha validações em lugar previsível**

   * Preferir concentrar “condições de campo” no modelo Pydantic.
   * Regras que envolvem banco (duplicidade, limites) na própria automação.

---

## 8) Exemplo completo (TS/py) para amarrar tudo

### 8.1. Frontend (TypeScript) — payload tipado

```ts title="Host — tipo de payload para automação exemplo" showLineNumbers
export type ExemploPayload = {
  numero: string;
  protocolo: string;
  assunto: string;
  pcaAno: string;
};

export async function submitExemplo(body: ExemploPayload) {
  const res = await fetch("/api/automations/exemplo/submit", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    // tratar erros padronizados (error/message/hint)
    const err = await res.json();
    throw err;
  }
  return await res.json();
}
```

### 8.2. Backend (Python) — Pydantic + saneamento + submission

```python title="BFF — modelo, saneamento e submit" showLineNumbers
class ExemploIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    numero: str = Field(..., min_length=1, max_length=50)
    protocolo: str = Field(..., min_length=1, max_length=50)
    assunto: str = Field(..., min_length=1, max_length=200)
    pca_ano: str = Field(..., alias="pcaAno", pattern=r"^\d{4}$")

    @field_validator("numero", "protocolo", "assunto")
    @classmethod
    def strip_common(cls, v: str) -> str:
        return v.strip()

@router.post("/submit")
def submit_exemplo(body: ExemploIn, user=Depends(require_auth)):
    if db.exists_submission_payload_value("exemplo", "numero", body.numero):
        return err_json(
            "duplicate_numero",
            f"Já existe EXEMPLO com número {body.numero}.",
            status_code=409,
        )

    sid = str(uuid4())
    payload = body.model_dump(mode="json")

    insert_submission(
        {
            "id": sid,
            "kind": "exemplo",
            "version": "1.0.0",
            "actor_cpf": user.get("cpf"),
            "actor_nome": user.get("nome"),
            "actor_email": user.get("email"),
            "payload": payload,
            "status": "queued",
            "result": None,
            "error": None,
        }
    )

    # ... disparar background task, etc.
    return {"sid": sid, "status": "queued"}
```

Com isso:

* o frontend envia payload **tipado**,
* o Pydantic garante estrutura e saneamento,
* o BFF evita 422 triviais (`extra="ignore"`),
* `submissions.payload` fica sempre em formato previsível para consultas futuras.

---

> _Criado em 2025-12-01_