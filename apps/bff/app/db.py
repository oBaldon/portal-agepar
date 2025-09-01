import os, sqlite3, json
from datetime import datetime
from typing import Any, Dict, List, Optional

DB_PATH = "/app/data/app.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def _conn():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = _conn()
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS submissions (
      id TEXT PRIMARY KEY,
      kind TEXT NOT NULL,
      version TEXT NOT NULL,
      actor_cpf TEXT, actor_nome TEXT, actor_email TEXT,
      payload TEXT NOT NULL,
      status TEXT NOT NULL,
      result TEXT,
      error TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audits (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      at TEXT NOT NULL,
      actor_cpf TEXT, actor_nome TEXT, kind TEXT NOT NULL,
      action TEXT NOT NULL, meta TEXT
    )""")
    con.commit()
    con.close()

def insert_submission(sub: Dict[str, Any]):
    con = _conn(); cur = con.cursor()
    cur.execute("""INSERT INTO submissions
      (id, kind, version, actor_cpf, actor_nome, actor_email, payload, status, result, error, created_at, updated_at)
      VALUES (:id, :kind, :version, :actor_cpf, :actor_nome, :actor_email, :payload, :status, :result, :error, :created_at, :updated_at)
    """, sub)
    con.commit(); con.close()

def update_submission(id: str, **fields):
    fields["updated_at"] = datetime.utcnow().isoformat() + "Z"
    sets = ", ".join(f"{k}=:{k}" for k in fields.keys())
    con = _conn(); cur = con.cursor()
    cur.execute(f"UPDATE submissions SET {sets} WHERE id=:id", dict(id=id, **fields))
    con.commit(); con.close()

def get_submission(id: str) -> Optional[Dict[str, Any]]:
    con = _conn(); cur = con.cursor()
    cur.execute("SELECT * FROM submissions WHERE id=?", (id,))
    row = cur.fetchone(); con.close()
    return dict(row) if row else None

def list_submissions(kind: Optional[str]=None, actor_cpf: Optional[str]=None, limit:int=50, offset:int=0) -> List[Dict[str, Any]]:
    con = _conn(); cur = con.cursor()
    q = "SELECT * FROM submissions WHERE 1=1"
    params = []
    if kind:
        q += " AND kind=?"; params.append(kind)
    if actor_cpf:
        q += " AND actor_cpf=?"; params.append(actor_cpf)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cur.execute(q, params)
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows

def add_audit(kind: str, action: str, actor: Dict[str, Any], meta: Dict[str, Any]):
    con = _conn(); cur = con.cursor()
    cur.execute("""INSERT INTO audits (at, actor_cpf, actor_nome, kind, action, meta)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (datetime.utcnow().isoformat()+"Z", actor.get("cpf"), actor.get("nome"),
                 kind, action, json.dumps(meta, ensure_ascii=False)))
    con.commit(); con.close()
