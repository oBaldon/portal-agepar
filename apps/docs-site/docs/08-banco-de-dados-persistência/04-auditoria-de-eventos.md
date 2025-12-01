---
id: auditoria-de-eventos
title: "Auditoria de eventos"
sidebar_position: 4
---

A **auditoria de eventos** do Portal AGEPAR registra, em um lugar único, tudo o que
é relevante do ponto de vista de rastreabilidade:

- quem fez o quê,
- em qual automação (`kind`),
- quando (`at`),
- com qual alvo (`sid`, `user_id`, `session_id`, etc.),
- e com metadados ricos (`meta` em JSONB).

Na prática, isso aparece como:

- tabela `automation_audits` no banco,
- helpers `add_audit`, `audit_log`, `list_audits` em `app/db.py`,
- endpoints de consulta em automações como `controle`, `dfd`, `ferias` e `fileshare`.

> Referências principais no repositório:  
> `apps/bff/app/db.py`  
> `apps/bff/app/automations/controle.py`  
> `apps/bff/app/automations/dfd.py`  
> `apps/bff/app/automations/ferias.py`  
> `apps/bff/app/automations/accounts.py`  
> `apps/bff/app/automations/usuarios.py`  
> `apps/bff/app/automations/fileshare.py`  
> `apps/bff/app/automations/whoisonline.py`

---

## 1) Modelo de auditoria: tabela `automation_audits`

Esquema criado em `init_db()` (`apps/bff/app/db.py`):

```sql title="Tabela automation_audits (resumo)"
CREATE TABLE IF NOT EXISTS automation_audits (
  id         BIGSERIAL PRIMARY KEY,
  at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor_cpf  TEXT,
  actor_nome TEXT,
  kind       TEXT NOT NULL,
  action     TEXT NOT NULL,
  meta       JSONB
);

CREATE INDEX IF NOT EXISTS ix_automation_audits_at
  ON automation_audits (at DESC);
````

Semântica dos campos:

* `id` — identificador do evento.
* `at` — timestamp (UTC) em que o evento foi gravado.
* `actor_cpf`, `actor_nome` — quem gerou a ação (quando aplicável).
* `kind` — automação ou domínio lógico:

  * `"dfd"`, `"ferias"`, `"form2json"`, `"accounts"`, `"usuarios"`, `"fileshare"`, `"whoisonline"`, etc.
* `action` — string curta representando a ação:

  * exemplos reais:
    `submitted`, `running`, `completed`, `failed`, `download`,
    `duplicate_rejected`, `create_user`, `update_user`, `delete_role`,
    `uploaded`, `shared_link_created`, `downloaded_shared_link`,
    `revoke` (sessão revogada), etc.
* `meta` — JSONB com detalhes de contexto:

  * `sid`, `protocolo`, `user_id`, `session_id`,
  * `filename`, `size`, `ttl`, `has_secret`,
  * `bytes`, `ip`, `changes_count`, etc.

Visão conceitual:

```mermaid
erDiagram
  automation_audits {
    bigserial   id PK
    timestamptz at
    text        actor_cpf
    text        actor_nome
    text        kind
    text        action
    jsonb       meta
  }

  %% Exemplo de convenção em meta
  %% meta.sid -> id de submissão
  %% meta.user_id -> id de usuário
  %% meta.session_id -> id de sessão
```

> Não existe FK formal para `submissions` ou outras tabelas: a ligação é feita **por
> convenção** via campos em `meta` (ex.: `sid`, `user_id`, `session_id`).

---

## 2) Helpers de DB: `add_audit`, `audit_log`, `list_audits`

### 2.1. `add_audit` — grava evento “cru” em `automation_audits`

`apps/bff/app/db.py`:

```python title="app/db.py — add_audit" showLineNumbers
def add_audit(kind: str, action: str, actor: Dict[str, Any], meta: Dict[str, Any]) -> None:
    """
    Registra um evento de auditoria em `automation_audits`.
    """
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO automation_audits (actor_cpf, actor_nome, kind, action, meta)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                actor.get("cpf"),
                actor.get("nome") or actor.get("name"),
                kind,
                action,
                _to_json_value(meta),
            ),
        )
```

* `actor` é o usuário autenticado (tipicamente vem de `request.session["user"]`).
* `meta` é qualquer dicionário **serializável em JSON**, convertido por `_to_json_value`.

### 2.2. `audit_log` — alias com `target_id`

Para cenários onde faz sentido ter um “alvo principal”:

```python title="app/db.py — audit_log (alias)" showLineNumbers
def audit_log(
    actor: Dict[str, Any],
    action: str,
    kind: str,
    target_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Alias compatível para `add_audit`, com `target_id` opcional em `meta`.
    """
    meta = dict(meta or {})
    if target_id is not None and "target_id" not in meta:
        meta["target_id"] = target_id
    add_audit(kind=kind, action=action, actor=actor, meta=meta)
```

É usado, por exemplo, em `fileshare.py`:

```python title="fileshare.py — exemplo com audit_log" showLineNumbers
db.audit_log(
    actor=user,
    action="uploaded",
    kind="fileshare",
    target_id=item_id,
    meta={"filename": file.filename, "size": size, "ttl": ttl, "has_secret": bool(secret)},
)
```

### 2.3. `list_audits` — leitura pura de `automation_audits`

Função base em `db.py`:

```python title="app/db.py — list_audits" showLineNumbers
def list_audits(kind: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Lista eventos de auditoria.
    """
    params: List[Any] = []
    where = ["1=1"]
    if kind:
        where.append("kind = %s")
        params.append(kind)
    where_sql = " AND ".join(where)
    sql = f"""
        SELECT * FROM automation_audits
        WHERE {where_sql}
        ORDER BY at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() or []
        return [dict(r) for r in rows]
```

Outras camadas (ex.: `controle.py`) constroem APIs mais ricas **em cima** disso.

---

## 3) Quando um evento é gerado? Exemplos por automação

### 3.1. DFD e Férias — ciclo de vida da submissão

Em `dfd.py` e `ferias.py`, o padrão é:

1. **Submissão criada** (`/submit`):

   * grava `submissions` com `status="queued"`;
   * registra auditoria `submitted`.

2. **Processamento em background**:

   * marca `status="running"`; audita `running`;
   * em sucesso: `status="done"`; audita `completed`;
   * em falha: `status="error"`; audita `failed`.

3. **Download de resultado**:

   * endpoint `/submissions/{sid}/download` registra `download` com detalhes
     (`bytes`, `fmt`, `ip`, `filename`, etc.).

Trecho real (DFD):

```python title="dfd.py — trechos de auditoria" showLineNumbers
# Na criação
insert_submission(sub)
add_audit(KIND, "submitted", user, {"sid": sid, "protocolo": raw.get("protocolo")})

# No processamento em background
update_submission(sid, status="running")
add_audit(KIND, "running", actor, {"sid": sid})

# Em sucesso (após gerar DOCX/PDF)
update_submission(sid, status="done", result=result, error=None)
add_audit(KIND, "completed", actor, {"sid": sid, "protocolo": body.protocolo})

# Em erro
update_submission(sid, status="error", error=str(exc))
add_audit(KIND, "failed", actor, {"sid": sid, "error": str(exc)})

# No download
add_audit(
    KIND,
    "download",
    user,
    {
        "sid": sid,
        "filename": filename,
        "bytes": len(data),
        "fmt": fmt,
        "ip": (getattr(request.client, "host", None) if request and request.client else None),
    },
)
```

Fluxo resumido:

```mermaid
sequenceDiagram
    participant U as Usuário
    participant BFF as BFF (DFD/Férias)
    participant DB as Postgres (submissions + automation_audits)

    U->>BFF: POST /submit
    BFF->>DB: INSERT submissions (status="queued")
    BFF->>DB: INSERT automation_audits (action="submitted")

    BFF->>BFF: BackgroundTask processa(submission)
    BFF->>DB: UPDATE submissions (status="running")
    BFF->>DB: INSERT automation_audits (action="running")

    alt sucesso
      BFF->>DB: UPDATE submissions (status="done", result=...)
      BFF->>DB: INSERT automation_audits (action="completed")
    else erro
      BFF->>DB: UPDATE submissions (status="error", error=...)
      BFF->>DB: INSERT automation_audits (action="failed")
    end

    U->>BFF: POST /submissions/{sid}/download
    BFF->>DB: INSERT automation_audits (action="download", meta={...})
```

### 3.2. Accounts/Usuários — eventos de administração

Em `accounts.py` e `usuarios.py`, a auditoria registra operações sensíveis:

```python title="accounts.py — exemplos" showLineNumbers
# Criação de usuário (API legada)
add_audit("accounts", "create_user", actor, {"user_id": user_id, "roles": roles, "deprecated": True})

# Atualização de usuário
add_audit("accounts", "update_user", actor, {"user_id": user_id, "fields": fields})

# Criação de role
add_audit("accounts", "create_role", actor, {"role": role_name})

# Deleção de role
add_audit("accounts", "delete_role", actor, {"role": role_name})
```

```python title="usuarios.py — exemplos" showLineNumbers
add_audit("usuarios", "user.create", actor, {"user_id": user_id, "org_unit": desired_code})

add_audit("usuarios", "user.update", actor, {
    "user_id": user_id,
    "changes_count": len(changes),
})
```

Esses eventos dão rastreabilidade para:

* quem criou/alterou usuários,
* quem mexeu em papéis de acesso.

### 3.3. Fileshare — uploads, links e remoções

Em `fileshare.py`, a automação usa `audit_log` para registrar:

* `uploaded` — upload autenticado inicial,
* `shared_link_created` — link público gerado,
* `downloaded_shared_link` — download via link,
* `deleted` — item removido (soft delete).

```python title="fileshare.py — upload e delete" showLineNumbers
db.audit_log(
    actor=user,
    action="uploaded",
    kind="fileshare",
    target_id=item_id,
    meta={"filename": file.filename, "size": size, "ttl": ttl, "has_secret": bool(secret)},
)

# ...

db.audit_log(
    actor=user,
    action="deleted",
    kind="fileshare",
    target_id=item_id,
    meta={"filename": r["filename"]},
)
```

### 3.4. Whoisonline — revogação de sessão

Na automação `whoisonline.py`, ao revogar uma sessão:

```python title="whoisonline.py — revogação de sessão" showLineNumbers
cur.execute(
    "UPDATE auth_sessions SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL",
    (session_id,),
)
try:
    add_audit(KIND, "revoke", actor, {"session_id": session_id})
except Exception:
    pass
```

Isso cria um trilho de auditoria para “quem derrubou qual sessão”.

---

## 4) Consulta e UI de auditoria

### 4.1. Painel de Controle (`controle.py`)

A automação `controle` expõe endpoints administrativos para visualizar e exportar auditoria:

* `GET /api/automations/controle/audits`
  → retorna uma página (`Page[AuditOut]`) de eventos normalizados.
* `GET /api/automations/controle/audits.csv`
  → exporta os mesmos eventos em CSV.

Modelo de saída `AuditOut`:

```python title="controle.py — AuditOut" showLineNumbers
class AuditOut(BaseModel):
    """
    Modelo de saída para eventos de auditoria exibidos na UI.
    """
    ts: Optional[datetime]        # timestamp (campo `at` ou similar)
    user_id: Optional[str]
    username: Optional[str]
    action: Optional[str]
    target_kind: Optional[str]    # automação origem
    target_id: Optional[str]      # ex.: submission id
    ip: Optional[str]
    user_agent: Optional[str]
    extra: Optional[Dict[str, Any]]
    # ...campos derivados para UI (descrições, labels, etc.)
```

Endpoint principal:

```python title="controle.py — list_audits_api" showLineNumbers
@router.get("/audits", response_model=Page[AuditOut])
def list_audits_api(
    kind: Optional[str] = Query(default=None),
    username: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    since: Optional[datetime] = Query(default=None),
    until: Optional[datetime] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """
    Lista eventos de auditoria com filtros e paginação.
    """
    # Internamente, usa db.list_audits(...) + filtros in-memory
    # para montar uma lista de AuditOut.
```

Filtros suportados:

* `kind` — automação (normalizado).
* `username` — substring ou CPF.
* `action` — substring da ação.
* `since` / `until` — intervalo temporal.
* `limit` / `offset` — paginação.

### 4.2. Endpoints específicos das automações

* `dfd.py`:

  * `GET /api/automations/dfd/audits` — lista auditorias só da automação DFD (apenas para `admin`).
* `ferias.py`:

  * `GET /api/automations/ferias/audits` — similar, focado em férias.

Esses endpoints usam diretamente `db.list_audits(kind=KIND, ...)` e retornam JSON simples, pensado para consultas mais técnicas ou integrações futuras.

---

## 5) Boas práticas para novas automações/eventos

Quando você criar uma nova automação ou quiser auditar uma ação nova:

1. **Escolha bem o `kind`**

   * Use sempre o mesmo slug da automação (`KIND = "minha_automacao"`).
   * Para domínios mais amplos, pense em algo estável (`"accounts"`, `"usuarios"`, `"fileshare"`).

2. **Defina `action` como verbo curto e consistente**

   * Ex.: `submitted`, `running`, `completed`, `failed`,
     `download`, `download_denied`,
     `user.create`, `user.update`, `set_password`, etc.
   * Prefira `snake_case` ou `kebab-case` simples e previsível.

3. **Enriqueça `meta` com chaves padrão**

   * Para automations baseadas em submissão:

     * `sid`, `protocolo`, `numero`.
   * Para usuários:

     * `user_id`, `org_unit`, `changes_count`.
   * Para arquivos:

     * `filename`, `size`, `ttl`, `has_secret`, `bytes`.
   * Para segurança:

     * `session_id`, `ip`, `user_agent` (quando disponível).

4. **Não coloque dados sensíveis demais**

   * Evitar senhas, tokens, segredos, conteúdo completo de documentos.
   * Se necessário, logar apenas hashes, tamanhos, contagens ou amostras.

5. **Use `add_audit`/`audit_log` a partir da lógica de negócio**

   * Registre eventos em pontos de decisão chave (antes/depois de mutações e efeitos observáveis).
   * Trate erros de auditoria como **não bloqueantes** (como o código já faz: loga, mas não falha a requisição principal).

:::tip Dica
Se você não tem certeza se algo merece auditoria, pergunte:

> *“Se isso der problema daqui 6 meses, essa linha de audit ajudaria a responder ‘quem fez o quê e por quê’?”*
> Se a resposta for “sim”, provavelmente vale registrar.
> :::

---

## 6) Exemplos práticos (cURL / TS / Python)

### 6.1. cURL — buscando auditoria pelo painel de controle

```bash title="Listando auditoria de DFD pelo painel de controle" showLineNumbers
# Exige papel coordenador/admin ou superuser
curl -X GET \
  -H "Cookie: session=<cookie-válido>" \
  "http://localhost:8000/api/automations/controle/audits?kind=dfd&action=download&limit=20"
```

Resposta simplificada:

```json title="Exemplo de resposta (resumida)" showLineNumbers
{
  "items": [
    {
      "ts": "2025-11-21T14:15:00Z",
      "username": "Fulano Exemplo",
      "action": "download",
      "target_kind": "dfd",
      "target_id": "a1b2c3...",
      "ip": "10.0.0.5",
      "extra": {
        "sid": "a1b2c3...",
        "filename": "dfd_2025-001.pdf",
        "bytes": 123456,
        "fmt": "pdf"
      }
    }
  ],
  "limit": 20,
  "offset": 0,
  "total": 1
}
```

### 6.2. TypeScript — consumindo auditoria no Host

```ts title="Hook simples para consumir /controle/audits" showLineNumbers
type AuditItem = {
  ts?: string;
  user_id?: string;
  username?: string;
  action?: string;
  target_kind?: string;
  target_id?: string;
  ip?: string;
  user_agent?: string;
  extra?: Record<string, unknown>;
};

type AuditPage = {
  items: AuditItem[];
  limit: number;
  offset: number;
  total?: number;
};

export async function fetchControlAudits(params: {
  kind?: string;
  username?: string;
  action?: string;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}): Promise<AuditPage> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null) qs.set(k, String(v));
  }

  const res = await fetch(`/api/automations/controle/audits?${qs.toString()}`, {
    method: "GET",
    credentials: "include",
  });

  if (!res.ok) {
    throw new Error(`Falha ao buscar auditoria: ${res.status}`);
  }
  return (await res.json()) as AuditPage;
}
```

### 6.3. Python — relatório ad-hoc em linha de comando

```python title="Relatório rápido de auditoria (admin)" showLineNumbers
import os
from app.db import list_audits  # type: ignore[import-not-found]

# Ajuste conforme seu ambiente local
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://portal:portaldev@localhost:5432/portal",
)

def main() -> None:
    audits = list_audits(kind="dfd", limit=50)
    for a in audits:
        print(f"[{a['at']}] {a['kind']} {a['action']} {a.get('actor_nome')} {a.get('meta')}")

if __name__ == "__main__":
    main()
```

---

> _Criado em 2025-12-01_