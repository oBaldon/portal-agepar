# app/db.py — versão Postgres (unifica storage das automações + fileshare)
from __future__ import annotations

"""
Camada de persistência para Postgres.

Propósito
---------
- Gerenciar conexões e schema (tabelas/índices/triggers) relacionados a:
  • submissions (execuções/solicitações das automações),
  • automation_audits (auditoria de ações),
  • fileshare_items (metadados de arquivos temporários).
- Expor helpers de CRUD e consultas frequentes (lista/obter/atualizar).
- Oferecer utilitários para JSON (psycopg.Json) e horários (UTC).

Referência
----------
- Banco de dados: PostgreSQL (psycopg 3).
- Serialização JSON: psycopg.types.json.Json (para colunas JSONB).
- Horário: timezone-aware (UTC) para timestamps de sistema.

Segurança & Efeitos colaterais
------------------------------
- Leitura de variável de ambiente `DATABASE_URL` (obrigatória).
- Acesso ao banco (criação de schema, inserts/updates/deletes/selects).
- Remoção de arquivos no filesystem durante limpeza do fileshare (best-effort).

Observações
-----------
- Lógica original preservada integralmente; apenas docstrings foram adicionadas,
  e comentários em linha substituídos por documentação.
"""

import os
import json
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pathlib import Path
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não configurada para Postgres")


def _pg():
    """
    Abre uma conexão Postgres com autocommit, usando row_factory `dict_row`.

    Retorna
    -------
    psycopg.Connection
        Conexão configurada para retornos como dicionários.
    """
    return psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row)


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

    CREATE INDEX IF NOT EXISTS ix_submissions_created_at            ON submissions (created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_submissions_kind_created          ON submissions (kind, created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_submissions_actor_cpf_created     ON submissions (actor_cpf, created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_submissions_actor_email_created   ON submissions (actor_email, created_at DESC);

    CREATE INDEX IF NOT EXISTS ix_submissions_kind_actor_cpf_created
      ON submissions (kind, actor_cpf, created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_submissions_kind_actor_email_created
      ON submissions (kind, actor_email, created_at DESC);

    CREATE INDEX IF NOT EXISTS ix_automation_audits_at ON automation_audits (at DESC);

    CREATE INDEX IF NOT EXISTS ix_fileshare_created_at ON fileshare_items (created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_fileshare_expires_at ON fileshare_items (expires_at DESC);
    CREATE INDEX IF NOT EXISTS ix_fileshare_owner      ON fileshare_items (owner_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_fileshare_deleted    ON fileshare_items (deleted_at, expires_at);

    CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
    BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_submissions_touch ON submissions;
    CREATE TRIGGER trg_submissions_touch
    BEFORE UPDATE ON submissions
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

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

    CREATE INDEX IF NOT EXISTS ix_submissions_kind_status_created
      ON submissions (kind, status, created_at DESC);

    CREATE INDEX IF NOT EXISTS ix_submissions_payload_gin ON submissions USING GIN (payload);
    CREATE INDEX IF NOT EXISTS ix_submissions_result_gin  ON submissions USING GIN (result);

    CREATE INDEX IF NOT EXISTS ix_submissions_kind_payload_numero
      ON submissions (kind, (payload->>'numero'));
    CREATE INDEX IF NOT EXISTS ix_submissions_kind_payload_protocolo
      ON submissions (kind, (payload->>'protocolo'));
    """
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(sql)


def _to_json_value(v: Any) -> Optional[Json]:
    """
    Converte valores Python em `psycopg.types.json.Json` para colunas JSONB.

    Regras
    ------
    - `None` → None
    - `dict`/`list` → Json(obj)
    - `str` → tenta fazer `json.loads`; em falha, mantém string como JSON
    - outros tipos → Json(valor)

    Retorna
    -------
    Optional[Json]
    """
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return Json(v)
    if isinstance(v, str):
        try:
            return Json(json.loads(v))
        except Exception:
            return Json(v)
    return Json(v)


def _utcnow() -> datetime:
    """
    Retorna o timestamp atual em UTC (timezone-aware).

    Retorna
    -------
    datetime
    """
    return datetime.now(timezone.utc)


def insert_submission(sub: Dict[str, Any]) -> None:
    """
    Insere uma submissão na tabela `submissions`.

    Observações
    -----------
    - Gera `id` UUID quando não informado.
    - Normaliza `payload` e `result` para JSONB.
    """
    sub = dict(sub)
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
    """
    Atualiza campos arbitrários de uma submissão por `id`.

    Parâmetros
    ----------
    id : str
        Identificador da submissão.
    **fields : Any
        Campos a atualizar; `payload`/`result` são normalizados para JSONB.
    """
    if not fields:
        return
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
    """
    Recupera uma submissão por `id`.

    Retorna
    -------
    dict | None
    """
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
    Lista submissões do ator autenticado (requer CPF ou e-mail).

    Parâmetros
    ----------
    kind : str | None
        Filtro por automação.
    actor_cpf : str | None
        CPF do ator.
    actor_email : str | None
        E-mail do ator.
    limit : int
        Quantidade de registros (padrão 50).
    offset : int
        Deslocamento para paginação.

    Retorna
    -------
    list[dict]
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
    Lista submissões para uso administrativo (sem exigir actor_*).

    Parâmetros
    ----------
    kind : str | None
        Filtro por automação.
    username : str | None
        Termo para nome/email/CPF.
    status : str | None
        Filtro por status.
    limit : int
        Quantidade de registros (padrão 100).
    offset : int
        Deslocamento para paginação.

    Retorna
    -------
    list[dict]
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
    """
    Registra um evento de auditoria em `automation_audits`.

    Parâmetros
    ----------
    kind : str
        Nome da automação.
    action : str
        Ação realizada (ex.: 'create', 'update').
    actor : dict
        Dados do ator (cpf, nome/name).
    meta : dict
        Metadados adicionais serializados como JSONB.
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


def audit_log(actor: Dict[str, Any], action: str, kind: str, target_id: Optional[str] = None, meta: Optional[Dict[str, Any]] = None) -> None:
    """
    Alias compatível para `add_audit`, com `target_id` opcional em `meta`.

    Parâmetros
    ----------
    actor : dict
        Ator (cpf/nome).
    action : str
        Ação.
    kind : str
        Automação.
    target_id : str | None
        Identificador do alvo (armazenado dentro de `meta`).
    meta : dict | None
        Metadados adicionais.
    """
    m = dict(meta or {})
    if target_id is not None:
        m.setdefault("target_id", target_id)
    add_audit(kind=kind, action=action, actor=actor, meta=m)


def list_audits(kind: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Lista eventos de auditoria.

    Parâmetros
    ----------
    kind : str | None
        Filtro opcional por automação.
    limit : int
        Quantidade (padrão 50).
    offset : int
        Deslocamento.

    Retorna
    -------
    list[dict]
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


def exists_submission_payload_value(kind: str, field: str, value: str) -> bool:
    """
    Verifica se existe submissão do `kind` cujo `payload[field] == value`.

    Parâmetros
    ----------
    kind : str
        Automação.
    field : str
        Campo dentro de `payload` (nível raiz).
    value : str
        Valor para comparação exata (case-sensitive).

    Retorna
    -------
    bool
    """
    if not kind or not field:
        return False
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM submissions WHERE kind = %s AND payload ->> %s = %s LIMIT 1",
            (kind, field, value),
        )
        return cur.fetchone() is not None


def fileshare_create(rec: Dict[str, Any]) -> None:
    """
    Cria metadados de arquivo temporário em `fileshare_items`.

    Parâmetros
    ----------
    rec : dict
        Deve conter: id, filename, size, content_type?, path, owner_id?, owner_name?,
        created_at (ISO), expires_at (ISO), secret_hash?, downloads, deleted_at?.
    """
    q = """
    INSERT INTO fileshare_items
      (id, filename, size, content_type, path, owner_id, owner_name,
       created_at, expires_at, secret_hash, downloads, deleted_at)
    VALUES
      (%(id)s, %(filename)s, %(size)s, %(content_type)s, %(path)s, %(owner_id)s, %(owner_name)s,
       %(created_at)s, %(expires_at)s, %(secret_hash)s, %(downloads)s, %(deleted_at)s)
    """
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(q, rec)


def fileshare_get(item_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtém um item do fileshare por `id`.

    Retorna
    -------
    dict | None
    """
    with _pg() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM fileshare_items WHERE id = %s LIMIT 1", (item_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def fileshare_list(owner_id: Optional[str], q: Optional[str], limit: int, offset: int) -> List[Dict[str, Any]]:
    """
    Lista arquivos não deletados, com filtros opcionais por dono e nome.

    Parâmetros
    ----------
    owner_id : str | None
        Filtro por proprietário.
    q : str | None
        Filtro por `filename` (ILIKE).
    limit : int
        Quantidade.
    offset : int
        Deslocamento.

    Retorna
    -------
    list[dict]
    """
    where = ["deleted_at IS NULL"]
    params: List[Any] = []
    if owner_id:
        where.append("owner_id = %s")
        params.append(owner_id)
    if q:
        where.append("filename ILIKE %s")
        params.append(f"%{q}%")

    sql = f"""
        SELECT *
        FROM fileshare_items
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() or []
        return [dict(r) for r in rows]


def fileshare_inc_downloads(item_id: str) -> None:
    """
    Incrementa o contador de downloads de um item do fileshare.

    Parâmetros
    ----------
    item_id : str
        Identificador do item.
    """
    with _pg() as conn, conn.cursor() as cur:
        cur.execute("UPDATE fileshare_items SET downloads = downloads + 1 WHERE id = %s", (item_id,))


def fileshare_soft_delete(item_id: str) -> None:
    """
    Marca um item como deletado (soft delete), registrando `deleted_at` em UTC.

    Parâmetros
    ----------
    item_id : str
        Identificador do item.
    """
    now = _utcnow()
    with _pg() as conn, conn.cursor() as cur:
        cur.execute("UPDATE fileshare_items SET deleted_at = %s WHERE id = %s AND deleted_at IS NULL", (now, item_id))


def fileshare_cleanup_expired(limit: int = 200) -> int:
    """
    Marca como deletados e remove fisicamente arquivos expirados (best-effort).

    Parâmetros
    ----------
    limit : int
        Máximo de itens a processar por execução (padrão 200).

    Retorna
    -------
    int
        Quantidade total de registros afetados (marcados/limpos).
    """
    now = _utcnow()
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, path FROM fileshare_items WHERE deleted_at IS NULL AND expires_at < %s LIMIT %s",
            (now, limit),
        )
        rows = cur.fetchall() or []
        count = 0
        for r in rows:
            cur.execute("UPDATE fileshare_items SET deleted_at = %s WHERE id = %s", (now, r["id"]))
            try:
                p = Path(r["path"])
                if p.exists():
                    p.unlink(missing_ok=True)
            except Exception:
                pass
            count += 1
        return count
