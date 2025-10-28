---
id: scripts-de-bootstrap-e-init-do-db
title: "Scripts de bootstrap e init do DB"
sidebar_position: 4
---

O BFF usa **Postgres** (driver **psycopg**) definido em `apps/bff/app/db.py` para persistir:
- **submissions** — `kind`, `payload` (JSONB), `status`, `result` (JSONB), `error`, timestamps
- **audits** — `event`, `details` (JSONB), `submission_id`, timestamps
- **fileshare_items** — metadados de arquivos, `expires_at`, `deleted_at` e rotina de limpeza

O módulo concentra **DDL idempotente** (CREATE TABLE/INDEX IF NOT EXISTS), **helpers de CRUD** e **limpeza de expirados**.

---

## Variáveis de ambiente (BFF)

```dotenv
DATABASE_URL=postgresql://user:pass@localhost:5432/agepar
ENV=dev
LOG_LEVEL=INFO
SESSION_SECRET=dev-secret
# Em dev, se o Host estiver no Docker, inclua ambos:
CORS_ORIGINS=http://localhost:5173,http://host:5173
AUTH_MODE=local
AUTH_LEGACY_MOCK=0
````

> `DATABASE_URL` é **obrigatório** para subir o BFF.

---

## Bootstrap do schema (startup)

```py
from fastapi import FastAPI
from app import db  # apps/bff/app/db.py

APP = FastAPI()

@APP.on_event("startup")
def on_startup():
    try:
        db.init_db()  # cria tabelas/índices se não existirem
    except Exception as e:
        print(f"[ERROR] init_db: {e}")
```

---

## Exemplos (uso direto de psycopg)

```py
import os, psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

DATABASE_URL = os.getenv("DATABASE_URL")

def _pg():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def insert_submission(kind: str, payload: dict) -> int:
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO submissions (kind, payload, status)
               VALUES (%s, %s, %s) RETURNING id""",
            (kind, Json(payload), "queued"),
        )
        rid = cur.fetchone()["id"]
        conn.commit()
        return rid

def audit(event: str, details: dict, submission_id: int | None = None):
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO audits (event, details, submission_id) VALUES (%s, %s, %s)",
            (event, Json(details), submission_id),
        )
        conn.commit()
```

---

## Compose (db + bff + host)

```yaml
version: "3.9"
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: agepar
      POSTGRES_PASSWORD: agepar
      POSTGRES_DB: agepar
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]

  bff:
    build: { context: ./apps/bff }
    environment:
      DATABASE_URL: postgresql://agepar:agepar@db:5432/agepar
      ENV: dev
      LOG_LEVEL: INFO
      CORS_ORIGINS: http://localhost:5173,http://host:5173
      SESSION_SECRET: dev-secret
    depends_on: [db]
    ports: ["8000:8000"]
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    volumes: ["./apps/bff:/app"]

  host:
    build: { context: ./apps/host }
    ports: ["5173:5173"]
    command: pnpm dev --host
    volumes: ["./apps/host:/app"]

volumes:
  pgdata:
```

---

## cURLs de verificação

```bash
curl -i http://localhost:8000/api/docs
curl -s http://localhost:8000/catalog/dev | jq .
curl -s http://localhost:8000/api/eprotocolo/ping
```

---

## Limpeza de arquivos (fileshare_items)

O `db.py` expõe utilitários para:

* inserir itens com `expires_at`
* marcar **soft-delete** (`deleted_at`)
* **cleanup** periódico (remove expirados e arquivos no disco)

---

## Boas práticas

* **DDL idempotente**, **índices** (status e GIN em JSONB), **transações curtas**.
* **Observabilidade**: auditar `submit`, `completed`, `error`, `download`.
* **ENVs por ambiente**; nunca versionar segredos reais.

---

> _Criado em 2025-10-27 13:10:00_
