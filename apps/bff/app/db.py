# app/db.py — versão Postgres (unifica storage das automações)
from __future__ import annotations
import os
import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não configurada para Postgres")

# ----------------------------- conexões -----------------------------
def _pg():
    """
    Abre uma conexão Postgres com autocommit (uso simples por helper).
    Observação: se precisar de pool/conexão persistente, mover para um pool global.
    """
    return psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row)

# ----------------------------- schema -------------------------------
def init_db() -> None:
    """
    Cria tabelas e índices idempotentes (IF NOT EXISTS).
    Inclui índices compostos otimizados para consultas por kind+ator.
    Aplica reforços de robustez (CHECK de status) e índices adicionais.
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

    -- Índices básicos
    CREATE INDEX IF NOT EXISTS ix_submissions_created_at            ON submissions (created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_submissions_kind_created          ON submissions (kind, created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_submissions_actor_cpf_created     ON submissions (actor_cpf, created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_submissions_actor_email_created   ON submissions (actor_email, created_at DESC);

    -- Índices compostos (consultas típicas: kind + ator + ordenação)
    CREATE INDEX IF NOT EXISTS ix_submissions_kind_actor_cpf_created
      ON submissions (kind, actor_cpf, created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_submissions_kind_actor_email_created
      ON submissions (kind, actor_email, created_at DESC);

    CREATE INDEX IF NOT EXISTS ix_automation_audits_at ON automation_audits (at DESC);

    -- Trigger de atualização de updated_at
    CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
    BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_submissions_touch ON submissions;
    CREATE TRIGGER trg_submissions_touch
    BEFORE UPDATE ON submissions
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

    -- Robustez: CHECK constraint para status permitido (queued|running|done|error).
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

    -- Índice adicional para consultas por status (ex.: dashboards/filas).
    CREATE INDEX IF NOT EXISTS ix_submissions_kind_status_created
      ON submissions (kind, status, created_at DESC);

    -- Índices GIN opcionais para consultas por campos dentro de JSONB (payload/result).
    CREATE INDEX IF NOT EXISTS ix_submissions_payload_gin ON submissions USING GIN (payload);
    CREATE INDEX IF NOT EXISTS ix_submissions_result_gin  ON submissions USING GIN (result);
    """
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(sql)

# ----------------------------- utils --------------------------------
def _to_json_value(v: Any) -> Optional[Json]:
    """Aceita dict/list/str JSON; retorna psycopg.Json ou None (para colunas JSONB)."""
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return Json(v)
    if isinstance(v, str):
        try:
            return Json(json.loads(v))
        except Exception:
            # Em casos raros, manter como string JSON (será serializada com aspas)
            return Json(v)
    return Json(v)

# ----------------------------- API ----------------------------------
def insert_submission(sub: Dict[str, Any]) -> None:
    sub = dict(sub)  # cópia defensiva
    # Garante ID quando não informado (coluna é NOT NULL e PRIMARY KEY)
    if not sub.get("id"):
        sub["id"] = str(uuid4())
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO submissions
              (id, kind, version, actor_cpf, actor_nome, actor_email, payload, status, result, error)
            VALUES
              (%(id)s, %(kind)s, %(version)s, %(actor_cpf)s, %(actor_nome)s, %(actor_email)s,
               %(payload)s, %(status)s, %(result)s, %(error)s)
            """,
            {
                **sub,
                "payload": _to_json_value(sub.get("payload") | {} if isinstance(sub.get("payload"), dict) else (sub.get("payload") or {})),
                "result": _to_json_value(sub.get("result")),
            },
        )

def update_submission(id: str, **fields: Any) -> None:
    if not fields:
        return
    # normaliza json
    if "payload" in fields:
        fields["payload"] = _to_json_value(fields["payload"])
    if "result" in fields:
        fields["result"] = _to_json_value(fields["result"])

    sets = []
    params: Dict[str, Any] = {"id": id}
    for k, v in fields.items():
        sets.append(f"{k} = %({k})s")
        params[k] = v
    sets.append("updated_at = now()")

    q = f"UPDATE submissions SET {', '.join(sets)} WHERE id = %(id)s"
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(q, params)

def get_submission(id: str) -> Optional[Dict[str, Any]]:
    with _pg() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM submissions WHERE id = %s", (id,))
        row = cur.fetchone()
        return dict(row) if row else None

def list_submissions(
    kind: Optional[str] = None,
    actor_cpf: Optional[str] = None,
    actor_email: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Lista submissões do ator autenticado. Segurança: exige CPF ou e-mail.
    Em geral chamamos com kind=... para telas por automação.
    """
    if not actor_cpf and not actor_email:
        raise RuntimeError("Identificador do ator ausente (cpf/email).")

    params: List[Any] = []
    where = ["1=1"]
    if kind:
        where.append("kind = %s")
        params.append(kind)
    if actor_cpf:
        where.append("actor_cpf = %s")
        params.append(actor_cpf)
    else:
        where.append("actor_email = %s")
        params.append(actor_email)

    where_sql = " AND ".join(where)
    sql = f"""
        SELECT * FROM submissions
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() or []
        return [dict(r) for r in rows]

def list_submissions_admin(
    kind: Optional[str] = None,
    username: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Lista submissões para painéis administrativos (ex.: diretores).
    Não exige actor_* e aceita filtros livres: kind, username (nome/email/CPF) e status.
    """
    where: List[str] = ["1=1"]
    params: List[Any] = []
    if kind:
        where.append("kind = %s")
        params.append(kind)
    if status:
        where.append("LOWER(status) = LOWER(%s)")
        params.append(status)
    if username:
        # busca em nome, email e CPF (ILIKE para nome/email; LIKE para cpf)
        where.append("("
                     "actor_nome ILIKE %s OR "
                     "actor_email ILIKE %s OR "
                     "actor_cpf LIKE %s"
                     ")")
        term = f"%{username}%"
        params.extend([term, term, f"%{username}%"])

    sql = f"""
        SELECT *
        FROM submissions
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() or []
        return [dict(r) for r in rows]

def add_audit(kind: str, action: str, actor: Dict[str, Any], meta: Dict[str, Any]) -> None:
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO automation_audits (actor_cpf, actor_nome, kind, action, meta)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                actor.get("cpf"),
                actor.get("nome") or actor.get("name"),  # aceita 'nome' (mock) e 'name' (login real)
                kind,
                action,
                _to_json_value(meta),
            ),
        )

def list_audits(kind: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
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
