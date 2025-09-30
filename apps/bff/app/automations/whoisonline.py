# apps/bff/app/automations/whoisonline.py
from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from app.db import _pg, add_audit
from app.auth.rbac import _get_user

KIND = "whoisonline"
VERSION = "0.1.0"

# Diretório dos HTMLs da automação
TPL_DIR = pathlib.Path(__file__).resolve().parent / "templates" / KIND

def require_superuser(req: Request) -> Dict[str, Any]:
    """
    Só permite superuser (admin não basta).
    """
    user = _get_user(req)
    if not bool(user.get("is_superuser")):
        raise HTTPException(status_code=403, detail="superuser only")
    return user

router = APIRouter(
    prefix=f"/api/automations/{KIND}",
    tags=["automations", KIND],
    dependencies=[Depends(require_superuser)],
)

def _read_html(name: str) -> str:
    path = TPL_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# -----------------------------------------------------------------------------
# UI (iframe)
# -----------------------------------------------------------------------------
@router.get("/ui")
def ui() -> HTMLResponse:
    html = _read_html("ui.html")
    return HTMLResponse(content=html)

# -----------------------------------------------------------------------------
# Schema/meta
# -----------------------------------------------------------------------------
@router.get("/schema")
def schema() -> Dict[str, Any]:
    return {
        "name": KIND,
        "version": VERSION,
        "title": "Quem está online (Superuser)",
        "endpoints": ["/ui", "/online", "/stats", "/sessions/{id}/revoke"],
    }

# -----------------------------------------------------------------------------
# JSON endpoints
# -----------------------------------------------------------------------------
class OnlineSession(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    session_id: str
    user_id: str
    nome: Optional[str] = None
    email: Optional[str] = None
    cpf: Optional[str] = None
    roles: List[str] = []
    is_superuser: bool = False
    created_at: str
    last_seen_at: Optional[str] = None
    expires_at: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None

@router.get("/online", response_model=List[OnlineSession])
def list_online(
    q: Optional[str] = Query(default=None, description="Filtro por nome/email/cpf/ip/user_agent"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> List[OnlineSession]:
    """
    Lista sessões ativas (não revogadas e não expiradas), juntando dados do usuário e seus roles.
    """
    where_extra = ""
    params: Dict[str, Any] = {"limit": limit}
    if q:
        where_extra = """
          AND (
            unaccent(lower(u.name)) LIKE unaccent(lower(%(q)s)) OR
            lower(u.email) LIKE lower(%(q)s) OR
            u.cpf LIKE %(qnum)s OR
            s.ip::text LIKE %(q)s OR
            lower(s.user_agent) LIKE lower(%(q)s)
          )
        """
        params["q"] = f"%{q}%"
        params["qnum"] = f"%{''.join(ch for ch in q if ch.isdigit())}%"

    sql = f"""
        SELECT
          s.id::text AS session_id,
          s.user_id::text AS user_id,
          u.name AS nome,
          u.email,
          u.cpf,
          COALESCE(u.is_superuser, FALSE) AS is_superuser,
          to_char(s.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS created_at,
          to_char(s.last_seen_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS last_seen_at,
          to_char(s.expires_at   AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS expires_at,
          s.ip::text AS ip,
          s.user_agent,
          COALESCE(roles.roles, ARRAY[]::text[]) AS roles
        FROM auth_sessions s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN LATERAL (
            SELECT array_agg(r.name ORDER BY r.name) AS roles
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = u.id
        ) roles ON TRUE
        WHERE s.revoked_at IS NULL
          AND s.expires_at > now()
          {where_extra}
        ORDER BY s.last_seen_at DESC NULLS LAST, s.created_at DESC
        LIMIT %(limit)s
    """
    with _pg() as conn, conn.cursor() as cur:
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
        except Exception:
            pass
        cur.execute(sql, params)
        rows = cur.fetchall() or []
    return [OnlineSession(**row) for row in rows]

@router.get("/stats")
def stats() -> Dict[str, Any]:
    """
    KPIs/Agregados das sessões ativas.
    """
    out: Dict[str, Any] = {}
    with _pg() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT count(*)::int AS c
            FROM auth_sessions s
            WHERE s.revoked_at IS NULL AND s.expires_at > now()
        """)
        out["sessions"] = (cur.fetchone() or {}).get("c", 0)

        cur.execute("""
            SELECT count(DISTINCT s.user_id)::int AS c
            FROM auth_sessions s
            WHERE s.revoked_at IS NULL AND s.expires_at > now()
        """)
        out["users"] = (cur.fetchone() or {}).get("c", 0)

        cur.execute("""
            SELECT
              COALESCE(u.is_superuser, FALSE) AS is_superuser,
              count(DISTINCT s.user_id)::int AS users
            FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.revoked_at IS NULL AND s.expires_at > now()
            GROUP BY 1
            ORDER BY 1 DESC
        """)
        out["by_superuser"] = cur.fetchall() or []

        cur.execute("""
            SELECT split_part(coalesce(s.user_agent,''), ' ', 1) AS agent, count(*)::int AS c
            FROM auth_sessions s
            WHERE s.revoked_at IS NULL AND s.expires_at > now()
            GROUP BY 1
            ORDER BY c DESC
            LIMIT 10
        """)
        out["top_agents"] = cur.fetchall() or []

        cur.execute("""
            SELECT COALESCE(s.ip::text, 'unknown') AS ip, count(*)::int AS c
            FROM auth_sessions s
            WHERE s.revoked_at IS NULL AND s.expires_at > now()
            GROUP BY 1
            ORDER BY c DESC
            LIMIT 10
        """)
        out["top_ips"] = cur.fetchall() or []

        cur.execute("""
            SELECT
              to_char(min(s.created_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS oldest_login,
              to_char(max(s.last_seen_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS latest_seen
            FROM auth_sessions s
            WHERE s.revoked_at IS NULL AND s.expires_at > now()
        """)
        out["window"] = cur.fetchone() or {}

    out["version"] = VERSION
    return out

@router.post("/sessions/{session_id}/revoke")
def revoke_session(session_id: str, request: Request) -> Response:
    """
    Revoga uma sessão específica (idempotente). Exige superuser.
    """
    actor = _get_user(request)
    with _pg() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id, revoked_at FROM auth_sessions WHERE id = %s", (session_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="session not found")
        cur.execute(
            "UPDATE auth_sessions SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL",
            (session_id,),
        )
    # auditoria
    try:
        add_audit(KIND, "revoke", actor, {"session_id": session_id})
    except Exception:
        pass
    return Response(status_code=204)
