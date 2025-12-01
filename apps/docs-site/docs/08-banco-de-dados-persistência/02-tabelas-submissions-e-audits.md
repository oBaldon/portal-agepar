---
id: tabelas-submissions-e-audits
title: "Tabelas submissions e audits"
sidebar_position: 2
---

As automações do Portal AGEPAR se apoiam em **duas tabelas centrais** de persistência:

- `submissions` — cada execução/solicitação de uma automação.
- `automation_audits` — trilha de auditoria dos eventos relacionados a essas execuções.

> Apesar do nome desta página falar em **“audits”**, o nome real da tabela é
> `automation_audits`. Em versões antigas do plano existiam referências a
> `auth_logs` em `infra/sql/001_init_auth_logs.sql` e `099_test_auth_logs.sql`,
> mas o repositório atual consolidou tudo em:
> `apps/bff/app/db.py` (schema em código) e `infra/sql/init_db.sql` (schema
> geral de Postgres).

> Referências principais no repositório:  
> `apps/bff/app/db.py` (schema e helpers de DB)  
> `apps/bff/app/main.py` (chamada de `init_db` no startup)  
> `apps/bff/app/automations/*.py` (uso de `insert_submission`, `update_submission`, `add_audit`, `list_audits`)  

---

## 1) Papel das tabelas no fluxo das automações

De forma simplificada:

- **`submissions`** guarda o “estado atual” de cada solicitação de automação:
  - quem pediu,
  - qual automação (`kind`) e versão,
  - payload de entrada,
  - status (`queued`, `running`, `done`, `error`),
  - resultado (quando concluída) ou mensagem de erro.
- **`automation_audits`** guarda o **histórico de eventos**:
  - quando a submissão foi criada, processada, concluída, falhou, baixada, rejeitada, etc.
  - cada linha é atômica e imutável.

Visão de alto nível:

```mermaid
erDiagram
  submissions {
    text        id PK
    text        kind
    text        version
    text        actor_cpf
    text        actor_nome
    text        actor_email
    jsonb       payload
    text        status
    jsonb       result
    text        error
    timestamptz created_at
    timestamptz updated_at
  }

  automation_audits {
    bigserial   id PK
    timestamptz at
    text        actor_cpf
    text        actor_nome
    text        kind
    text        action
    jsonb       meta
  }

  submissions ||--o{ automation_audits : "eventos relacionados (por meta.sid)"
````

> **Importante:** não existe hoje uma FK explícita entre `automation_audits`
> e `submissions`. A ligação é feita **por convenção**, via campo `sid` dentro de
> `meta` (quando aplicável).

---

## 2) Tabela `submissions` — modelo de execução das automações

### 2.1. Campos principais

Trecho do schema em `apps/bff/app/db.py`:

```sql title="apps/bff/app/db.py (trecho do init_db)" showLineNumbers
CREATE TABLE IF NOT EXISTS submissions (
  id           TEXT PRIMARY KEY,
  kind         TEXT NOT NULL,
  version      TEXT NOT NULL,
  actor_cpf    TEXT,
  actor_nome   TEXT,
  actor_email  TEXT,
  payload      JSONB NOT NULL,
  status       TEXT NOT NULL,
  result       JSONB,
  error        TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Campo a campo:**

* `id` (`TEXT PRIMARY KEY`)

  * Identificador único da submissão (UUID gerado em Python quando não informado).
* `kind` (`TEXT NOT NULL`)

  * Slug da automação: `"dfd"`, `"ferias"`, `"form2json"`, etc.
* `version` (`TEXT NOT NULL`)

  * Versão do “motor” da automação (ex.: `DFD_VERSION`, `FERIAS_VERSION`,
    `FORM2JSON_VERSION`).
* `actor_cpf`, `actor_nome`, `actor_email` (`TEXT`)

  * Quem disparou a automação.
  * Preenchidos a partir do usuário autenticado em `app/auth`.
* `payload` (`JSONB NOT NULL`)

  * Corpo de entrada da automação, **normalizado** pelos modelos Pydantic.
* `status` (`TEXT NOT NULL`)

  * Situação atual da submissão (ver seção abaixo).
* `result` (`JSONB`)

  * Saída da automação (documentos gerados, dados consolidados, etc.).
* `error` (`TEXT`)

  * Mensagem de erro “human readable” quando a submissão falha.
* `created_at`, `updated_at` (`TIMESTAMPTZ`)

  * Datas de criação e última alteração, sempre em UTC.
  * `updated_at` é mantido por uma trigger `BEFORE UPDATE` (`touch_updated_at()`).

### 2.2. Status da submissão e fluxo de estados

Foi criada uma constraint de integridade específica:

```sql title="Constraint de status (init_db)" showLineNumbers
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'chk_submissions_status'
    AND conrelid = 'submissions'::regclass
  ) THEN
    ALTER TABLE submissions
      ADD CONSTRAINT chk_submissions_status
      CHECK (status IN ('queued','running','done','error'));
  END IF;
END$$;
```

Ou seja, os status permitidos são:

* `queued` — submissão recém-criada, aguardando processamento em background.
* `running` — automação em execução (já saiu da fila).
* `done` — execução concluída com sucesso; `result` deve estar preenchido.
* `error` — execução falhou; `error` deve ter mensagem útil para o cliente.

Fluxo típico:

```mermaid
stateDiagram-v2
    [*] --> queued

    queued --> running : worker/background task inicia
    running --> done   : processamento OK
    running --> error  : exceção/inconsistência

    done --> done
    error --> error
```

> **Boas práticas:**
>
> * Não “reciclar” a mesma submissão mudando o payload; crie uma **nova** submissão.
> * Sempre atualizar `status` para `error` com uma mensagem clara em `error` quando
>   a automação não conseguir completar o trabalho.

### 2.3. Índices em `submissions`

No mesmo `init_db` são criados índices para dar suporte a consultas típicas:

```sql title="Índices principais em submissions" showLineNumbers
CREATE INDEX IF NOT EXISTS ix_submissions_created_at
  ON submissions (created_at DESC);

CREATE INDEX IF NOT EXISTS ix_submissions_kind_created
  ON submissions (kind, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_submissions_actor_cpf_created
  ON submissions (actor_cpf, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_submissions_actor_email_created
  ON submissions (actor_email, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_submissions_kind_actor_cpf_created
  ON submissions (kind, actor_cpf, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_submissions_kind_actor_email_created
  ON submissions (kind, actor_email, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_submissions_kind_status_created
  ON submissions (kind, status, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_submissions_payload_gin
  ON submissions USING GIN (payload);

CREATE INDEX IF NOT EXISTS ix_submissions_result_gin
  ON submissions USING GIN (result);

CREATE INDEX IF NOT EXISTS ix_submissions_kind_payload_numero
  ON submissions (kind, (payload->>'numero'));

CREATE INDEX IF NOT EXISTS ix_submissions_kind_payload_protocolo
  ON submissions (kind, (payload->>'protocolo'));
```

Esses índices suportam:

* **Listar rapidamente** últimas submissões globais ou de uma automação específica.
* Filtrar por ator (CPF/email) e por status.
* Consultar por campos específicos do payload (`numero`, `protocolo`).
* Rodar buscas mais ricas em `payload`/`result` via GIN em JSONB.

### 2.4. Helpers Python para trabalhar com `submissions`

`apps/bff/app/db.py` expõe funções utilitárias:

* `insert_submission(sub: dict) -> None`

  * Gera `id` se não existir.
  * Converte `payload`/`result` para `Json` (psycopg) quando necessário.
  * Faz o `INSERT` na tabela `submissions`.
* `update_submission(id: str, **fields) -> None`

  * Atualiza campos específicos (incluindo `status`, `result`, `error`).
  * Mantém `updated_at` atualizado via trigger.
* `get_submission(id: str) -> Optional[dict]`

  * Retorna uma submissão como `dict` ou `None` se não existir.
* `list_submissions(...)`

  * Lista submissões por ator autenticado (CPF/email), com filtros opcionais.
* `list_submissions_admin(...)`

  * Lista submissões para uso administrativo, com filtros por `kind`, `status` e `username`.

Trecho simplificado:

```python title="Uso típico em uma automação (ex.: form2json/dfd/ferias)" showLineNumbers
from app.db import insert_submission, update_submission, get_submission, list_submissions, add_audit

def criar_submissao(kind: str, version: str, actor: dict, payload: dict) -> str:
    sub = {
        "kind": kind,
        "version": version,
        "actor_cpf": actor.get("cpf"),
        "actor_nome": actor.get("nome") or actor.get("name"),
        "actor_email": actor.get("email"),
        "payload": payload,
        "status": "queued",
    }
    insert_submission(sub)
    return sub["id"]
```

---

## 3) Tabela `automation_audits` — trilha de auditoria

### 3.1. Campos principais

Trecho do schema em `db.py`:

```sql title="Tabela automation_audits (init_db)" showLineNumbers
CREATE TABLE IF NOT EXISTS automation_audits (
  id         BIGSERIAL PRIMARY KEY,
  at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor_cpf  TEXT,
  actor_nome TEXT,
  kind       TEXT NOT NULL,
  action     TEXT NOT NULL,
  meta       JSONB
);
```

* `id` (`BIGSERIAL PRIMARY KEY`)

  * Identificador da linha de auditoria.
* `at` (`TIMESTAMPTZ NOT NULL DEFAULT now()`)

  * Momento em que o evento foi registrado (UTC).
* `actor_cpf`, `actor_nome` (`TEXT`)

  * Ator associado ao evento (se houver).
* `kind` (`TEXT NOT NULL`)

  * Automação relacionada (`"dfd"`, `"ferias"`, `"form2json"`, etc.).
* `action` (`TEXT NOT NULL`)

  * Ação registrada (ex.: `"submitted"`, `"running"`, `"completed"`, `"failed"`,
    `"download"`, `"duplicate_rejected"`).
* `meta` (`JSONB`)

  * Metadados livres:

    * ID da submissão (`sid`),
    * protocolo,
    * formato de download (`fmt`),
    * detalhes de erro, etc.

Índice principal:

```sql title="Índice em automation_audits" showLineNumbers
CREATE INDEX IF NOT EXISTS ix_automation_audits_at
  ON automation_audits (at DESC);
```

> Em cenários futuros com muito volume, novos índices podem ser adicionados
> (ex.: por `kind`, por `actor_cpf`). Por enquanto, a combinação de ordenação por
> `at DESC` + filtros em memória tem sido suficiente.

### 3.2. Helpers Python para registrar e ler auditoria

`db.py` expõe:

* `add_audit(kind: str, action: str, actor: dict, meta: dict) -> None`

  * Função principal de gravação.
* `audit_log(actor: dict, action: str, kind: str, target_id: Optional[str] = None, meta: Optional[dict] = None) -> None`

  * Alias compatível que injeta `target_id` dentro de `meta`.
* `list_audits(kind: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[dict]`

  * Leitura de eventos para fins administrativos.

Uso típico (ex.: em `form2json.py`, `dfd.py`, `ferias.py`):

```python title="Exemplo de uso de add_audit em uma automação" showLineNumbers
from app.db import add_audit

KIND = "dfd"

def registrar_submissao(user: dict, sid: str, protocolo: str) -> None:
    add_audit(
        KIND,
        "submitted",
        user,
        {"sid": sid, "protocolo": protocolo},
    )

def registrar_erro(user: dict, sid: str, error: str) -> None:
    add_audit(
        KIND,
        "failed",
        user,
        {"sid": sid, "error": error},
    )
```

Valores de `action` que aparecem hoje no código:

* `"submitted"` — submissão criada.
* `"running"` — processamento iniciado.
* `"completed"` — processamento concluído com sucesso.
* `"failed"` — falha em alguma etapa.
* `"download"` — usuário baixou algum artefato (JSON, DOCX, ZIP, etc.).
* `"duplicate_rejected"` — submissão rejeitada por duplicidade (por exemplo,
  quando já existe um DFD com mesmo `numero` ou `protocolo`).

---

## 4) Como as automações combinam `submissions` e `automation_audits`

### 4.1. Fluxo típico de uma automação “clássica”

1. **Recebe um POST `/submit`**

   * Valida o corpo com Pydantic.
   * Normaliza campos (datas, números, flags).
2. **Grava `submissions`**

   * Chama `insert_submission(...)` com `status="queued"`.
   * Cria um registro imutável de “intenção de execução”.
3. **Registra auditoria de submissão**

   * Chama `add_audit(kind, "submitted", actor, {"sid": sid, ...})`.
4. **Background task processa a submissão**

   * Atualiza `submissions` com `status="running"`.
   * Em caso de sucesso:

     * salva o resultado em `result`,
     * marca `status="done"`,
     * registra `add_audit(kind, "completed", actor, {"sid": sid, ...})`.
   * Em caso de erro:

     * marca `status="error"` com uma mensagem em `error`,
     * registra `add_audit(kind, "failed", actor, {"sid": sid, "error": ...})`.
5. **Downloads e ações subsequentes**

   * Endpoints como `/submissions/{sid}/download` chamam `get_submission(...)`
     e, se bem-sucedidos, registram `add_audit(kind, "download", user, {"sid": sid, "fmt": fmt, ...})`.

### 4.2. Endpoints padrão para consumo via API/Host

Os módulos `dfd`, `ferias` e `form2json` expõem um conjunto de rotas muito semelhante:

* `GET /api/automations/<kind>/submissions`

  * Lista submissões do usuário (ou administrativas, dependendo do módulo).
* `GET /api/automations/<kind>/submissions/{sid}`

  * Detalha uma submissão específica.
* `POST /api/automations/<kind>/submissions/{sid}/download[/{fmt}]`

  * Baixa resultado (por exemplo, JSON, DOCX, ZIP), com auditoria de download.
* `POST /api/automations/<kind>/submit`

  * Cria submissão + agenda background task.

> A lógica interna desses endpoints é toda construída **em cima de**
> `insert_submission`, `update_submission`, `get_submission`,
> `list_submissions` e `add_audit`.

---

## 5) Exemplos práticos (cURL/TS/Python)

### 5.1. cURL — listar submissões de uma automação

```bash title="Listando submissões de DFD (ex.: administrativo)" showLineNumbers
curl -X GET \
  -H "Cookie: session=<cookie válido>" \
  "http://localhost:8000/api/automations/dfd/submissions?status=done&limit=20"
```

Resposta típica (resumida):

```json title="Exemplo de resposta (resumida)"
[
  {
    "id": "a1b2c3...",
    "kind": "dfd",
    "version": "1.2.3",
    "actor_cpf": "00000000000",
    "actor_nome": "Fulano Example",
    "payload": { "numero": "2025-001", "protocolo": "12345/2025" },
    "status": "done",
    "result": { "protocolo": "12345/2025", "arquivo": "..." },
    "error": null,
    "created_at": "2025-11-20T10:00:00Z",
    "updated_at": "2025-11-20T10:01:30Z"
  }
]
```

### 5.2. TypeScript — consumindo submissões no Host

```ts title="Hook simples para listar submissões no Host" showLineNumbers
type Submission = {
  id: string;
  kind: string;
  version: string;
  status: "queued" | "running" | "done" | "error";
  created_at: string;
  updated_at: string;
  payload: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  error?: string | null;
};

export async function fetchDfdSubmissions(): Promise<Submission[]> {
  const res = await fetch("/api/automations/dfd/submissions", {
    method: "GET",
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Falha ao buscar submissões: ${res.status}`);
  }
  return (await res.json()) as Submission[];
}
```

### 5.3. Python — relatório simples de auditoria

```python title="Script ad-hoc para inspecionar automation_audits" showLineNumbers
import os
from app.db import list_audits  # type: ignore[import-not-found]

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://portal:portaldev@localhost:5432/portal",
)

def main() -> None:
    # Audits da automação DFD
    audits = list_audits(kind="dfd", limit=20)
    for a in audits:
        print(f"[{a['at']}] {a['kind']} {a['action']} {a.get('actor_nome')} {a.get('meta')}")

if __name__ == "__main__":
    main()
```

---

> _Criado em 2025-12-01_