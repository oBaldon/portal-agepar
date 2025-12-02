---
id: regras-de-normalização-para-evitar-422
title: "Regras de normalização para evitar 422"
sidebar_position: 3
---

O Portal AGEPAR tenta ser **tolerante com o frontend**:

- o BFF não deve devolver `422 Unprocessable Entity` por detalhes bobos,
- campos extras **não** devem quebrar endpoints,
- diferenças pequenas de nome (`pcaAno` vs `pca_ano`) não devem causar erro.

Para isso, o backend aplica um conjunto de **regras de normalização** antes (ou durante)
a validação Pydantic, e o Host também ajusta os payloads.

> Referências principais  
> `apps/bff/app/automations/dfd.py`  
> `apps/bff/app/automations/ferias.py`  
> `apps/bff/app/auth/schemas.py`  
> `apps/host/src/types.ts`  
> `apps/host/src/lib/api.ts`

---

## 1) Objetivo: diminuir 422 “bobos”, não esconder 422 reais

A ideia não é “sumir com 422”, e sim:

- **evitar 422 causados apenas por evolução de UI** (campo novo, alias diferente, etc.),
- reservar `422 validation_error` para **erros de validação de fato**:
  - campo obrigatório ausente,
  - formato incorreto (data, número, ano com 4 dígitos),
  - regra de negócio de validação (datas invertidas, etc.).

Pipeline conceitual:

```mermaid
flowchart LR
  A["Request JSON do Host/Form"]
  B["Normalização leve (strip, defaults, mapeamentos)"]
  C["Modelo Pydantic v2 (populate_by_name + extra='ignore')"]
  D["Negócio / persistência"]
  E["422 validation_error {code, message, details}"]

  A --> B
  B --> C
  C -->|ok| D
  C -->|ValidationError| E

````

---

## 2) Configuração padrão dos modelos (Pydantic v2)

Quase todos os modelos de entrada seguem o mesmo padrão de `model_config`:

```python title="Padrão de configuração dos modelos" showLineNumbers
from pydantic import BaseModel, Field, ConfigDict

class DfdIn(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    modelo_slug: str = Field(..., alias="modeloSlug")
    numero: str = Field(..., min_length=1, max_length=50)
    protocolo: str = Field(..., min_length=1, max_length=50)
    assunto: str = Field(..., min_length=1, max_length=200)
    pca_ano: str = Field(..., alias="pcaAno", pattern=r"^\d{4}$")
```

**Como isso ajuda a evitar 422 triviais:**

* `extra="ignore"`
  → campos extras enviados pelo frontend (experimentos/flags) são simplesmente
  ignorados, em vez de causarem `422` (`extra_forbidden`).
* `populate_by_name=True`
  → o modelo aceita tanto:

  * `modelo_slug` (nome Python),
  * quanto `modeloSlug` (alias esperado pelo JSON do front).
* `alias` em campos-chave
  → permite que forms usem `camelCase` sem quebrar a API.

Exemplo de payload aceito:

```json
{
  "modeloSlug": "padrao",
  "numero": "2025-001",
  "protocolo": "12345/2025",
  "assunto": "Aquisição de serviço X",
  "pcaAno": "2025",
  "campoNovoDaUI": "qualquer coisa"
}
```

Mesmo que `campoNovoDaUI` não exista no modelo, ele será ignorado.

---

## 3) Normalização de strings e campos antes de validar

Além da config do modelo, as automations fazem **normalização leve** antes de instanciar
o `BaseModel`, para reduzir chances de 422 “semânticos”.

Padrões comuns:

* `strip()` em todos os campos de texto:

  * `"  12345/2025  "` → `"12345/2025"`,
* normalizar “ano” para string de 4 dígitos:

  * `2025` (número) → `"2025"`,
* tratar `None`/`""` como “não informado” para campos opcionais,
* remover caracteres não numéricos de campos como CPF, quando necessário.

Exemplo simplificado (padrão usado em DFD/outros):

```python title="Normalização de payload bruto antes de validar" showLineNumbers
def _clean_str(v: str | None) -> str | None:
    if v is None:
        return None
    return v.strip()

def normalize_dfd_payload(raw: dict) -> dict:
    data = dict(raw or {})

    data["modeloSlug"] = _clean_str(data.get("modeloSlug") or "")
    data["numero"] = _clean_str(data.get("numero") or "")
    data["protocolo"] = _clean_str(data.get("protocolo") or "")
    data["assunto"] = _clean_str(data.get("assunto") or "")

    pca_ano = data.get("pcaAno")
    if isinstance(pca_ano, int):
        data["pcaAno"] = f"{pca_ano:04d}"
    elif isinstance(pca_ano, str):
        data["pcaAno"] = pca_ano.strip()

    return data

# Uso no endpoint de submit
raw = await request.json()
normalized = normalize_dfd_payload(raw)
body = DfdIn(**normalized)
```

Benefícios:

* Usuário não é penalizado por pequenos erros de digitação (espaços a mais),
* UI pode mandar `number` ou `string` para `pcaAno`, e o BFF ajusta antes de validar,
* reduz a chance de disparar `422` apenas por causa de whitespace ou tipo literal.

---

## 4) Regras específicas vistas em DFD/Férias

### 4.1. DFD

Em `dfd.py` (conceito):

* **requests GET/list**:

  * validam params de paginação (`limit`, `offset`) com defaults e `Query(..., ge, le)`,
  * qualquer coisa fora do range vira 422 “real” (FastAPI/Pydantic).
* **submit**:

  * normaliza campos (`strip`, `pcaAno`),
  * usa `populate_by_name + alias` para aceitar variações,
  * transforma `ValidationError` em `validation_error` com mensagens amigáveis.

Trecho de tratamento de `ValidationError` (resumo):

```python title="DFD — convertendo ValidationError em erro amigável" showLineNumbers
from pydantic import ValidationError

try:
    body = DfdIn(**normalized)
except ValidationError as ve:
    friendly = _format_validation_errors(ve)
    return err_json(
        422,
        code="validation_error",
        message="Erro de validação nos campos.",
        details={"errors": friendly},
    )
```

### 4.2. Férias

Em `ferias.py`:

* fluxo semelhante, mas os `details` carregam `ve.errors()` direto (útil para UIs mais ricas),
* normalização de datas/strings antes de instanciar o modelo,
* validação de período (início ≤ fim) feita via Pydantic ou validador de modelo.

Exemplo simplificado de validador:

```python title="Validação de período de datas (Férias)" showLineNumbers
from pydantic import BaseModel, ConfigDict, field_validator
from datetime import date

class FeriasIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    inicio: date
    fim: date

    @field_validator("fim")
    @classmethod
    def check_period(cls, v: date, values: dict) -> date:
        inicio = values.get("inicio")
        if inicio and v < inicio:
            raise ValueError("data de fim não pode ser menor que data de início")
        return v
```

Essa validação é **negócio-real**, então 422 é desejado — mas diferenças bobas de
formato (ex.: `" 2025-01-10 "`) são sanadas na normalização anterior.

---

## 5) Normalização também no Host (React/TS)

O Host ajuda a evitar 422 antes de falar com o BFF:

* tipos TS dos formulários espelham os modelos de entrada,
* conversão de campos de UI (checkbox, select) para o formato esperado pelo backend,
* garantias básicas:

  * `pcaAno` sempre com 4 dígitos,
  * datas em `YYYY-MM-DD`,
  * booleanos de checkboxes convertidos para `true/false`.

Exemplo típico de payload no Host:

```ts title="Host — tipo e normalização de payload DFD" showLineNumbers
export type DfdFormPayload = {
  modeloSlug: string;
  numero: string;
  protocolo: string;
  assunto: string;
  pcaAno: string;
};

export function normalizeDfdForm(form: Partial<DfdFormPayload>): DfdFormPayload {
  return {
    modeloSlug: (form.modeloSlug ?? "").trim(),
    numero: (form.numero ?? "").trim(),
    protocolo: (form.protocolo ?? "").trim(),
    assunto: (form.assunto ?? "").trim(),
    pcaAno: String(form.pcaAno ?? "").trim(),
  };
}

export async function submitDfd(form: Partial<DfdFormPayload>) {
  const body = normalizeDfdForm(form);
  const res = await fetch("/api/automations/dfd/submit", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  // tratamento de erro padrão...
}
```

Essa camada:

* reduz chance de mandar tipos esquisitos (`number`/`null` em campos textuais),
* já faz `trim` básico para o usuário,
* deixa a validação Pydantic mais previsível.

---

## 6) Regras de normalização resumidas

### 6.1. No backend (Pydantic + helpers)

* **Sempre** usar `ConfigDict(populate_by_name=True, extra="ignore")`.
* **Sempre** considerar um passo de normalização antes do `BaseModel`:

  * `strip()` em strings,
  * conversão de tipos (int → str em anos, etc.),
  * tratar `None` como `""` quando campo é obrigatório de texto.
* **Usar alias** para compatibilizar `snake_case`/`camelCase`:

  * `pca_ano` com `alias="pcaAno"`,
  * `remember_me` com `alias="rememberMe"` (login).
* **Tratar campos opcionais**:

  * permitir ausência sem 422,
  * só validar quando presentes.

### 6.2. No frontend (Host)

* Modelar tipos TS próximos do modelo Pydantic.
* Garantir:

  * datas em `YYYY-MM-DD`,
  * anos como string de 4 dígitos,
  * checkboxes em `boolean`, não `"on"`.
* Não enviar campos “aleatórios” com valores inesperados (ex.: objetos grandes sem motivo).

---

## 7) Checklist para novas automations/endpoints (evitar 422 inútil)

Quando criar uma nova automação ou endpoint:

1. **Defina o modelo Pydantic com:**

   ```python
   model_config = ConfigDict(populate_by_name=True, extra="ignore")
   ```
2. **Use `alias` para campos expostos na UI**

   * `campoPython: str = Field(..., alias="campoJson")`.
3. **Implemente uma função de normalização do `raw`**

   * limpeza de whitespace,
   * ajustes de tipos (`int` → `str`),
   * saneamento de valores de select (ex.: `"---"` → `""`).
4. **Converta `ValidationError` em `422 validation_error` amigável**

   * usando `err_json(...)` com `code="validation_error"`,
   * em DFD: transformar em lista de mensagens legíveis,
   * em outras automations: `ve.errors()` em `details`.
5. **Não trate como 422 o que é regra de negócio pós-validação**

   * duplicidade → `409 duplicate`,
   * submissão em processamento → `409 not_ready/submission_in_progress`,
   * permissão → `403 forbidden`.
6. **No Host, crie helpers de normalização de formulário**

   * uma função `normalizeXxxForm(form)` por automação,
   * assim o backend recebe menos “ruído”.

---

## 8) Exemplo completo (cURL + TS + py)

### 8.1. TS — envio normalizado

```ts title="TS — envio de férias normalizado" showLineNumbers
type FeriasPayload = {
  inicio: string; // "YYYY-MM-DD"
  fim: string;    // "YYYY-MM-DD"
  servidorCpf: string;
};

function normalizeFeriasForm(form: Partial<FeriasPayload>): FeriasPayload {
  return {
    inicio: (form.inicio ?? "").trim(),
    fim: (form.fim ?? "").trim(),
    servidorCpf: (form.servidorCpf ?? "").replace(/\D/g, ""),
  };
}

async function submitFerias(form: Partial<FeriasPayload>) {
  const body = normalizeFeriasForm(form);
  const res = await fetch("/api/automations/ferias/submit", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  // tratar resposta / erro...
}
```

### 8.2. Python — modelo e submit

```python title="Python — modelo e uso no endpoint" showLineNumbers
class FeriasIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    inicio: date
    fim: date
    servidor_cpf: str = Field(..., alias="servidorCpf", min_length=11, max_length=11)

    @field_validator("servidor_cpf")
    @classmethod
    def somente_digitos(cls, v: str) -> str:
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 11:
            raise ValueError("CPF deve ter 11 dígitos")
        return digits

@router.post("/submit")
def submit_ferias(body: FeriasIn, user=Depends(require_auth)):
    # body já está normalizado (datas e cpf)
    ...
```

### 8.3. cURL — teste com espaços e formatação solta

```bash title="Teste com payload “sujo”" showLineNumbers
curl -i -b /tmp/cookies.txt \
  -X POST http://localhost:8000/api/automations/ferias/submit \
  -H "Content-Type: application/json" \
  -d '{
    "inicio": " 2025-01-10 ",
    "fim": "2025-01-20",
    "servidorCpf": " 000.000.000-00 "
  }'
```

Com as regras de normalização, o backend aceita e valida corretamente:

* `inicio` → `"2025-01-10"`,
* `servidorCpf` → `"00000000000"`.

Se algo ficar realmente inválido (ex.: data impossível), cai no `422 validation_error`,
que é exatamente o que esperamos.

---

> _Criado em 2025-12-01_
