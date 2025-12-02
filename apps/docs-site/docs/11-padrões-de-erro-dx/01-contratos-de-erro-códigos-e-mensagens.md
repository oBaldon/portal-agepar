---
id: contratos-de-erro-códigos-e-mensagens
title: "Contratos de erro (códigos e mensagens)"
sidebar_position: 1
---

Os endpoints de automação do Portal AGEPAR (ex.: **DFD** e **Férias**) seguem
um **contrato de erro explícito**:

- **Status HTTP** coerente com o cenário (400/403/404/409/410/422/500…).
- Corpo JSON padronizado com, no mínimo:

  ```json
  {
    "code": "validation_error",
    "message": "Erro de validação nos campos."
  }
  ```

* Campos opcionais (`details`, `hint`, etc.) para enriquecer a DX sem quebrar clientes.

> Referências principais no repositório
> `apps/bff/app/automations/dfd.py`
> `apps/bff/app/automations/ferias.py`

---

## 1) Envelope padrão de erro (`err_json`)

Tanto `dfd.py` quanto `ferias.py` definem um helper único para respostas de erro:

```python title="apps/bff/app/automations/dfd.py — err_json" showLineNumbers
def err_json(status: int, **payload):
    """
    Retorna uma resposta JSON com encoding/controlado, preservando mensagens em pt-BR.
    """
    return StreamingResponse(
        BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
        status_code=status,
        media_type="application/json; charset=utf-8",
    )
```

Mesma ideia em `ferias.py`.

**Propriedades importantes:**

* `status: int` → define o **HTTP status code** (ex.: 400, 404, 422, 500…).

* `**payload` → dicionário livre, mas na prática sempre contém:

  * `code: str` — código de erro para a aplicação/Host,
  * `message: str` — mensagem em pt-BR para o usuário,
  * `details: any` (opcional) — dados extras (lista de erros, campos, etc.),
  * `hint: str` (muito raro hoje) — dica de como resolver.

* `ensure_ascii=False` → preserva acentuação nos JSONs (DX 💚).

* `media_type="application/json; charset=utf-8"` → charset explícito.

> 💡 Regra: **toda automação nova** deve usar `err_json(...)` para erros,
> mantendo esse envelope.

---

## 2) Mapeamento `status HTTP` × `code`

### 2.1. Códigos usados em **DFD**

A partir de `apps/bff/app/automations/dfd.py`:

| HTTP | `code`             | Uso típico                                                                            |
| ---- | ------------------ | ------------------------------------------------------------------------------------- |
| 400  | `bad_request`      | Formato de parâmetro inválido (ex.: formato de download diferente de `pdf`/`docx`).   |
| 403  | `forbidden`        | Usuário autenticado, mas sem acesso à submissão (não é dono e não tem role adequada). |
| 404  | `not_found`        | Submissão inexistente ou não acessível pelo usuário.                                  |
| 409  | `not_ready`        | Resultado ainda não está pronto (submissão `queued`/`running`).                       |
| 409  | `not_available`    | Resultado existe, mas formato pedido (PDF/DOCX) não foi gerado para aquela submissão. |
| 410  | `file_not_found`   | Arquivo já foi removido ou não está mais disponível no filesystem.                    |
| 409  | `duplicate`        | Já existe DFD com o mesmo número de memorando ou protocolo (checagem de duplicidade). |
| 422  | `validation_error` | Erros de validação nos campos (Pydantic/negócio).                                     |
| 422  | `identity_missing` | Falta de CPF/e-mail para filtrar submissões (sessão inconsistente).                   |
| 500  | `storage_error`    | Falhas de banco/IO na listagem/consulta/salvamento.                                   |
| 500  | `download_error`   | Erro inesperado ao preparar o download (zip/DOCX/PDF).                                |

Exemplo real de resposta:

```json title="Exemplo de erro de validação (DFD)"
{
  "code": "validation_error",
  "message": "Erro de validação nos campos.",
  "details": {
    "errors": [
      "Campo 'Ano do PCA' deve conter 4 dígitos (ex.: 2025).",
      "Campo 'Número do memorando' excedeu o limite de 30 caracteres."
    ]
  }
}
```

E um erro de duplicidade:

```json title="Exemplo de duplicidade (DFD)"
{
  "code": "duplicate",
  "message": "Já existe um DFD com este Protocolo.",
  "details": {
    "field": "protocolo",
    "value": "12345/2025"
  }
}
```

### 2.2. Códigos usados em **Férias**

A partir de `apps/bff/app/automations/ferias.py`:

| HTTP | `code`                   | Uso típico                                                                         |
| ---- | ------------------------ | ---------------------------------------------------------------------------------- |
| 400  | `bad_request`            | Formato de download inválido (`fmt` fora de `requerimento`/`substituicao`, etc.).  |
| 400  | `confirmation_required`  | Falta de confirmação explícita (`body.confirm=false`) para excluir uma submissão.  |
| 403  | `forbidden`              | Usuário autenticado, mas não é dono da submissão ou não tem permissão para a ação. |
| 404  | `not_found`              | Submissão inexistente ou não visível para o usuário.                               |
| 409  | `not_ready`              | Resultado ainda não está pronto (processo em andamento).                           |
| 409  | `submission_in_progress` | Tentativa de excluir submissão ainda em `running`.                                 |
| 410  | `file_not_found`         | Arquivos de saída (PDF/ZIP) não disponíveis (limpeza, erro prévio, etc.).          |
| 422  | `validation_error`       | Erros de validação nos campos (Pydantic).                                          |
| 422  | `identity_missing`       | Falta de CPF/e-mail para filtrar submissões do usuário (sessão inconsistente).     |
| 500  | `storage_error`          | Falha em consultas/gravação no Postgres.                                           |

Exemplos:

```json title="Sem identidade para filtro (Férias)"
{
  "code": "identity_missing",
  "message": "Sem CPF/e-mail para filtrar submissões. Faça login novamente."
}
```

```json title="Submissão em processamento (Férias)"
{
  "code": "submission_in_progress",
  "message": "Submissão em processamento; aguarde a conclusão para tentar excluir novamente.",
  "details": {
    "sid": "1f9e04b2-...",
    "status": "running"
  }
}
```

```json title="Erro de validação (Férias)"
{
  "code": "validation_error",
  "message": "Erro de validação nos campos.",
  "details": [
    {
      "loc": ["body", "inicio"],
      "msg": "Data inválida",
      "type": "value_error"
    }
  ]
}
```

> Note que em Férias os `details` para `validation_error` carregam diretamente
> `ve.errors()` do Pydantic; em DFD, o helper `_format_validation_errors(...)`
> converte em mensagens de texto amigáveis.

---

## 3) Padrão de mensagens (`message`) e idioma

As mensagens são sempre:

* em **português**, pensadas para o usuário final (servidor público),
* curtas, diretas, sem incluir stack trace ou detalhes internos,
* alinhadas ao HTTP status:

  * 400/422 → foco em “o que tem de errado no campo ou no pedido”,
  * 403 → “você não tem permissão…”,
  * 404 → “Submissão não encontrada.”,
  * 409 → “Resultado ainda não está pronto.”, “já existe…”, etc.,
  * 410 → “Arquivo não está mais disponível.”,
  * 500 → “Falha ao consultar/salvar…”.

A **aplicação cliente (Host)** deve sempre:

* usar `code` para **ramificações** (ex.: mostrar alert específico para `duplicate`,
  `not_ready`, `confirmation_required`),
* exibir `message` diretamente ou com pequenas adaptações.

---

## 4) Erros de validação (`validation_error`) e DX

### 4.1. DFD — mensagens amigáveis por campo

No DFD, um helper transforma erros do Pydantic em texto:

```python title="apps/bff/app/automations/dfd.py — friendly errors" showLineNumbers
def _format_validation_errors(ve: ValidationError) -> List[str]:
    """
    Traduz erros do Pydantic v2 em mensagens amigáveis por campo para a UI.
    """
    msgs: List[str] = []
    for err in ve.errors():
        # usa FIELD_INFO para mapear chaves -> labels de formulário
        # gera mensagens como:
        # - "Campo 'Ano do PCA' deve conter 4 dígitos (ex.: 2025)."
        # - "Campo 'Assunto' excedeu o limite de 200 caracteres."
        ...
    return msgs
```

E na rota de submit:

```python title="DFD — uso de validation_error" showLineNumbers
try:
    body = DfdPayload(**raw)
except ValidationError as ve:
    friendly = _format_validation_errors(ve)
    logger.info("[DFD] validation_error: %s", friendly)
    return err_json(
        422,
        code="validation_error",
        message="Erro de validação nos campos.",
        details={"errors": friendly},
    )
except Exception as ve:
    logger.exception("validation error on submit")
    return err_json(
        422,
        code="validation_error",
        message="Erro de validação.",
        details=str(ve),
    )
```

Contrato resultante:

```json
{
  "code": "validation_error",
  "message": "Erro de validação nos campos.",
  "details": {
    "errors": ["mensagem 1", "mensagem 2", "..."]
  }
}
```

### 4.2. Férias — erros Pydantic crus em `details`

Já em Férias:

```python title="Férias — uso de validation_error" showLineNumbers
except ValidationError as ve:
    try:
        logger.info(
            "[FERIAS][SUBMIT][422] validation_error errors=%s raw=%s",
            ve.errors(),
            json.dumps(raw, ensure_ascii=False),
        )
    except Exception:
        logger.exception("[FERIAS][SUBMIT][422] failed to log validation_error")
    return err_json(
        422,
        code="validation_error",
        message="Erro de validação nos campos.",
        details=ve.errors(),
    )
```

Ou seja:

* `details` é a lista original de `ve.errors()` (Pydantic v2),
* permite que UIs mais avançadas (ou futuras automações) interpretem a estrutura
  programaticamente, se desejarem.

---

## 5) Erros *genéricos* via `HTTPException` (auth e afins)

Fora das automations (ex.: login, cadastro, sessões), o BFF usa `HTTPException`
diretamente — nesses casos, o corpo padrão é:

```json
{ "detail": "Mensagem de erro" }
```

Exemplos em `apps/bff/app/auth/routes.py`:

```python title="auth/routes.py — exemplos de HTTPException" showLineNumbers
raise HTTPException(status_code=401, detail="Credenciais inválidas.")
raise HTTPException(status_code=409, detail="E-mail já cadastrado.")
raise HTTPException(status_code=410, detail="Auto-registro desativado.")
raise HTTPException(status_code=429, detail="Muitas tentativas. Tente novamente mais tarde.")
```

Ponto importante para DX:

* **Automations** → usam `err_json` com `{code, message, details}`.
* **Auth/outros** → usam `HTTPException` com `{detail}`.

O Host tratou isso abstraindo a leitura:

* tenta primeiro `res.json().code/message`,
* se não houver, cai para `detail` e status HTTP.

---

## 6) Guia rápido para novos endpoints/atuações

Quando for criar/alterar endpoints, siga este **contrato de erro**:

1. **Use sempre `err_json(...)` em automations**

   ```python
   return err_json(
       400,
       code="bad_request",
       message="Parâmetros inválidos.",
       details={"campo": "xyz"},
   )
   ```

2. **Escolha um `code` curto e estável**

   * snake_case, em inglês:

     * `validation_error`, `storage_error`, `not_ready`,
       `duplicate_numero`, `permission_denied` etc.
   * não incluir o nome da automação no code (isso vem em `kind`/rota/audit).

3. **Mensagem em pt-BR, para humanos**

   * clara e sem detalhes internos (stack trace, nome de tabela, etc.).
   * não misturar `code` e `message` (code é para máquina, message para gente).

4. **Use `details` para dar contexto, nunca para despejar tudo**

   * exemplos:

     * `{"field": "numero", "value": "2025-001"}`,
     * `{"errors": ["Mensagem 1", "Mensagem 2"]}`,
     * `{"sid": "...", "status": "running"}`.
   * evite colocar payload completo ou dados sensíveis.

5. **Alinhe o status HTTP com o cenário**

   * 400 → request malformado (campo obrigatório, `confirmation_required`, etc.).
   * 401 → não autenticado (uso de `HTTPException` comum).
   * 403 → autenticado, mas sem permissão (`forbidden`).
   * 404 → recurso inexistente (`not_found`).
   * 409 → conflito de estado (`duplicate`, `not_ready`, `submission_in_progress`).
   * 410 → recurso antes existente, agora removido (`file_not_found`).
   * 422 → erro de validação (`validation_error`) quando faz sentido destacar esse tipo.
   * 500 → falhas servidor/infra (`storage_error`, `download_error`).

6. **Padronize também a auditoria**

   * junto com o erro, grave `automation_audits` com:

     * `action="failed"` ou similar,
     * `meta={"code": "validation_error", "sid": sid, ...}`.

---

## 7) Exemplos (cURL) para ver o contrato em ação

### 7.1. DFD — erro de validação

```bash title="DFD — submit com erro de validação" showLineNumbers
curl -i -c /tmp/cookies.txt \
  -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"identifier":"dev@example.com","password":"dev"}'

curl -i -b /tmp/cookies.txt \
  -X POST http://localhost:8000/api/automations/dfd/submit \
  -H "Content-Type: application/json" \
  -d '{"numero":"", "protocolo":"", "pcaAno":"20", "assunto":""}'
```

Resposta (resumo):

```json
HTTP/1.1 422 Unprocessable Entity
{
  "code": "validation_error",
  "message": "Erro de validação nos campos.",
  "details": { "errors": ["Campo 'Ano do PCA' deve conter 4 dígitos (ex.: 2025).", "..."] }
}
```

### 7.2. Férias — submissão ainda em processamento

```bash title="Férias — tentar excluir submissão em running" showLineNumbers
curl -i -b /tmp/cookies.txt \
  -X DELETE http://localhost:8000/api/automations/ferias/submissions/<sid>
```

Resposta (resumo):

```json
HTTP/1.1 409 Conflict
{
  "code": "submission_in_progress",
  "message": "Submissão em processamento; aguarde a conclusão para tentar excluir novamente.",
  "details": { "sid": "<sid>", "status": "running" }
}
```

---

> _Criado em 2025-12-02_