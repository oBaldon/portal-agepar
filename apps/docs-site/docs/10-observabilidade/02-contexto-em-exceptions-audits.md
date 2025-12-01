---
id: contexto-em-exceptions-audits
title: "Contexto em exceptions/audits"
sidebar_position: 2
---

O Portal AGEPAR trata **erros** e **eventos de negócio** sempre com _contexto_ suficiente
para:

- entender o que aconteceu (logs + HTTP),
- rastrear quem fez o quê (auditoria em banco),
- correlacionar tudo por IDs (`sid`, `user_id`, `session_id`, etc.).

Na prática, quase toda operação importante deixa três rastros:

1. **Exception/log** (para dev/ops) → `logger.exception(...)` com contexto.
2. **Erro HTTP estruturado** (para o cliente) → `err_json(...)` ou `HTTPException`.
3. **Evento de auditoria** (para negócio) → `automation_audits` via `add_audit`/`audit_log`.

> Referências principais no repositório:  
> `apps/bff/app/automations/dfd.py`  
> `apps/bff/app/automations/ferias.py`  
> `apps/bff/app/automations/support.py`  
> `apps/bff/app/automations/accounts.py`  
> `apps/bff/app/automations/usuarios.py`  
> `apps/bff/app/automations/fileshare.py`  
> `apps/bff/app/automations/whoisonline.py`  
> `apps/bff/app/db.py`  

---

## 1) Três camadas de contexto para um mesmo problema

Quando algo dá errado em uma automação (ex.: DFD), o fluxo típico é:

```mermaid
sequenceDiagram
    participant User
    participant BFF as BFF (FastAPI)
    participant DB as Postgres

    User->>BFF: POST /api/automations/dfd/submit
    BFF->>BFF: valida payload (Pydantic)
    alt erro de validação
      BFF->>BFF: logger.exception("validation error on submit") (opcional)
      BFF-->>User: 422 {code, message, details}
      BFF->>DB: INSERT automation_audits (kind="dfd", action="failed", meta={...})
    else erro de processamento (I/O, template, etc.)
      BFF->>BFF: logger.exception("processing error | ...")
      BFF->>DB: UPDATE submissions (status="error", error="...")
      BFF->>DB: INSERT automation_audits (kind="dfd", action="failed", meta={sid, error})
      BFF-->>User: 500 {code="processing_error", message="Falha...", details}
    end
````

Para o mesmo incidente, você normalmente terá:

* uma linha de **log** com stack trace (`logger.exception(...)`),
* uma entrada em `submissions` com `status="error"` e `error="..."`,
* uma linha em `automation_audits` (`action="failed"`, `meta={"sid": ..., "error": ...}`),
* uma resposta HTTP JSON consistente para o cliente.

---

## 2) Exceptions com contexto (logger.exception)

### 2.1. DFD & Férias — mensagens específicas + IDs

Nos módulos `dfd.py` e `ferias.py`, o padrão é usar **mensagens específicas** nos
`logger.exception`:

```python title="apps/bff/app/automations/dfd.py — exemplos de mensagens" showLineNumbers
logger.exception("list models failed")
logger.exception("list_submissions storage error")
logger.exception("get_submission storage error")
logger.exception("validation error on submit")
logger.exception("duplicate check failed")
logger.exception("insert_submission failed")
logger.exception("processing error")
logger.exception("download error")
logger.exception("list_audits storage error")
logger.exception("audit (download) failed (non-blocking)")
```

No caso de `Férias` as mensagens ainda incluem “tags” visuais:

```python title="apps/bff/app/automations/ferias.py — contexto nas mensagens" showLineNumbers
logger.exception("[FERIAS][SUBMIT] failed to log raw payload")
logger.exception("[FERIAS][SUBMIT] failed to log validated summary")
logger.exception("[FERIAS][SUBMIT][422] failed to log validation_error")
logger.exception("[FERIAS][DELETE] get_submission storage error")
logger.exception("[FERIAS][DELETE] update storage error")
logger.exception("[FERIAS][DELETE] audit failed (non-blocking)")
```

Essas mensagens servem para:

* localizar rapidamente **onde** o erro ocorreu,
* diferenciar falhas de infra (`storage error`, `insert_submission failed`) de falhas de
  negócio (`validation_error`, `duplicate` etc.),
* tornar claro quando a falha em auditoria é **non-blocking** (não quebra a operação principal).

### 2.2. Exceções com IDs de negócio

Na pipeline assíncrona do DFD, o logger inclui o `sid` (submission id) sempre que possível:

```python title="apps/bff/app/automations/dfd.py — erro ao mudar para running" showLineNumbers
def _process_submission(sid: str, body: DfdIn, actor: Dict[str, Any]) -> None:
    try:
        update_submission(sid, status="running")
        add_audit(KIND, "running", actor, {"sid": sid})
    except Exception as e:
        logger.exception("update to running failed")
        try:
            update_submission(sid, status="error", error=f"storage: {e}")
        except Exception:
            pass
        try:
            add_audit(KIND, "failed", actor, {"sid": sid, "error": f"storage: {e}"})
        except Exception:
            pass
        return
```

Mesmo sem colocar o `sid` na mensagem, o contexto completo vem:

* na stack trace (arquivo/linha),
* no `automation_audits` (`meta={"sid": sid, ...}`),
* em `submissions` (`id = sid`, `error="storage: ..."`).

> **Ideia central:** o log identifica *o que* deu errado;
> o `sid` e os audits identificam *em qual execução* isso aconteceu.

---

## 3) Erros HTTP padronizados (`err_json`)

Quase todas as automations expõem um helper `err_json(...)` para responder erros
de forma estruturada:

```python title="apps/bff/app/automations/form2json.py — err_json" showLineNumbers
def err_json(
    status: int,
    *,
    code: str,
    message: str,
    details: Any = None,
    hint: Optional[str] = None,
    received: Any = None,
) -> JSONResponse:
    """
    Constrói uma resposta JSON padronizada de erro.
    """
    payload: Dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    if hint:
        payload["hint"] = hint
    if received is not None:
        payload["received"] = received
    return JSONResponse(status_code=status, content=payload)
```

Uso típico (DFD e Férias):

```python title="storage error em listagem de submissões" showLineNumbers
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

Ou em validação:

```python title="Erro de validação com detalhes amigáveis" showLineNumbers
try:
    payload = DfdIn(**raw)  # Pydantic v2
except ValidationError as ve:
    friendly = _friendly_errors(ve)
    return err_json(
        422,
        code="validation_error",
        message="Erro de validação nos campos.",
        details={"errors": friendly},
    )
```

Pontos importantes:

* O cliente sempre recebe um `code` curto (`"storage_error"`, `"validation_error"`,
  `"duplicate_numero"`, etc.).
* `message` é em pt-BR, voltada ao usuário.
* `details` pode conter detalhes técnicos **controlados**, úteis para suporte.
* Stack trace nunca vai para o cliente; fica só no log.

---

## 4) Auditoria com meta rico (automation_audits)

A parte “permanente” do contexto de negócio fica em:

* tabela **`automation_audits`** (ver seção de Banco),
* helpers `add_audit` e `audit_log` (`apps/bff/app/db.py`).

### 4.1. `add_audit` — eventos das automations

Exemplos concretos:

```python title="apps/bff/app/automations/dfd.py — ciclo de vida da submissão" showLineNumbers
# criação
add_audit(KIND, "submitted", user, {"sid": sid, "protocolo": raw.get("protocolo")})

# início do processamento
add_audit(KIND, "running", actor, {"sid": sid})

# erro de storage
add_audit(KIND, "failed", actor, {"sid": sid, "error": f"storage: {e}"})

# erro de item específico
add_audit(KIND, "failed", actor, {"sid": sid, "error": f"item {i} invalid"})

# conclusão bem-sucedida
add_audit(KIND, "completed", actor, {"sid": sid, "protocolo": body.protocolo})
```

Em `Férias`:

```python title="apps/bff/app/automations/ferias.py — delete + download" showLineNumbers
add_audit(
    KIND,
    "deleted",
    user,
    {
        "sid": sid,
        "status": row.get("status"),
        "protocolo": (_to_obj(row.get("payload"), {}) or {}).get("protocolo") or None,
        "soft_delete": True,
    },
)

add_audit(KIND, "download", user, {"sid": sid, "fmt": "zip", "protocolo": result.get("protocolo")})
add_audit(KIND, "download", user, {"sid": sid, "fmt": fmt, "bytes": len(data), "protocolo": result.get("protocolo")})
```

E em automations administrativas:

```python title="apps/bff/app/automations/accounts.py — usuários e roles" showLineNumbers
add_audit("accounts", "create_user", actor, {"user_id": user_id, "roles": roles, "deprecated": True})
add_audit("accounts", "update_user", actor, {"user_id": user_id, "fields": [f.split("=")[0].strip() for f in fields]})
add_audit("accounts", "delete_user", actor, {"user_id": user_id})
add_audit("accounts", "set_roles", actor, {"user_id": user_id, "roles": roles})
add_audit("accounts", "create_role", actor, {"role": name_norm})
add_audit("accounts", "delete_role", actor, {"role": role_name})
```

Padrão de **meta**:

* `sid` para submissões,
* `protocolo`, `numero` para documentos,
* `user_id` para contas,
* `session_id` para sessões (`whoisonline.py`),
* `filename`, `size`, `ttl`, `has_secret` em `fileshare`,
* `soft_delete`, `fmt`, `bytes` em operações específicas.

### 4.2. `audit_log` — eventos de fileshare

`fileshare.py` usa um alias com `target_id`:

```python title="apps/bff/app/automations/fileshare.py — audit_log" showLineNumbers
db.audit_log(
    actor=user,
    action="uploaded",
    kind="fileshare",
    target_id=item_id,
    meta={"filename": file.filename, "size": size, "ttl": ttl, "has_secret": bool(secret)},
)

db.audit_log(
    actor=user,
    action="download_denied",
    kind="fileshare",
    target_id=item_id,
    meta={"reason": "secret_required"},
)

db.audit_log(
    actor=user,
    action="deleted",
    kind="fileshare",
    target_id=item_id,
    meta={"filename": r["filename"]},
)
```

Esse `target_id` vira `meta["target_id"]` dentro de `audit_log`, facilitando
construir telas de auditoria que mostram:

* “Arquivo X (id Y) foi enviado por Fulano às HH:MM…”
* “Download negado por falta de chave secreta…”.

---

## 5) Erros na própria auditoria: non-blocking

Uma decisão explícita do projeto é:

> **Falha ao auditar não deve, sozinha, derrubar a operação principal.**

Por isso, chamadas de `add_audit` em pontos sensíveis são protegidas por `try/except`
que **logam o erro mas seguem em frente**:

```python title="apps/bff/app/automations/dfd.py — falha em auditoria" showLineNumbers
try:
    add_audit(KIND, "failed", actor, {"sid": sid, "error": f"storage: {e}"})
except Exception:
    logger.exception("audit (download) failed (non-blocking)")
```

Em `Férias`:

```python title="apps/bff/app/automations/ferias.py — delete" showLineNumbers
try:
    add_audit(
        KIND,
        "deleted",
        user,
        {
            "sid": sid,
            "status": row.get("status"),
            "protocolo": (_to_obj(row.get("payload"), {}) or {}).get("protocolo") or None,
            "soft_delete": True,
        },
    )
except Exception:
    logger.exception("[FERIAS][DELETE] audit failed (non-blocking)")
```

Ou seja:

* Se o INSERT em `automation_audits` falhar:

  * o usuário ainda recebe resposta (delete ok, download ok, etc.),
  * a falha de auditoria fica registrada em log (com stack trace),
  * pode ser alvo de investigação/alertas de observabilidade,
  * nenhuma transação de negócio é revertida por falta de log.

---

## 6) Diretrizes para “contexto em exceptions/audits” em novas features

Quando você criar ou evoluir uma automação, use este checklist:

1. **Sempre que capturar `Exception`, registre em log com contexto**

   * usar `logger.exception("mensagem curta e específica")`;
   * incluir, se possível, identificadores (`sid`, `user_id`, `session_id`) na mensagem
     ou em campos adicionais;
   * evitar despejar o `payload` inteiro no log.

2. **Construa respostas de erro HTTP padronizadas**

   * usar `err_json(status, code="...", message="...", details=...)` em automations;
   * para erros “globais”, pode usar `HTTPException` diretamente, com `detail` claro;
   * nunca expor stack trace ou detalhes sensíveis ao cliente.

3. **Registre eventos em `automation_audits` com meta rico**

   * incluir sempre:

     * `sid` (quando houver submissão),
     * `user_id` ou dados do ator,
     * chaves de negócio (`protocolo`, `numero`, `filename`, `fmt`, etc.);
   * diferenciar ações com `action` semanticamente útil (`submitted`, `running`,
     `completed`, `failed`, `download`, `deleted`, `user.create`, etc.).

4. **Trate falhas de auditoria como non-blocking**

   * embrulhar `add_audit`/`audit_log` em `try/except` nos pontos críticos;
   * usar `logger.exception("... audit failed (non-blocking)")`;
   * só falhar a operação se a auditoria for o próprio core da feature.

5. **Evitar dados sensíveis em logs/audits**

   * não incluir:

     * senhas, tokens, segredos,
     * documentos inteiros ou grandes blobs,
     * dados pessoais além do necessário (CPF apenas quando realmente precisa).
   * preferir hashes, tamanhos (`bytes`), IDs e rótulos neutros.

6. **Padronizar chaves em `meta` e mensagens**

   * `sid`, `user_id`, `session_id`, `protocolo`, `numero`, `fmt`, `bytes`, `reason`,
     `soft_delete`, etc.;
   * isso facilita dashboards (como a automação `controle`) usarem sempre as mesmas
     chaves para montar descrições humanas.

---

> _Criado em 2025-12-01_