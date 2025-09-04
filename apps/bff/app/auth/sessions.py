from __future__ import annotations

import os
from typing import List, Optional

import psycopg
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")

def _pg_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL, autocommit=True)

def _require_current_session(request: Request) -> str:
    """
    Lê o db_session_id da session do app.
    Verifica no banco se é uma sessão válida (não revogada e não expirada).
    Retorna o user_id autenticado.
    """
    db_session_id = request.session.get("db_session_id") if hasattr(request, "session") else None
    if not db_session_id:
        raise HTTPException(status_code=401, detail="not authenticated (no server-side session)")
    with _pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_id
            FROM auth_sessions
            WHERE id = %s
              AND revoked_at IS NULL
              AND expires_at > now()
            """,
            (db_session_id,),
        )
        row = cur.fetchone()
        if not row:
            # Session inválida → limpar sessão do app (quando possível)
            try:
                request.session.clear()
            except Exception:
                pass
            raise HTTPException(status_code=401, detail="not authenticated")
        return row[0]

class SessionOut(BaseModel):
    id: str
    created_at: str
    last_seen_at: str
    expires_at: str
    revoked_at: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    current: bool = Field(description="Indica se é a sessão utilizada nesta requisição")

@router.get("/api/auth/sessions", response_model=List[SessionOut])
def list_my_sessions(request: Request) -> List[SessionOut]:
    """
    Lista todas as sessões do usuário autenticado (atuais e antigas).
    """
    with _pg_conn() as conn, conn.cursor() as cur:
        user_id = _require_current_session(request)
        current_id = request.session.get("db_session_id")

        cur.execute(
            """
            SELECT id::text, created_at::text, last_seen_at::text, expires_at::text,
                   revoked_at::text, ip::text, user_agent
            FROM auth_sessions
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        items: List[SessionOut] = []
        for row in cur.fetchall():
            (sid, created, seen, exp, rev, ip, ua) = row
            items.append(
                SessionOut(
                    id=sid,
                    created_at=created,
                    last_seen_at=seen,
                    expires_at=exp,
                    revoked_at=rev,
                    ip=ip,
                    user_agent=ua,
                    current=(sid == current_id),
                )
            )
        return items

@router.post("/api/auth/sessions/{session_id}/revoke", status_code=204, response_class=Response)
def revoke_my_session(session_id: str, request: Request) -> Response:
    """
    Revoga uma sessão do próprio usuário. Idempotente.
    - 204: revogada (ou já estava revogada).
    - 404: sessão não pertence ao usuário.
    """
    user_id = _require_current_session(request)
    with _pg_conn() as conn, conn.cursor() as cur:
        # Garante ownership
        cur.execute(
            "SELECT 1 FROM auth_sessions WHERE id = %s AND user_id = %s",
            (session_id, user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="session not found")

        # Revoga (idempotente)
        cur.execute(
            "UPDATE auth_sessions SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL",
            (session_id,),
        )
    return Response(status_code=204)
