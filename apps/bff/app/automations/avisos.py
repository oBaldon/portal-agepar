# apps/bff/app/automations/avisos.py
from __future__ import annotations

"""
Automação de Avisos Globais — Portal AGEPAR.

Propósito
---------
Permite que administradores publiquem um aviso global para os usuários com
sessão ativa no momento do disparo. Cada destinatário pode:
- confirmar ciência do aviso; ou
- registrar objeção com mensagem.

Além do painel administrativo (iframe), o módulo também expõe endpoints para o
host consultar avisos pendentes e apresentar um popup global em qualquer rota.

Decisões de projeto
-------------------
- Apenas **um** aviso publicado por vez.
- Público-alvo: snapshot dos usuários com sessão ativa (`auth_sessions`) no
  momento da publicação.
- Rastreamento por usuário (não por aba/sessão).
- Objeção com mensagem obrigatória por padrão.
- O host decide a UX de exibição global (popup / badge na aba), enquanto o BFF
  centraliza regras de negócio, persistência e auditoria.

Segurança
---------
- Painel administrativo e ações de criação/encerramento exigem papel `admin`
  (ou superuser via bypass do RBAC existente).
- Endpoints do usuário exigem autenticação e pertencimento ao destinatário.

Observações
-----------
- O módulo grava histórico em `submissions`, `automation_audits` e
  `audit_events`.
- As tabelas principais são `platform_alerts` e `platform_alert_recipients`.
"""

import csv
import io
import logging
import pathlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.auth.rbac import require_auth, require_roles_any
from app.db import DATABASE_URL

logger = logging.getLogger(__name__)

KIND = "avisos"
AVISOS_VERSION = "0.1.0"
TITLE = "Admin — Avisos Globais"
AUTOMATION_META = {
    "kind": KIND,
    "version": AVISOS_VERSION,
    "title": TITLE,
}

TPL_DIR = pathlib.Path(__file__).resolve().parent / "templates" / KIND

LEVELS = {"info", "warning", "danger"}
ALERT_STATUSES = {"published", "closed", "expired", "cancelled"}
RECIPIENT_STATUSES = {"pending", "seen", "confirmed", "objected"}

router = APIRouter(
    prefix="/api/automations/avisos",
    tags=["automations", KIND],
)


class CreateAlertIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    title: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=4000)
    level: Literal["info", "warning", "danger"] = "warning"
    expires_in_minutes: int = Field(default=60, ge=1, le=10080)
    allow_dismiss: bool = False
    objection_enabled: bool = True
    objection_requires_message: bool = True
    tab_badge_enabled: bool = True

    @model_validator(mode="after")
    def validate_flags(self) -> "CreateAlertIn":
        if not self.objection_enabled:
            self.objection_requires_message = False
        return self


class CloseAlertIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    reason: Optional[str] = Field(default=None, max_length=240)


class ObjectionIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    message: str = Field(min_length=1, max_length=2000)


def _conn(*, autocommit: bool = False) -> psycopg.Connection:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg.connect(DATABASE_URL, autocommit=autocommit, row_factory=dict_row)


def _read_html(name: str) -> str:
    with open(TPL_DIR / name, "r", encoding="utf-8") as f:
        return f.read()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _actor_name(user: Dict[str, Any]) -> Optional[str]:
    return user.get("nome") or user.get("name")


def _expire_old_alerts(conn: psycopg.Connection) -> List[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE platform_alerts
               SET status = 'expired',
                   closed_at = COALESCE(closed_at, now()),
                   closed_reason = COALESCE(closed_reason, 'expired'),
                   updated_at = now()
             WHERE status = 'published'
               AND expires_at <= now()
             RETURNING id::text
            """
        )
        rows = cur.fetchall() or []
    return [str(r["id"]) for r in rows]


def _resolve_user_id(
    conn: psycopg.Connection,
    request: Request,
    user: Dict[str, Any],
) -> Optional[str]:
    user_id = user.get("id")
    if user_id:
        return str(user_id)

    db_sess_id = None
    try:
        db_sess_id = request.session.get("db_session_id")
    except Exception:
        db_sess_id = None

    with conn.cursor() as cur:
        if db_sess_id:
            cur.execute(
                """
                SELECT user_id::text
                  FROM auth_sessions
                 WHERE id = %s::uuid
                   AND revoked_at IS NULL
                   AND expires_at > now()
                """,
                (str(db_sess_id),),
            )
            row = cur.fetchone()
            if row and row.get("user_id"):
                return str(row["user_id"])

        email = (user.get("email") or "").strip().lower() or None
        cpf = (user.get("cpf") or "").strip() or None

        if email:
            cur.execute("SELECT id::text FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            if row and row.get("id"):
                return str(row["id"])

        if cpf:
            cur.execute("SELECT id::text FROM users WHERE cpf = %s", (cpf,))
            row = cur.fetchone()
            if row and row.get("id"):
                return str(row["id"])

    return None


def _select_logged_in_user_ids(conn: psycopg.Connection) -> List[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT s.user_id::text AS user_id
              FROM auth_sessions s
              JOIN users u ON u.id = s.user_id
             WHERE s.revoked_at IS NULL
               AND s.expires_at > now()
               AND u.status = 'active'
            """
        )
        rows = cur.fetchall() or []
    return [str(r["user_id"]) for r in rows if r.get("user_id")]


def _insert_submission(
    conn: psycopg.Connection,
    *,
    kind: str,
    actor: Dict[str, Any],
    payload: Dict[str, Any],
    result: Optional[Dict[str, Any]] = None,
    status: str = "done",
    error: Optional[str] = None,
) -> str:
    submission_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO submissions
              (id, kind, version, actor_cpf, actor_nome, actor_email, payload, status, result, error)
            VALUES
              (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s)
            """,
            (
                submission_id,
                kind,
                AVISOS_VERSION,
                actor.get("cpf"),
                _actor_name(actor),
                actor.get("email"),
                Json(payload or {}),
                status,
                Json(result or {}),
                error,
            ),
        )
    return submission_id


def _insert_automation_audit(
    conn: psycopg.Connection,
    *,
    actor: Dict[str, Any],
    action: str,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO automation_audits (actor_cpf, actor_nome, kind, action, meta)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (
                actor.get("cpf"),
                _actor_name(actor),
                KIND,
                action,
                Json(meta or {}),
            ),
        )


def _insert_audit_event(
    conn: psycopg.Connection,
    *,
    actor_user_id: Optional[str],
    action: str,
    object_id: str,
    message: str,
    metadata: Optional[Dict[str, Any]],
    request: Request,
) -> None:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_events
              (actor_user_id, action, object_type, object_id, message, metadata, ip, user_agent)
            VALUES
              (%s::uuid, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                actor_user_id,
                action,
                "platform_alert",
                object_id,
                message,
                Json(metadata or {}),
                ip,
                ua,
            ),
        )


def _row_to_alert_out(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "message": row["message"],
        "level": row["level"],
        "status": row["status"],
        "createdAt": row.get("created_at").isoformat() if row.get("created_at") else None,
        "updatedAt": row.get("updated_at").isoformat() if row.get("updated_at") else None,
        "publishedAt": row.get("published_at").isoformat() if row.get("published_at") else None,
        "expiresAt": row.get("expires_at").isoformat() if row.get("expires_at") else None,
        "closedAt": row.get("closed_at").isoformat() if row.get("closed_at") else None,
        "closedReason": row.get("closed_reason"),
        "allowDismiss": bool(row.get("allow_dismiss")),
        "objectionEnabled": bool(row.get("objection_enabled")),
        "objectionRequiresMessage": bool(row.get("objection_requires_message")),
        "tabBadgeEnabled": bool(row.get("tab_badge_enabled")),
        "createdByUserId": str(row["created_by_user_id"]) if row.get("created_by_user_id") else None,
        "createdByName": row.get("actor_nome"),
        "createdByEmail": row.get("actor_email"),
    }


def _load_alert_or_404(conn: psycopg.Connection, alert_id: str) -> Dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM platform_alerts WHERE id = %s::uuid", (alert_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Aviso não encontrado.")
    return dict(row)


def _load_alert_counts(conn: psycopg.Connection, alert_id: str) -> Dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              COUNT(*)::int AS total,
              COUNT(*) FILTER (WHERE r.first_seen_at IS NOT NULL)::int AS visualized,
              COUNT(*) FILTER (WHERE r.status = 'confirmed')::int AS confirmed,
              COUNT(*) FILTER (WHERE r.status = 'objected')::int AS objected,
              COUNT(*) FILTER (WHERE r.status = 'seen')::int AS seen,
              COUNT(*) FILTER (WHERE r.status = 'pending')::int AS pending,
              COUNT(*) FILTER (WHERE r.status IN ('pending', 'seen'))::int AS no_action
            FROM platform_alert_recipients r
            WHERE r.alert_id = %s::uuid
            """,
            (alert_id,),
        )
        row = cur.fetchone() or {}
    return {
        "total": int(row.get("total") or 0),
        "visualized": int(row.get("visualized") or 0),
        "confirmed": int(row.get("confirmed") or 0),
        "objected": int(row.get("objected") or 0),
        "seen": int(row.get("seen") or 0),
        "pending": int(row.get("pending") or 0),
        "noAction": int(row.get("no_action") or 0),
    }


def _load_alert_detail(conn: psycopg.Connection, alert_id: str) -> Dict[str, Any]:
    row = _load_alert_or_404(conn, alert_id)
    out = _row_to_alert_out(row)
    out["counts"] = _load_alert_counts(conn, alert_id)
    return out


def _list_alerts(
    conn: psycopg.Connection,
    *,
    status: Optional[str],
    limit: int,
    offset: int,
) -> List[Dict[str, Any]]:
    params: List[Any] = []
    where = ["1=1"]
    if status:
        where.append("a.status = %s")
        params.append(status)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              a.*,
              COUNT(r.*)::int AS total_count,
              COUNT(*) FILTER (WHERE r.first_seen_at IS NOT NULL)::int AS visualized_count,
              COUNT(*) FILTER (WHERE r.status = 'confirmed')::int AS confirmed_count,
              COUNT(*) FILTER (WHERE r.status = 'objected')::int AS objected_count,
              COUNT(*) FILTER (WHERE r.status = 'seen')::int AS seen_count,
              COUNT(*) FILTER (WHERE r.status = 'pending')::int AS pending_count,
              COUNT(*) FILTER (WHERE r.status IN ('pending', 'seen'))::int AS no_action_count
            FROM platform_alerts a
            LEFT JOIN platform_alert_recipients r ON r.alert_id = a.id
            WHERE {' AND '.join(where)}
            GROUP BY a.id
            ORDER BY COALESCE(a.published_at, a.created_at) DESC, a.created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = cur.fetchall() or []

    items: List[Dict[str, Any]] = []
    for row in rows:
        item = _row_to_alert_out(dict(row))
        item["counts"] = {
            "total": int(row.get("total_count") or 0),
            "visualized": int(row.get("visualized_count") or 0),
            "confirmed": int(row.get("confirmed_count") or 0),
            "objected": int(row.get("objected_count") or 0),
            "seen": int(row.get("seen_count") or 0),
            "pending": int(row.get("pending_count") or 0),
            "noAction": int(row.get("no_action_count") or 0),
        }
        items.append(item)
    return items




def _normalize_recipient_status_filter(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    normalized = status.strip().lower()
    if not normalized:
        return None
    if normalized not in RECIPIENT_STATUSES:
        raise HTTPException(status_code=422, detail="Status de destinatário inválido.")
    return normalized


def _load_alert_recipients(
    conn: psycopg.Connection,
    *,
    alert_id: str,
    q: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    _load_alert_or_404(conn, alert_id)

    where = ["r.alert_id = %s::uuid"]
    params: List[Any] = [alert_id]

    normalized_status = _normalize_recipient_status_filter(status)
    if normalized_status:
        where.append("r.status = %s")
        params.append(normalized_status)

    search = (q or "").strip()
    if search:
        term = f"%{search}%"
        where.append("(u.name ILIKE %s OR u.email ILIKE %s OR u.cpf LIKE %s)")
        params.extend([term, term, term])

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              r.alert_id,
              r.user_id::text AS user_id,
              u.name,
              u.email,
              u.cpf,
              r.status,
              r.delivered_at,
              r.first_seen_at,
              r.responded_at,
              r.confirmed_at,
              r.objected_at,
              r.objection_message
            FROM platform_alert_recipients r
            JOIN users u ON u.id = r.user_id
            WHERE {' AND '.join(where)}
            ORDER BY
              CASE r.status
                WHEN 'objected' THEN 0
                WHEN 'pending' THEN 1
                WHEN 'seen' THEN 2
                WHEN 'confirmed' THEN 3
                ELSE 4
              END,
              u.name ASC
            """,
            params,
        )
        rows = cur.fetchall() or []

    items: List[Dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "alertId": str(row["alert_id"]),
                "userId": str(row["user_id"]),
                "name": row["name"],
                "email": row.get("email"),
                "cpf": row.get("cpf"),
                "status": row["status"],
                "deliveredAt": row.get("delivered_at").isoformat() if row.get("delivered_at") else None,
                "firstSeenAt": row.get("first_seen_at").isoformat() if row.get("first_seen_at") else None,
                "respondedAt": row.get("responded_at").isoformat() if row.get("responded_at") else None,
                "confirmedAt": row.get("confirmed_at").isoformat() if row.get("confirmed_at") else None,
                "objectedAt": row.get("objected_at").isoformat() if row.get("objected_at") else None,
                "objectionMessage": row.get("objection_message"),
            }
        )
    return items


def _load_alert_objections(
    conn: psycopg.Connection,
    *,
    alert_id: str,
    q: Optional[str] = None,
) -> List[Dict[str, Any]]:
    _load_alert_or_404(conn, alert_id)

    where = ["r.alert_id = %s::uuid", "r.status = 'objected'"]
    params: List[Any] = [alert_id]
    search = (q or "").strip()
    if search:
        term = f"%{search}%"
        where.append(
            "(u.name ILIKE %s OR u.email ILIKE %s OR u.cpf LIKE %s OR COALESCE(r.objection_message, '') ILIKE %s)"
        )
        params.extend([term, term, term, term])

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              r.alert_id,
              r.user_id::text AS user_id,
              u.name,
              u.email,
              u.cpf,
              r.objected_at,
              r.objection_message
            FROM platform_alert_recipients r
            JOIN users u ON u.id = r.user_id
            WHERE {' AND '.join(where)}
            ORDER BY r.objected_at DESC NULLS LAST, u.name ASC
            """,
            params,
        )
        rows = cur.fetchall() or []

    items: List[Dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "alertId": str(row["alert_id"]),
                "userId": str(row["user_id"]),
                "name": row["name"],
                "email": row.get("email"),
                "cpf": row.get("cpf"),
                "objectedAt": row.get("objected_at").isoformat() if row.get("objected_at") else None,
                "message": row.get("objection_message"),
            }
        )
    return items


def _load_alert_events(conn: psycopg.Connection, *, alert_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    _load_alert_or_404(conn, alert_id)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              ae.id,
              ae.at,
              ae.action,
              ae.message,
              ae.metadata,
              ae.ip::text AS ip,
              COALESCE(u.name, u.email, ae.actor_user_id::text) AS actor_name,
              u.email AS actor_email,
              u.cpf AS actor_cpf
            FROM audit_events ae
            LEFT JOIN users u ON u.id = ae.actor_user_id
            WHERE ae.object_type = 'platform_alert'
              AND ae.object_id = %s
            ORDER BY ae.at DESC, ae.id DESC
            LIMIT %s
            """,
            (alert_id, limit),
        )
        rows = cur.fetchall() or []

    items: List[Dict[str, Any]] = []
    for row in rows:
        metadata = row.get("metadata") or {}
        items.append(
            {
                "id": int(row["id"]),
                "at": row.get("at").isoformat() if row.get("at") else None,
                "action": row.get("action"),
                "message": row.get("message"),
                "actorName": row.get("actor_name"),
                "actorEmail": row.get("actor_email"),
                "actorCpf": row.get("actor_cpf"),
                "ip": row.get("ip"),
                "metadata": metadata,
            }
        )
    return items


def _csv_response(filename: str, headers: List[str], rows: List[List[Any]]) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])

    content = buf.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

def _active_recipient_for_user_or_404(
    conn: psycopg.Connection,
    *,
    alert_id: str,
    user_id: str,
) -> Dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              a.id AS alert_id,
              a.title,
              a.message,
              a.level,
              a.status AS alert_status,
              a.allow_dismiss,
              a.objection_enabled,
              a.objection_requires_message,
              a.tab_badge_enabled,
              a.created_at,
              a.published_at,
              a.expires_at,
              r.user_id,
              r.status AS recipient_status,
              r.delivered_at,
              r.first_seen_at,
              r.responded_at,
              r.confirmed_at,
              r.objected_at,
              r.objection_message
            FROM platform_alerts a
            JOIN platform_alert_recipients r
              ON r.alert_id = a.id
            WHERE a.id = %s::uuid
              AND r.user_id = %s::uuid
            """,
            (alert_id, user_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Aviso não encontrado para o usuário atual.")
    return dict(row)


def _ensure_alert_actionable(row: Dict[str, Any]) -> None:
    if row.get("alert_status") != "published":
        raise HTTPException(status_code=409, detail="Este aviso não está mais ativo.")
    expires_at = row.get("expires_at")
    if expires_at and expires_at <= _now_utc():
        raise HTTPException(status_code=409, detail="Este aviso expirou.")
    if row.get("recipient_status") in ("confirmed", "objected"):
        return


def _recipient_item_out(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "alertId": str(row["alert_id"]),
        "id": str(row["alert_id"]),
        "title": row["title"],
        "message": row["message"],
        "level": row["level"],
        "status": row["recipient_status"],
        "publishedAt": row.get("published_at").isoformat() if row.get("published_at") else None,
        "expiresAt": row.get("expires_at").isoformat() if row.get("expires_at") else None,
        "allowDismiss": bool(row.get("allow_dismiss")),
        "objectionEnabled": bool(row.get("objection_enabled")),
        "objectionRequiresMessage": bool(row.get("objection_requires_message")),
        "tabBadgeEnabled": bool(row.get("tab_badge_enabled")),
        "firstSeenAt": row.get("first_seen_at").isoformat() if row.get("first_seen_at") else None,
        "respondedAt": row.get("responded_at").isoformat() if row.get("responded_at") else None,
        "confirmedAt": row.get("confirmed_at").isoformat() if row.get("confirmed_at") else None,
        "objectedAt": row.get("objected_at").isoformat() if row.get("objected_at") else None,
        "objectionMessage": row.get("objection_message"),
    }


def _mark_seen_if_needed(conn: psycopg.Connection, *, alert_id: str, user_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE platform_alert_recipients
               SET status = 'seen',
                   first_seen_at = COALESCE(first_seen_at, now()),
                   updated_at = now()
             WHERE alert_id = %s::uuid
               AND user_id = %s::uuid
               AND status = 'pending'
            """,
            (alert_id, user_id),
        )


@router.get("/ui", response_class=HTMLResponse)
def ui(_: Dict[str, Any] = Depends(require_roles_any("admin"))) -> HTMLResponse:
    return HTMLResponse(_read_html("ui.html"))


@router.get("/schema")
def schema(_: Dict[str, Any] = Depends(require_roles_any("admin"))) -> Dict[str, Any]:
    return {
        "kind": KIND,
        "version": AVISOS_VERSION,
        "supports": {
            "singleActiveAlert": True,
            "audited": True,
            "tabBadge": True,
            "dismissible": True,
            "objection": True,
        },
        "levels": sorted(LEVELS),
        "statuses": sorted(ALERT_STATUSES),
        "recipientStatuses": sorted(RECIPIENT_STATUSES),
        "defaults": {
            "level": "warning",
            "expiresInMinutes": 60,
            "allowDismiss": False,
            "objectionEnabled": True,
            "objectionRequiresMessage": True,
            "tabBadgeEnabled": True,
        },
    }


@router.get("")
def list_alerts(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: Dict[str, Any] = Depends(require_roles_any("admin")),
) -> Dict[str, Any]:
    if status and status not in ALERT_STATUSES:
        raise HTTPException(status_code=422, detail="Status inválido.")
    with _conn() as conn:
        with conn.transaction():
            _expire_old_alerts(conn)
        items = _list_alerts(conn, status=status, limit=limit, offset=offset)
    return {"items": items, "limit": limit, "offset": offset}


@router.post("")
def create_alert(
    body: CreateAlertIn,
    request: Request,
    admin: Dict[str, Any] = Depends(require_roles_any("admin")),
) -> Dict[str, Any]:
    with _conn() as conn:
        with conn.transaction():
            _expire_old_alerts(conn)

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id::text FROM platform_alerts WHERE status = 'published' LIMIT 1"
                )
                active = cur.fetchone()
                if active:
                    raise HTTPException(
                        status_code=409,
                        detail="Já existe um aviso global ativo. Encerre-o antes de publicar outro.",
                    )

            actor_user_id = _resolve_user_id(conn, request, admin)
            recipient_ids = _select_logged_in_user_ids(conn)
            if not recipient_ids:
                raise HTTPException(
                    status_code=409,
                    detail="Nenhum usuário com sessão ativa foi encontrado para receber o aviso.",
                )

            alert_id = str(uuid.uuid4())
            expires_at = _now_utc() + timedelta(minutes=int(body.expires_in_minutes))

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO platform_alerts
                      (
                        id,
                        title,
                        message,
                        level,
                        status,
                        created_by_user_id,
                        actor_cpf,
                        actor_nome,
                        actor_email,
                        published_at,
                        expires_at,
                        allow_dismiss,
                        objection_enabled,
                        objection_requires_message,
                        tab_badge_enabled
                      )
                    VALUES
                      (%s::uuid, %s, %s, %s, 'published', %s::uuid, %s, %s, %s, now(), %s, %s, %s, %s, %s)
                    """,
                    (
                        alert_id,
                        body.title.strip(),
                        body.message.strip(),
                        body.level,
                        actor_user_id,
                        admin.get("cpf"),
                        _actor_name(admin),
                        admin.get("email"),
                        expires_at,
                        bool(body.allow_dismiss),
                        bool(body.objection_enabled),
                        bool(body.objection_requires_message),
                        bool(body.tab_badge_enabled),
                    ),
                )
                cur.executemany(
                    """
                    INSERT INTO platform_alert_recipients (alert_id, user_id, status)
                    VALUES (%s::uuid, %s::uuid, 'pending')
                    ON CONFLICT DO NOTHING
                    """,
                    [(alert_id, uid) for uid in recipient_ids],
                )

            submission_id = _insert_submission(
                conn,
                kind=KIND,
                actor=admin,
                payload=body.model_dump(),
                result={
                    "alert_id": alert_id,
                    "recipient_count": len(recipient_ids),
                    "published_at": _now_utc().isoformat(),
                },
            )
            _insert_automation_audit(
                conn,
                actor=admin,
                action="publish",
                meta={
                    "alert_id": alert_id,
                    "submission_id": submission_id,
                    "recipient_count": len(recipient_ids),
                    "expires_at": expires_at.isoformat(),
                },
            )
            _insert_audit_event(
                conn,
                actor_user_id=actor_user_id,
                action="avisos.publish",
                object_id=alert_id,
                message="Aviso global publicado",
                metadata={
                    "recipient_count": len(recipient_ids),
                    "submission_id": submission_id,
                },
                request=request,
            )

        detail = _load_alert_detail(conn, alert_id)

    logger.info(
        "Aviso global publicado id=%s actor=%s recipients=%s",
        alert_id,
        _actor_name(admin),
        len(recipient_ids),
    )
    return {
        "ok": True,
        "item": detail,
    }


@router.get("/active")
def active_alert(_: Dict[str, Any] = Depends(require_roles_any("admin"))) -> Dict[str, Any]:
    with _conn() as conn:
        with conn.transaction():
            _expire_old_alerts(conn)
        items = _list_alerts(conn, status="published", limit=1, offset=0)
    return {"item": items[0] if items else None}


@router.get("/{alert_id}")
def get_alert_detail(
    alert_id: str,
    _: Dict[str, Any] = Depends(require_roles_any("admin")),
) -> Dict[str, Any]:
    with _conn() as conn:
        with conn.transaction():
            _expire_old_alerts(conn)
        return {"item": _load_alert_detail(conn, alert_id)}


@router.get("/{alert_id}/recipients")
def list_alert_recipients(
    alert_id: str,
    q: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    _: Dict[str, Any] = Depends(require_roles_any("admin")),
) -> Dict[str, Any]:
    with _conn() as conn:
        with conn.transaction():
            _expire_old_alerts(conn)
        items = _load_alert_recipients(conn, alert_id=alert_id, q=q, status=status)
    return {"items": items, "filters": {"q": q or "", "status": _normalize_recipient_status_filter(status)}}


@router.get("/{alert_id}/objections")
def list_alert_objections(
    alert_id: str,
    q: Optional[str] = Query(default=None),
    _: Dict[str, Any] = Depends(require_roles_any("admin")),
) -> Dict[str, Any]:
    with _conn() as conn:
        with conn.transaction():
            _expire_old_alerts(conn)
        items = _load_alert_objections(conn, alert_id=alert_id, q=q)
    return {"items": items, "filters": {"q": q or ""}}


@router.get("/{alert_id}/events")
def list_alert_events(
    alert_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    _: Dict[str, Any] = Depends(require_roles_any("admin")),
) -> Dict[str, Any]:
    with _conn() as conn:
        with conn.transaction():
            _expire_old_alerts(conn)
        items = _load_alert_events(conn, alert_id=alert_id, limit=limit)
    return {"items": items, "limit": limit}


@router.get("/{alert_id}/download")
def download_alert_report(
    alert_id: str,
    kind: Literal["recipients", "objections", "events"] = Query(default="recipients"),
    q: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    _: Dict[str, Any] = Depends(require_roles_any("admin")),
) -> Response:
    with _conn() as conn:
        with conn.transaction():
            _expire_old_alerts(conn)
        _load_alert_or_404(conn, alert_id)

        if kind == "recipients":
            items = _load_alert_recipients(conn, alert_id=alert_id, q=q, status=status)
            rows = [
                [
                    item.get("name"),
                    item.get("email"),
                    item.get("cpf"),
                    item.get("status"),
                    item.get("deliveredAt"),
                    item.get("firstSeenAt"),
                    item.get("respondedAt"),
                    item.get("confirmedAt"),
                    item.get("objectedAt"),
                    item.get("objectionMessage"),
                ]
                for item in items
            ]
            return _csv_response(
                filename=f"avisos-{alert_id}-destinatarios.csv",
                headers=[
                    "nome",
                    "email",
                    "cpf",
                    "status",
                    "entregue_em",
                    "primeira_visualizacao_em",
                    "respondido_em",
                    "confirmado_em",
                    "objetado_em",
                    "mensagem_objecao",
                ],
                rows=rows,
            )

        if kind == "objections":
            items = _load_alert_objections(conn, alert_id=alert_id, q=q)
            rows = [
                [
                    item.get("name"),
                    item.get("email"),
                    item.get("cpf"),
                    item.get("objectedAt"),
                    item.get("message"),
                ]
                for item in items
            ]
            return _csv_response(
                filename=f"avisos-{alert_id}-objecoes.csv",
                headers=["nome", "email", "cpf", "objetado_em", "mensagem"],
                rows=rows,
            )

        items = _load_alert_events(conn, alert_id=alert_id, limit=500)
        rows = [
            [
                item.get("at"),
                item.get("action"),
                item.get("message"),
                item.get("actorName"),
                item.get("actorEmail"),
                item.get("actorCpf"),
                item.get("ip"),
                (item.get("metadata") or {}),
            ]
            for item in items
        ]
        return _csv_response(
            filename=f"avisos-{alert_id}-eventos.csv",
            headers=["at", "acao", "mensagem", "ator_nome", "ator_email", "ator_cpf", "ip", "metadata"],
            rows=rows,
        )


@router.post("/{alert_id}/close")
def close_alert(
    alert_id: str,
    body: CloseAlertIn,
    request: Request,
    admin: Dict[str, Any] = Depends(require_roles_any("admin")),
) -> Dict[str, Any]:
    with _conn() as conn:
        with conn.transaction():
            _expire_old_alerts(conn)
            row = _load_alert_or_404(conn, alert_id)
            if row["status"] != "published":
                raise HTTPException(status_code=409, detail="Apenas avisos ativos podem ser encerrados.")

            actor_user_id = _resolve_user_id(conn, request, admin)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE platform_alerts
                       SET status = 'closed',
                           closed_at = now(),
                           closed_reason = %s,
                           closed_by_user_id = %s::uuid,
                           updated_at = now()
                     WHERE id = %s::uuid
                    """,
                    (body.reason or "closed_by_admin", actor_user_id, alert_id),
                )

            _insert_automation_audit(
                conn,
                actor=admin,
                action="close",
                meta={
                    "alert_id": alert_id,
                    "reason": body.reason or "closed_by_admin",
                },
            )
            _insert_audit_event(
                conn,
                actor_user_id=actor_user_id,
                action="avisos.close",
                object_id=alert_id,
                message="Aviso global encerrado",
                metadata={"reason": body.reason or "closed_by_admin"},
                request=request,
            )

        detail = _load_alert_detail(conn, alert_id)

    logger.info("Aviso global encerrado id=%s actor=%s", alert_id, _actor_name(admin))
    return {"ok": True, "item": detail}


@router.get("/mine/pending")
def my_pending_alerts(request: Request, user: Dict[str, Any] = Depends(require_auth)) -> Dict[str, Any]:
    with _conn() as conn:
        with conn.transaction():
            _expire_old_alerts(conn)
        user_id = _resolve_user_id(conn, request, user)
        if not user_id:
            return {"count": 0, "items": []}

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  a.id AS alert_id,
                  a.title,
                  a.message,
                  a.level,
                  a.status AS alert_status,
                  a.allow_dismiss,
                  a.objection_enabled,
                  a.objection_requires_message,
                  a.tab_badge_enabled,
                  a.created_at,
                  a.published_at,
                  a.expires_at,
                  r.user_id,
                  r.status AS recipient_status,
                  r.delivered_at,
                  r.first_seen_at,
                  r.responded_at,
                  r.confirmed_at,
                  r.objected_at,
                  r.objection_message
                FROM platform_alerts a
                JOIN platform_alert_recipients r
                  ON r.alert_id = a.id
                WHERE a.status = 'published'
                  AND a.expires_at > now()
                  AND r.user_id = %s::uuid
                  AND r.status IN ('pending', 'seen')
                ORDER BY a.published_at DESC, a.created_at DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall() or []

    items = [_recipient_item_out(dict(r)) for r in rows]
    return {"count": len(items), "items": items}


@router.post("/{alert_id}/seen")
def mark_seen(
    alert_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(require_auth),
) -> Dict[str, Any]:
    with _conn() as conn:
        with conn.transaction():
            _expire_old_alerts(conn)
            user_id = _resolve_user_id(conn, request, user)
            if not user_id:
                raise HTTPException(status_code=400, detail="Usuário da sessão sem vínculo persistido.")
            row = _active_recipient_for_user_or_404(conn, alert_id=alert_id, user_id=user_id)
            if row.get("alert_status") != "published" or (row.get("expires_at") and row.get("expires_at") <= _now_utc()):
                raise HTTPException(status_code=409, detail="Este aviso não está mais ativo.")
            _mark_seen_if_needed(conn, alert_id=alert_id, user_id=user_id)
            row = _active_recipient_for_user_or_404(conn, alert_id=alert_id, user_id=user_id)

    return {"ok": True, "item": _recipient_item_out(row)}


@router.post("/{alert_id}/confirm")
def confirm_alert(
    alert_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(require_auth),
) -> Dict[str, Any]:
    with _conn() as conn:
        with conn.transaction():
            _expire_old_alerts(conn)
            user_id = _resolve_user_id(conn, request, user)
            if not user_id:
                raise HTTPException(status_code=400, detail="Usuário da sessão sem vínculo persistido.")
            row = _active_recipient_for_user_or_404(conn, alert_id=alert_id, user_id=user_id)
            _ensure_alert_actionable(row)

            current_status = row.get("recipient_status")
            if current_status == "confirmed":
                return {"ok": True, "item": _recipient_item_out(row)}
            if current_status == "objected":
                raise HTTPException(status_code=409, detail="Este aviso já foi objetado por você.")

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE platform_alert_recipients
                       SET status = 'confirmed',
                           first_seen_at = COALESCE(first_seen_at, now()),
                           responded_at = now(),
                           confirmed_at = now(),
                           updated_at = now()
                     WHERE alert_id = %s::uuid
                       AND user_id = %s::uuid
                    """,
                    (alert_id, user_id),
                )

            _insert_automation_audit(
                conn,
                actor=user,
                action="confirm",
                meta={"alert_id": alert_id, "user_id": user_id},
            )
            _insert_audit_event(
                conn,
                actor_user_id=user_id,
                action="avisos.confirm",
                object_id=alert_id,
                message="Aviso global confirmado pelo destinatário",
                metadata={"user_id": user_id},
                request=request,
            )
            row = _active_recipient_for_user_or_404(conn, alert_id=alert_id, user_id=user_id)

    return {"ok": True, "item": _recipient_item_out(row)}


@router.post("/{alert_id}/object")
def object_alert(
    alert_id: str,
    body: ObjectionIn,
    request: Request,
    user: Dict[str, Any] = Depends(require_auth),
) -> Dict[str, Any]:
    msg = (body.message or "").strip()
    if not msg:
        raise HTTPException(status_code=422, detail="A mensagem da objeção é obrigatória.")

    with _conn() as conn:
        with conn.transaction():
            _expire_old_alerts(conn)
            user_id = _resolve_user_id(conn, request, user)
            if not user_id:
                raise HTTPException(status_code=400, detail="Usuário da sessão sem vínculo persistido.")
            row = _active_recipient_for_user_or_404(conn, alert_id=alert_id, user_id=user_id)
            _ensure_alert_actionable(row)

            current_status = row.get("recipient_status")
            if current_status == "objected":
                return {"ok": True, "item": _recipient_item_out(row)}
            if current_status == "confirmed":
                raise HTTPException(status_code=409, detail="Este aviso já foi confirmado por você.")
            if not bool(row.get("objection_enabled")):
                raise HTTPException(status_code=409, detail="Este aviso não aceita objeções.")
            if bool(row.get("objection_requires_message")) and not msg:
                raise HTTPException(status_code=422, detail="A mensagem da objeção é obrigatória.")

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE platform_alert_recipients
                       SET status = 'objected',
                           first_seen_at = COALESCE(first_seen_at, now()),
                           responded_at = now(),
                           objected_at = now(),
                           objection_message = %s,
                           updated_at = now()
                     WHERE alert_id = %s::uuid
                       AND user_id = %s::uuid
                    """,
                    (msg, alert_id, user_id),
                )

            _insert_automation_audit(
                conn,
                actor=user,
                action="object",
                meta={"alert_id": alert_id, "user_id": user_id},
            )
            _insert_audit_event(
                conn,
                actor_user_id=user_id,
                action="avisos.object",
                object_id=alert_id,
                message="Objeção registrada para aviso global",
                metadata={"user_id": user_id},
                request=request,
            )
            row = _active_recipient_for_user_or_404(conn, alert_id=alert_id, user_id=user_id)

    return {"ok": True, "item": _recipient_item_out(row)}
