import os
import sqlite3
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = "/app/data/app.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    # Melhorias de confiabilidade/concorrência no SQLite
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def _utcnow() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _as_text(v: Any) -> Optional[str]:
    """
    Garante TEXT para armazenamento. Dict/list → JSON.
    None permanece None.
    """
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def init_db() -> None:
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
              id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              version TEXT NOT NULL,
              actor_cpf TEXT,
              actor_nome TEXT,
              actor_email TEXT,
              payload TEXT NOT NULL,
              status TEXT NOT NULL,
              result TEXT,
              error TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audits (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              at TEXT NOT NULL,
              actor_cpf TEXT,
              actor_nome TEXT,
              kind TEXT NOT NULL,
              action TEXT NOT NULL,
              meta TEXT
            )
            """
        )
        # Índices úteis para consultas frequentes
        cur.execute("CREATE INDEX IF NOT EXISTS ix_submissions_created_at ON submissions (created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_submissions_kind_created ON submissions (kind, created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_submissions_actor_cpf_created ON submissions (actor_cpf, created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_audits_at ON audits (at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_submissions_actor_email_created ON submissions (actor_email, created_at DESC)")


def insert_submission(sub: Dict[str, Any]) -> None:
    sub = dict(sub)  # cópia defensiva
    # Normaliza campos textuais/JSON
    sub["payload"] = _as_text(sub.get("payload"))
    sub["result"] = _as_text(sub.get("result"))
    sub["error"] = _as_text(sub.get("error"))
    # Garantia de timestamps
    sub.setdefault("created_at", _utcnow())
    sub.setdefault("updated_at", sub["created_at"])

    with _conn() as con:
        con.execute(
            """
            INSERT INTO submissions
              (id, kind, version, actor_cpf, actor_nome, actor_email, payload, status, result, error, created_at, updated_at)
            VALUES
              (:id, :kind, :version, :actor_cpf, :actor_nome, :actor_email, :payload, :status, :result, :error, :created_at, :updated_at)
            """,
            sub,
        )


def update_submission(id: str, **fields: Any) -> None:
    if not fields:
        return
    fields = {k: _as_text(v) if k in {"payload", "result", "error"} else v for k, v in fields.items()}
    fields["updated_at"] = _utcnow()
    sets = ", ".join(f"{k}=:{k}" for k in fields.keys())
    params = dict(id=id, **fields)
    with _conn() as con:
        con.execute(f"UPDATE submissions SET {sets} WHERE id=:id", params)


def get_submission(id: str) -> Optional[Dict[str, Any]]:
    with _conn() as con:
        cur = con.execute("SELECT * FROM submissions WHERE id = ?", (id,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_submissions(
    kind: Optional[str] = None,
    actor_cpf: Optional[str] = None,
    actor_email: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    q = "SELECT * FROM submissions WHERE 1=1"
    params: Tuple[Any, ...] = ()
    if kind:
        q += " AND kind = ?"
        params += (kind,)
    # Prioriza CPF; se não houver, cai para e-mail
    if actor_cpf is not None:
        q += " AND actor_cpf = ?"
        params += (actor_cpf,)
    elif actor_email is not None:
        q += " AND actor_email = ?"
        params += (actor_email,)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params += (limit, offset)

    with _conn() as con:
        cur = con.execute(q, params)
        return [dict(r) for r in cur.fetchall()]



def add_audit(kind: str, action: str, actor: Dict[str, Any], meta: Dict[str, Any]) -> None:
    with _conn() as con:
        con.execute(
            """
            INSERT INTO audits (at, actor_cpf, actor_nome, kind, action, meta)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _utcnow(),
                actor.get("cpf"),
                actor.get("nome"),
                kind,
                action,
                json.dumps(meta, ensure_ascii=False),
            ),
        )

def list_audits(kind: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    q = "SELECT * FROM audits WHERE 1=1"
    params: Tuple[Any, ...] = ()
    if kind:
        q += " AND kind = ?"
        params += (kind,)
    q += " ORDER BY at DESC LIMIT ? OFFSET ?"
    params += (limit, offset)
    with _conn() as con:
        cur = con.execute(q, params)
        rows = [dict(r) for r in cur.fetchall()]
        return rows