---
id: exemplos-de-4xx-5xx-por-cenário
title: "Exemplos de 4xx/5xx por cenário"
sidebar_position: 2
---

Esta página mostra **erros na prática**, com exemplos reais de:

- **4xx** → problema no pedido / permissão do cliente (DX),
- **5xx** → problema interno no BFF / infra.

O foco são as automações **DFD** e **Férias**, que seguem o contrato:

```json
{
  "code": "algum_codigo",
  "message": "Mensagem em português.",
  "details": { "..." : "..." }
}
```

(implementado via `err_json(...)` em `dfd.py` e `ferias.py`).

> Referências principais
> `apps/bff/app/automations/dfd.py`
> `apps/bff/app/automations/ferias.py`

---

## 1) Visão rápida: 4xx vs 5xx

* **4xx** (erro do cliente / contexto de uso):

  * payload inválido (`validation_error`),
  * pedido malformado (`bad_request`),
  * falta de confirmação (`confirmation_required`),
  * permissão insuficiente (`forbidden`),
  * submissão inexistente (`not_found`),
  * estado conflitante (`not_ready`, `submission_in_progress`, `duplicate`),
  * recurso antes existente, agora removido (`file_not_found` com 410).

* **5xx** (erro no servidor):

  * falha ao falar com o banco (`storage_error`),
  * erro inesperado ao gerar/baixar arquivos (`download_error`),
  * exceções não tratadas em rotinas internas.

---

## 2) 400 / 422 — payload inválido ou pedido inconsistente

### 2.1. `422 validation_error` (DFD — campos errados)

**Cenário**
Usuário preenche o formulário DFD com:

* `pcaAno` com 2 dígitos,
* `numero` vazio,
* `assunto` vazio.

Back-end (em `dfd.py`):

* Pydantic levanta `ValidationError`,
* helper `_format_validation_errors` gera mensagens amigáveis,
* resposta vem com `422 validation_error`.

```bash title="DFD — submit com payload inválido" showLineNumbers
curl -i -b /tmp/cookies.txt \
  -X POST http://localhost:8000/api/automations/dfd/submit \
  -H "Content-Type: application/json" \
  -d '{
    "modeloSlug": "padrao",
    "numero": "",
    "protocolo": "12345/2025",
    "assunto": "",
    "pcaAno": "20"
  }'
```

Resposta (resumida):

```json
HTTP/1.1 422 Unprocessable Entity
{
  "code": "validation_error",
  "message": "Erro de validação nos campos.",
  "details": {
    "errors": [
      "Campo 'Número do memorando' é obrigatório.",
      "Campo 'Assunto' é obrigatório.",
      "Campo 'Ano do PCA' deve conter 4 dígitos (ex.: 2025)."
    ]
  }
}
```

### 2.2. `422 validation_error` (Férias — Pydantic cru em `details`)

**Cenário**
Usuário envia datas de férias invertidas (início > fim) ou formato inválido.

Em `ferias.py`:

* Pydantic levanta `ValidationError`,
* logs em `[FERIAS][SUBMIT][422] validation_error`,
* o BFF retorna `ve.errors()` direto em `details`.

```bash title="Férias — payload inválido" showLineNumbers
curl -i -b /tmp/cookies.txt \
  -X POST http://localhost:8000/api/automations/ferias/submit \
  -H "Content-Type: application/json" \
  -d '{
    "inicio": "2025-15-01",
    "fim": "2025-01-10",
    "servidorCpf": "00000000000"
  }'
```

Resposta (exemplo):

```json
HTTP/1.1 422 Unprocessable Entity
{
  "code": "validation_error",
  "message": "Erro de validação nos campos.",
  "details": [
    {
      "loc": ["body", "inicio"],
      "msg": "value is not a valid date",
      "type": "value_error.date"
    },
    {
      "loc": ["body", "__root__"],
      "msg": "data de início não pode ser maior que data de fim",
      "type": "value_error"
    }
  ]
}
```

### 2.3. `400 bad_request` (parâmetro inválido de download)

**Cenário**
Usuário tenta baixar DFD em um formato desconhecido (`fmt=txt`).

Trecho (DFD):

```python
if fmt not in ("pdf", "docx", "zip"):
    return err_json(
        400,
        code="bad_request",
        message="Formato de download inválido.",
        details={"allowed": ["pdf", "docx", "zip"], "fmt": fmt},
    )
```

Chamada:

```bash title="DFD — download com fmt inválido" showLineNumbers
curl -i -b /tmp/cookies.txt \
  "http://localhost:8000/api/automations/dfd/submissions/<sid>/download?fmt=txt"
```

Resposta:

```json
HTTP/1.1 400 Bad Request
{
  "code": "bad_request",
  "message": "Formato de download inválido.",
  "details": {
    "allowed": ["pdf", "docx", "zip"],
    "fmt": "txt"
  }
}
```

---

## 3) 401 / 403 — não autenticado vs sem permissão

### 3.1. `401 not authenticated` em `/api/me` e automations

**Cenário**
Usuário sem cookie de sessão válido chama `/api/me` ou tenta acessar submissões.

Em `main.py`:

```python
@APP.get("/api/me")
def get_me(request: Request):
    user = _get_user_from_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user
```

Chamada:

```bash title="GET /api/me sem sessão" showLineNumbers
curl -i http://localhost:8000/api/me
```

Resposta:

```json
HTTP/1.1 401 Unauthorized
{ "detail": "not authenticated" }
```

### 3.2. `403 forbidden` — submissão de outro usuário (DFD/Férias)

**Cenário**
Usuário tenta baixar ou excluir submissão que não é dele e não tem role de admin.

Trecho típico (DFD):

```python
if not _can_access_submission(user, row):
    return err_json(
        403,
        code="forbidden",
        message="Você não tem permissão para acessar esta submissão.",
    )
```

Chamada:

```bash title="DFD — tentar acessar submissão de outro usuário" showLineNumbers
curl -i -b /tmp/cookies-outro-usuario.txt \
  "http://localhost:8000/api/automations/dfd/submissions/<sid>/download?fmt=pdf"
```

Resposta:

```json
HTTP/1.1 403 Forbidden
{
  "code": "forbidden",
  "message": "Você não tem permissão para acessar esta submissão."
}
```

---

## 4) 404 / 410 — recurso não encontrado / removido

### 4.1. `404 not_found` — submissão inexistente

**Cenário**
Usuário tenta acessar um `sid` que não existe (ou não tem acesso a ele).

Trecho (DFD/Férias):

```python
row = get_submission(sid)
if not row:
    return err_json(
        404,
        code="not_found",
        message="Submissão não encontrada.",
        details={"sid": sid},
    )
```

Chamada:

```bash title="Férias — submissão inexistente" showLineNumbers
curl -i -b /tmp/cookies.txt \
  "http://localhost:8000/api/automations/ferias/submissions/00000000-0000-0000-0000-000000000000"
```

Resposta:

```json
HTTP/1.1 404 Not Found
{
  "code": "not_found",
  "message": "Submissão não encontrada.",
  "details": { "sid": "00000000-0000-0000-0000-000000000000" }
}
```

### 4.2. `410 file_not_found` — saída foi removida (DFD/Férias)

**Cenário**
Submission está `done`, mas o arquivo físico (PDF/DOCX/ZIP) já não existe mais
(limpeza de disco, erro de IO prévio).

Trecho típico:

```python
if not os.path.exists(path):
    return err_json(
        410,
        code="file_not_found",
        message="Arquivo não está mais disponível.",
        details={"sid": sid, "fmt": fmt},
    )
```

Chamada:

```bash title="DFD — arquivo removido do disco" showLineNumbers
curl -i -b /tmp/cookies.txt \
  "http://localhost:8000/api/automations/dfd/submissions/<sid>/download?fmt=pdf"
```

Resposta:

```json
HTTP/1.1 410 Gone
{
  "code": "file_not_found",
  "message": "Arquivo não está mais disponível.",
  "details": {
    "sid": "<sid>",
    "fmt": "pdf"
  }
}
```

---

## 5) 409 — conflitos de estado

### 5.1. `409 not_ready` — ainda processando

**Cenário**
Usuário tenta baixar resultado de DFD/Férias enquanto status é `queued` ou `running`.

Trecho (DFD):

```python
if row["status"] in ("queued", "running"):
    return err_json(
        409,
        code="not_ready",
        message="Resultado ainda não está pronto.",
        details={"sid": sid, "status": row["status"]},
    )
```

Chamada:

```bash title="DFD — tentar baixar enquanto processa" showLineNumbers
curl -i -b /tmp/cookies.txt \
  "http://localhost:8000/api/automations/dfd/submissions/<sid>/download?fmt=pdf"
```

Resposta:

```json
HTTP/1.1 409 Conflict
{
  "code": "not_ready",
  "message": "Resultado ainda não está pronto.",
  "details": {
    "sid": "<sid>",
    "status": "running"
  }
}
```

### 5.2. `409 submission_in_progress` — não pode excluir (Férias)

**Cenário**
Usuário tenta deletar submissão `running` em Férias.

Trecho (Férias):

```python
if row["status"] == "running":
    return err_json(
        409,
        code="submission_in_progress",
        message="Submissão em processamento; aguarde a conclusão para tentar excluir novamente.",
        details={"sid": sid, "status": row["status"]},
    )
```

Chamada:

```bash title="Férias — delete em running" showLineNumbers
curl -i -b /tmp/cookies.txt \
  -X DELETE http://localhost:8000/api/automations/ferias/submissions/<sid>
```

Resposta:

```json
HTTP/1.1 409 Conflict
{
  "code": "submission_in_progress",
  "message": "Submissão em processamento; aguarde a conclusão para tentar excluir novamente.",
  "details": { "sid": "<sid>", "status": "running" }
}
```

### 5.3. `409 duplicate` — DFD já existe

**Cenário**
Na automação DFD, o sistema não permite criar dois DFDs com:

* mesmo número de memorando **ou**
* mesmo protocolo.

Trecho simplificado:

```python
if exists_submission_payload_value(KIND, "protocolo", body.protocolo):
    return err_json(
        409,
        code="duplicate",
        message="Já existe um DFD com este Protocolo.",
        details={"field": "protocolo", "value": body.protocolo},
    )
```

Chamada:

```bash title="DFD — duplicidade de protocolo" showLineNumbers
curl -i -b /tmp/cookies.txt \
  -X POST http://localhost:8000/api/automations/dfd/submit \
  -H "Content-Type: application/json" \
  -d '{"modeloSlug":"padrao","numero":"2025-001","protocolo":"12345/2025","assunto":"...","pcaAno":"2025"}'
```

Resposta:

```json
HTTP/1.1 409 Conflict
{
  "code": "duplicate",
  "message": "Já existe um DFD com este Protocolo.",
  "details": {
    "field": "protocolo",
    "value": "12345/2025"
  }
}
```

---

## 6) 400 específicos de fluxo: confirmação necessária

### `400 confirmation_required` (Férias — delete sem confirmação)

**Cenário**
Endpoint de exclusão de Férias exige um body com `confirm=true`.
Sem isso, responde com erro explícito, para evitar exclusões acidentais (UX).

Trecho (Férias):

```python
if not body.confirm:
    return err_json(
        400,
        code="confirmation_required",
        message="Confirmação obrigatória para excluir a submissão.",
        details={"sid": sid},
    )
```

Chamada:

```bash title="Férias — delete sem confirm" showLineNumbers
curl -i -b /tmp/cookies.txt \
  -X DELETE "http://localhost:8000/api/automations/ferias/submissions/<sid>" \
  -H "Content-Type: application/json" \
  -d '{"confirm": false}'
```

Resposta:

```json
HTTP/1.1 400 Bad Request
{
  "code": "confirmation_required",
  "message": "Confirmação obrigatória para excluir a submissão.",
  "details": { "sid": "<sid>" }
}
```

---

## 7) 500 — storage_error / download_error

### 7.1. `500 storage_error` — problema de banco/IO

**Cenário**
O BFF falha ao ler/escrever em `submissions` (`db.insert_submission`, `db.list_submissions`, etc.).

Trecho típico (DFD/Férias):

```python
try:
    rows = list_submissions(...)
    return {"items": rows, "limit": limit, "offset": offset}
except Exception as e:
    logger.exception("list_submissions storage error")
    return err_json(
        500,
        code="storage_error",
        message="Falha ao consultar submissões.",
        details=str(e),
    )
```

Resposta:

```json
HTTP/1.1 500 Internal Server Error
{
  "code": "storage_error",
  "message": "Falha ao consultar submissões.",
  "details": "connection refused"
}
```

> Nos logs, `logger.exception` grava stack trace completo e contexto de operação.

### 7.2. `500 download_error` — falha inesperada ao gerar/streamar arquivo

**Cenário**
Erro inesperado ao criar um ZIP ou streamar um arquivo para o cliente.

Trecho (DFD/Férias, conceito):

```python
try:
    # montar zip ou streaming response
except Exception as e:
    logger.exception("download error")
    return err_json(
        500,
        code="download_error",
        message="Falha ao preparar o download.",
        details=str(e),
    )
```

Resposta:

```json
HTTP/1.1 500 Internal Server Error
{
  "code": "download_error",
  "message": "Falha ao preparar o download.",
  "details": "..."
}
```

---

## 8) Resumo em tabela (cenário → status/code)

| Cenário                                         | HTTP | `code`                         |
| ----------------------------------------------- | ---- | ------------------------------ |
| Payload inválido (DFD/Férias)                   | 422  | `validation_error`             |
| Formato de download inválido                    | 400  | `bad_request`                  |
| Delete sem confirmação (Férias)                 | 400  | `confirmation_required`        |
| Não autenticado                                 | 401  | `{detail:"not authenticated"}` |
| Sem permissão (DFD/Férias)                      | 403  | `forbidden`                    |
| Submissão não encontrada                        | 404  | `not_found`                    |
| Resultado ainda não pronto                      | 409  | `not_ready`                    |
| Exclusão de submissão em processamento (Férias) | 409  | `submission_in_progress`       |
| Duplicidade (DFD mesmo protocolo/número)        | 409  | `duplicate`                    |
| Arquivo não está mais disponível                | 410  | `file_not_found`               |
| Falha de banco/IO geral                         | 500  | `storage_error`                |
| Falha inesperada ao preparar download           | 500  | `download_error`               |

---

## 9) Dica para o Host (TypeScript): tratar 4xx/5xx

Um pattern simples para o Host:

```ts title="Helper TS para tratar erros de automations" showLineNumbers
export type AutomationError = {
  code?: string;
  message?: string;
  details?: unknown;
  hint?: string;
};

export async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (res.ok) {
    return (await res.json()) as T;
  }

  let payload: any = null;
  try {
    payload = await res.json();
  } catch {
    // fallback genérico
    throw new Error(`Erro HTTP ${res.status}`);
  }

  // Automations (err_json): {code, message, ...}
  if (payload && typeof payload === "object" && "code" in payload) {
    const err = payload as AutomationError;
    const msg = err.message || `Erro HTTP ${res.status}`;
    const e = new Error(msg) as Error & { code?: string; details?: unknown };
    e.code = err.code;
    e.details = err.details;
    throw e;
  }

  // Demais (HTTPException): {detail}
  if (payload && typeof payload.detail === "string") {
    throw new Error(payload.detail);
  }

  throw new Error(`Erro HTTP ${res.status}`);
}
```

Com isso:

* `code` pode ser usado para fluxos especiais (`duplicate`, `not_ready`, etc.),
* `message` é exibida direto para o usuário,
* 4xx/5xx são tratados de forma uniforme.

---

> _Criado em 2025-12-02_