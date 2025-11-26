# apps/bff/app/auth/sessions.py
"""
Rotas de gerenciamento de sessões do BFF do Portal AGEPAR.

Visão geral
-----------
Expõe endpoints para o usuário autenticado:
- `GET /api/auth/sessions`            → lista todas as sessões do próprio usuário.
- `POST /api/auth/sessions/{id}/revoke` → revoga uma sessão específica (idempotente).

Modelo de sessão
----------------
As sessões são persistidas na tabela `auth_sessions` (PostgreSQL) e o ID da sessão
corrente fica espelhado em `request.session["db_session_id"]`.

Variáveis de ambiente
---------------------
- DATABASE_URL : string de conexão do PostgreSQL (obrigatória).
- AUTH_REVOKE_AUTO_LOGOUT_CURRENT : "1"/"true" para efetuar logout local imediato
  quando a sessão **corrente** for revogada via API.

Segurança
---------
Os endpoints usam `_require_current_session` para validar que há uma sessão
server-side ativa. Não há RBAC adicional aqui porque as operações são
estritamente **do próprio usuário** (escopo self).
"""

from __future__ import annotations

import os
from uuid import UUID
from typing import List, Optional, Dict, Any

import psycopg
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")
AUTH_REVOKE_AUTO_LOGOUT_CURRENT = os.getenv("AUTH_REVOKE_AUTO_LOGOUT_CURRENT", "1") in ("1", "true", "True")


def _pg_conn():
    """
    Abre uma conexão curta com o PostgreSQL usando `DATABASE_URL`.

    Retorna
    -------
    psycopg.Connection
        Conexão com `autocommit=True`.

    Levanta
    -------
    RuntimeError
        Caso `DATABASE_URL` não esteja configurada.
    """
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL, autocommit=True)


def _insert_audit(
    conn,
    actor_user_id: Optional[str],
    action: str,
    obj_type: Optional[str],
    obj_id: Optional[str],
    message: str,
    metadata: Dict[str, Any],
    ip: Optional[str],
    ua: Optional[str],
) -> None:
    """
    Registra um evento de auditoria na tabela `audit_events`.

    Parâmetros
    ----------
    conn : psycopg.Connection
        Conexão ativa.
    actor_user_id : Optional[str]
        ID do usuário responsável pela ação.
    action : str
        Código curto da ação (ex.: "auth.session.revoke").
    obj_type : Optional[str]
        Tipo do objeto-alvo (ex.: "session").
    obj_id : Optional[str]
        Identificador do objeto-alvo.
    message : str
        Mensagem descritiva do evento.
    metadata : Dict[str, Any]
        Metadados serializados como JSONB.
    ip : Optional[str]
        IP de origem (quando disponível).
    ua : Optional[str]
        User-Agent (quando disponível).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_events (actor_user_id, action, object_type, object_id, message, metadata, ip, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (actor_user_id, action, obj_type, obj_id, message, psycopg.types.json.Json(metadata), ip, ua),
        )


def _require_current_session(request: Request) -> str:
    """
    Valida a existência de sessão server-side ativa e retorna o `user_id`.

    Estratégia
    ----------
    1) Lê `db_session_id` de `request.session`.
    2) Confirma no banco se a sessão não está revogada e não expirou.
    3) Em caso de sessão inválida, limpa a sessão web (quando possível) e retorna 401.

    Parâmetros
    ----------
    request : Request
        Requisição atual.

    Retorna
    -------
    str
        Identificador do usuário autenticado (`user_id`).

    Levanta
    -------
    HTTPException
        401 quando não há sessão válida.
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
            try:
                request.session.clear()
            except Exception:
                pass
            raise HTTPException(status_code=401, detail="not authenticated")
        return row[0]


class SessionOut(BaseModel):
    """
    Representação pública de uma sessão do usuário.

    Campos
    ------
    id : str
        Identificador da sessão.
    created_at : str
        Timestamp de criação (formato textual do banco).
    last_seen_at : str
        Último acesso registrado.
    expires_at : str
        Expiração da sessão.
    revoked_at : Optional[str]
        Data/hora de revogação, quando houver.
    ip : Optional[str]
        IP associado durante a criação da sessão.
    user_agent : Optional[str]
        User-Agent informado na criação.
    current : bool
        Indica se é a sessão utilizada nesta requisição.
    """
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
    Lista todas as sessões do próprio usuário (atuais, expiradas e/ou revogadas).

    Parâmetros
    ----------
    request : Request
        Requisição atual.

    Retorna
    -------
    List[SessionOut]
        Lista ordenada por `created_at` decrescente.
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
    Revoga uma sessão pertencente ao próprio usuário (operação idempotente).

    Regras
    ------
    - Se a sessão não pertencer ao usuário autenticado, retorna 404.
    - Caso a sessão já esteja revogada, a operação segue retornando 204.
    - Opcionalmente, efetua logout local imediato se a sessão revogada for a atual.

    Parâmetros
    ----------
    session_id : str
        Identificador da sessão em formato UUID.
    request : Request
        Requisição atual.

    Retorna
    -------
    Response
        204 No Content em caso de sucesso.

    Levanta
    -------
    HTTPException
        404 para sessão inexistente/não pertencente.
        401 para sessão corrente inválida.
    """
    user_id = _require_current_session(request)
    current_id = request.session.get("db_session_id") if hasattr(request, "session") else None
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        sid = str(UUID(session_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="session not found")

    with _pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM auth_sessions WHERE id = %s AND user_id = %s",
            (sid, user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="session not found")

        cur.execute(
            "UPDATE auth_sessions SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL",
            (sid,),
        )

        _insert_audit(
            conn,
            actor_user_id=str(user_id),
            action="auth.session.revoke",
            obj_type="session",
            obj_id=sid,
            message="Revogação de sessão via API",
            metadata={"current": bool(current_id and str(current_id) == sid)},
            ip=ip,
            ua=ua,
        )

    if AUTH_REVOKE_AUTO_LOGOUT_CURRENT and current_id and str(current_id) == sid:
        try:
            request.session.clear()
        except Exception:
            pass
    return Response(status_code=204)
