---
id: sqlite-no-startup-init_db
title: "SQLite no startup (init_db)"
sidebar_position: 1
---

> Apesar do nome histórico desta página falar em **SQLite**, a versão atual do Portal AGEPAR já utiliza **PostgreSQL** no ambiente dev (e mira produção).  
> O conceito continua o mesmo: no **startup** do BFF, a função `init_db()` garante que o schema mínimo das automações exista.

Esta página explica:

- Onde vive a função `init_db()` e **quando** ela é executada.
- Como ela usa `DATABASE_URL` para conectar ao banco.
- O que é criado no banco (submissions, automation_audits, fileshare_items).
- Como isso impacta o fluxo de automações na prática.

---

## 1) Onde o `init_db()` vive e como é chamado

A função mora em:

- `apps/bff/app/db.py`

Logo no início do arquivo:

```python title="apps/bff/app/db.py" showLineNumbers
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não configurada para Postgres")


def _pg():
    """
    Abre uma conexão Postgres com autocommit, usando row_factory `dict_row`.
    """
    return psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row)
````

Pontos importantes:

* O BFF **não sobe** se `DATABASE_URL` não estiver configurada → falha rápida em ambiente quebrado.
* `_pg()` é o *factory* central de conexões Postgres; tudo passa por ele (inclusive o `init_db()`).

A ligação com o ciclo de vida do FastAPI está em `apps/bff/app/main.py`:

```python title="apps/bff/app/main.py" showLineNumbers
from app.db import init_db
from app.automations.dfd import DFD_VERSION as DFD_VER
from app.automations.ferias import FERIAS_VERSION as FERIAS_VER

@APP.on_event("startup")
def _startup() -> None:
    """
    Hook de inicialização do aplicativo.

    Efeitos colaterais
    ------------------
    - Executa `init_db()` para garantir o schema Postgres.
    - Loga versões dos motores DFD e FÉRIAS.
    """
    init_db()
    logger.info("DB initialized (Postgres)")
    logger.info("DFD engine version: %s", DFD_VER)
    logger.info("FERIAS engine version: %s", FERIAS_VER)
```

Ou seja:

* **Toda vez que um processo do BFF inicia**, o FastAPI dispara `_startup()`.
* `_startup()` chama `init_db()` **uma vez por processo**, antes de atender qualquer requisição.
* Se houver erro de conexão ou de DDL, o processo cai — o que é desejável para não rodar com banco inconsistente.

### 1.1. Diagrama (Mermaid) — visão rápida

```mermaid
sequenceDiagram
    participant U as Dev/Infra
    participant Proc as Processo FastAPI (BFF)
    participant DB as Postgres

    U->>Proc: docker compose up / uvicorn app.main:APP
    activate Proc
    Proc->>Proc: evento "startup"
    Proc->>Proc: _startup()
    Proc->>DB: init_db() (DDL idempotente)
    DB-->>Proc: OK (tabelas/índices garantidos)
    Proc-->>U: /health => {"status":"ok"}
    deactivate Proc
```

---

## 2) O que o `init_db()` faz exatamente

Ainda em `apps/bff/app/db.py`, a função:

```python title="apps/bff/app/db.py" showLineNumbers
def init_db() -> None:
    """
    Cria tabelas e índices idempotentes (IF NOT EXISTS) e garante:
    - submissions: índices por data, kind, ator e status; trigger de `updated_at`;
      CHECK de `status` em {'queued','running','done','error'};
      índices GIN para JSONB (payload/result) e índices por expressão.
    - automation_audits: índice por timestamp.
    - fileshare_items: índices por criação, expiração, dono e deleted_at.
    """
    sql = """
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

    CREATE TABLE IF NOT EXISTS automation_audits (
      id         BIGSERIAL PRIMARY KEY,
      at         TIMESTAMPTZ NOT NULL DEFAULT now(),
      actor_cpf  TEXT,
      actor_nome TEXT,
      kind       TEXT NOT NULL,
      action     TEXT NOT NULL,
      meta       JSONB
    );

    CREATE TABLE IF NOT EXISTS fileshare_items (
      id           TEXT PRIMARY KEY,
      filename     TEXT NOT NULL,
      size         BIGINT NOT NULL,
      content_type TEXT,
      path         TEXT NOT NULL,
      owner_id     TEXT,
      owner_name   TEXT,
      created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
      expires_at   TIMESTAMPTZ NOT NULL,
      secret_hash  TEXT,
      downloads    INTEGER NOT NULL DEFAULT 0,
      deleted_at   TIMESTAMPTZ
    );

    -- (demais índices, constraints e triggers)
    """
    with _pg() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
```

Resumo prático:

* **Idempotência**: usa `CREATE TABLE IF NOT EXISTS` e `CREATE INDEX IF NOT EXISTS`, então é seguro rodar quantas vezes for necessário.
* Cria 3 tabelas centrais para as automações:

  1. `submissions` — cada execução de automação.
  2. `automation_audits` — trilha de auditoria de ações.
  3. `fileshare_items` — metadados de arquivos temporários (fileshare).

### 2.1. Tabela `submissions` (núcleo das automations)

Campos principais:

* `id` — `TEXT PRIMARY KEY` (gerado na camada Python com `uuid4()`).
* `kind` — slug da automação (`"form2json"`, `"dfd"`, `"ferias"`, etc.).
* `version` — versão do motor da automação (ex.: `FERIAS_VERSION`).
* `actor_cpf`, `actor_nome`, `actor_email` — quem disparou a automação.
* `payload` — `JSONB` com a entrada normalizada.
* `status` — `TEXT` com **CHECK** `'queued' | 'running' | 'done' | 'error'`.
* `result` — `JSONB` com o resultado (quando `status = 'done'`).
* `error` — mensagem de erro (quando `status = 'error'`).
* `created_at`, `updated_at` — timestamps (`TIMESTAMPTZ`).

Índices e regras importantes (resumidos):

* Índices por:

  * `created_at` (ordem decrescente).
  * `kind + created_at`.
  * `kind + status + created_at`.
  * `kind + actor_cpf + created_at`.
  * `kind + actor_email + created_at`.
* Índices GIN para:

  * `payload` (consultas em campos de entrada).
  * `result` (consultas em campos de saída).
* Trigger `touch_updated_at`:

  * Função `touch_updated_at()` em PL/pgSQL.
  * Trigger `trg_submissions_touch` em `BEFORE UPDATE` → mantém `updated_at` sempre sincronizado.

Esses índices permitem:

* Listar rapidamente “últimas submissões” por automação.
* Filtrar por ator (CPF/email) + tipo de automação.
* Futuras consultas mais ricas em cima de JSON (payload/result).

### 2.2. Tabela `automation_audits`

Serve para registrar **eventos de auditoria** das automations:

* `kind` — automação relacionada.
* `action` — string curta identificando a ação (`"submit"`, `"download"`, etc.).
* `meta` — `JSONB` com detalhes do evento.
* Índice principal em `at DESC` (timestamp).

Ela é utilizada pelos módulos que chamam helpers de auditoria em `db.py` (ex.: DFD, Férias, Controle).

### 2.3. Tabela `fileshare_items`

Usada pelo módulo `fileshare` para expor downloads temporários:

* Armazena `filename`, `size`, `content_type` e `path` (no filesystem).
* Campos para controle:

  * `owner_id`, `owner_name` — responsável pelo arquivo.
  * `created_at`, `expires_at` — janelas de validade.
  * `secret_hash` — token de segurança.
  * `downloads` — contador de downloads.
  * `deleted_at` — marcação de soft delete.
* Índices de suporte:

  * por criação (`created_at`),
  * por expiração (`expires_at`),
  * por dono (`owner_id` + `created_at`),
  * por `deleted_at` (para limpeza).

Há também funções em `db.py` que fazem:

* Limpeza periódica (`cleanup_expired_files`) apagando registros vencidos e removendo arquivos do disco.
* CRUD básico para o módulo fileshare.

---

## 3) Como isso conversa com as automations

Do ponto de vista das automations (`apps/bff/app/automations/*.py`):

* Elas **não criam tabelas diretamente**.
* Em vez disso, usam helpers expostos por `db.py`:

  * `insert_submission(...)`
  * `update_submission(id, status=..., result=..., error=...)`
  * `get_submission(id)`
  * `list_submissions(...)`
  * `add_audit(...)` (nome exato pode variar, mas a ideia é essa camada de serviço).

Fluxo típico de uma automação (ex.: `form2json`, `dfd`, `ferias`):

1. Endpoint `POST /api/automations/{kind}/submit`:

   * Valida o payload com Pydantic.
   * Monta um dicionário `sub = {id, kind, version, actor_*, payload, status="queued"}`.
   * Chama `insert_submission(sub)`.
2. Um `BackgroundTasks` processa a submissão:

   * Atualiza `status` para `"running"`.
   * Gera output; ao final faz `status="done"` + `result=...`.
   * Em caso de erro: `status="error"` + `error="mensagem"`.
3. A automação registra eventos relevantes em `automation_audits`.

Tudo isso assume que, **quando o processo de API começou**, `init_db()` já garantiu:

* Tabela `submissions` presente.
* Tabela `automation_audits` presente.
* Tabela `fileshare_items` presente.
* Índices/constraints/triggers criados.

---

## 4) Ambiente dev e `DATABASE_URL`

Em dev, o stack com Postgres é definido em:

* `infra/docker-compose.pg.yml`

Trecho relevante (simplificado):

```yaml title="infra/docker-compose.pg.yml" showLineNumbers
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${PGDATABASE:-portal}
      POSTGRES_USER: ${PGUSER:-portal}
      POSTGRES_PASSWORD: ${PGPASSWORD:-portaldev}
    # ...

  bff:
    build:
      context: ../apps/bff
      dockerfile: Dockerfile.dev
    environment:
      DATABASE_URL: "postgresql://${PGUSER:-portal}:${PGPASSWORD:-portaldev}@postgres:5432/${PGDATABASE:-portal}"
    depends_on:
      postgres:
        condition: service_healthy
```

Consequências:

* O BFF sempre enxerga o banco Postgres via `DATABASE_URL`.
* Quando o container do BFF sobe, o `startup` do FastAPI chama `init_db()` usando essa URL.
* Em ambientes que **não** usam Postgres (ex.: experimentos locais antigos com SQLite), seria necessário:

  * ou adaptar `DATABASE_URL` para apontar para um SQLite em modo compatível (não recomendado),
  * ou manter uma branch separada (cenário histórico, não o atual).

Na prática, o título desta página deveria evoluir para algo como:

> “PostgreSQL no startup (init_db)”

…mas mantivemos o identificador histórico `sqlite-no-startup-init_db` para não quebrar links internos e o plano original.

---

## 5) Exemplos práticos (cURL, TS, Python)

### 5.1. Smoke-test via cURL

Após subir o stack com Postgres:

```bash title="Verificando se o BFF subiu e rodou init_db()"
# Subir serviços (exemplo)
cd infra
docker compose -f docker-compose.pg.yml up -d --build

# Checar saúde do BFF
curl -s http://localhost:8000/health
# -> {"status":"ok"}

# Ver metadados de versão/ambiente (útil para confirmar ENV)
curl -s http://localhost:8000/version | jq .
```

Se `DATABASE_URL` estiver incorreta ou o Postgres fora do ar:

* O container do BFF provavelmente não ficará "healthy".
* As chamadas a `/health` e `/version` não vão responder.

### 5.2. Exemplo TypeScript (Host chamando o BFF)

Mesmo que o Host não fale diretamente com o banco, ele pode expor um “card de status” mostrando se a API está de pé:

```ts title="Exemplo simples de fetch no Host" showLineNumbers
async function getApiVersion() {
  const res = await fetch("/api/version", {
    method: "GET",
    credentials: "include",
  });

  if (!res.ok) {
    throw new Error(`Falha ao obter versão: ${res.status}`);
  }

  const data = await res.json() as {
    app: string;
    env: string;
    dfd_version: string;
    ferias_version: string;
  };

  return data;
}

// Em um componente React:
// const { app, env } = await getApiVersion();
```

Esse tipo de chamada é útil para:

* Mostrar um “badge” de ambiente (dev/homolog/produção).
* Confirmar rapidamente que o BFF está rodando → logo, que o `init_db()` já foi executado.

### 5.3. Exemplo Python — rodando `init_db()` manualmente

Em cenários de manutenção/migração, você pode querer rodar `init_db()` manualmente (por exemplo, em um job de CI):

```python title="Script utilitário para garantir schema" showLineNumbers
import os

# Configure a variável de ambiente, se necessário
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://portal:portaldev@localhost:5432/portal",
)

from app.db import init_db  # type: ignore[import-not-found]

if __name__ == "__main__":
    init_db()
    print("Schema de automations garantido com sucesso.")
```

Esse script é **idempotente**:

* Pode ser executado em deploys, pipelines ou comandos manuais.
* Não apaga dados; apenas cria tabelas/índices/constraints ausentes.

---

> _Criado em 2025-12-01_
> _Atualizado para refletir a migração de SQLite (plano original) para PostgreSQL com `init_db()` no startup do BFF._
