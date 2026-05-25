# apps/bff/app/notifications.py
from __future__ import annotations

"""
Notificações (inbox) — Portal AGEPAR.
"""

import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import urljoin

import psycopg
from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.auth.rbac import require_auth, require_roles_any
from app.integrations.email_templates import build_notification_email_html
from app.integrations.expresso_mail import ExpressoMailError, get_expresso_mail_client

DATABASE_URL = os.getenv("DATABASE_URL")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _pg_conn() -> psycopg.Connection:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg.connect(DATABASE_URL, autocommit=True)


def _insert_audit_event(
    conn: psycopg.Connection,
    *,
    actor_user_id: Optional[uuid.UUID],
    action: str,
    obj_type: str,
    obj_id: str,
    message: str,
    metadata: Optional[Dict[str, Any]],
    ip: Optional[str],
    ua: Optional[str],
) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_events (actor_user_id, action, object_type, object_id, message, metadata, ip, user_agent)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    actor_user_id,
                    action,
                    obj_type,
                    obj_id,
                    message,
                    psycopg.types.json.Json(metadata or {}),
                    ip,
                    ua,
                ),
            )
    except Exception:
        return


def _user_uuid_from_session_user(user: Dict[str, Any]) -> uuid.UUID:
    raw = user.get("id")
    if not raw:
        raise HTTPException(status_code=409, detail="user has no id (cannot use notifications in this auth mode)")
    try:
        return uuid.UUID(str(raw))
    except Exception:
        raise HTTPException(status_code=422, detail="invalid user id in session")


def _normalize_level(level: Optional[str]) -> str:
    lv = (level or "info").strip().lower()
    if lv not in ("info", "success", "warning", "danger"):
        raise HTTPException(status_code=422, detail={"level": "invalid (use info|success|warning|danger)"})
    return lv


class NotificationOut(BaseModel):
    id: str
    title: str
    message: str
    level: str
    action_url: Optional[str] = Field(default=None, alias="actionUrl")
    created_at: str = Field(alias="createdAt")
    read_at: Optional[str] = Field(default=None, alias="readAt")
    meta: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class NotifyTargets(BaseModel):
    user_ids: List[str] = Field(default_factory=list, alias="userIds")
    role_names: List[str] = Field(default_factory=list, alias="roleNames")

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class SendNotificationIn(BaseModel):
    title: str
    message: str
    targets: NotifyTargets
    level: Optional[str] = "info"
    action_url: Optional[str] = Field(default=None, alias="actionUrl")
    meta: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class SendNotificationOut(BaseModel):
    id: str
    delivered: int

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


def _parse_default_roles() -> Set[str]:
    raw = os.getenv("AUTH_DEFAULT_ROLES", "")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return {p.lower() for p in parts}


def _normalize_email_address(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        result = validate_email(raw, check_deliverability=False)
    except EmailNotValidError:
        return None
    return result.normalized


def _select_recipient_email(
    *,
    email: Optional[str],
    email_institucional: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    email_inst_raw = (email_institucional or "").strip()
    if not email_inst_raw:
        return None, "email_institucional_blank"

    preferred = _normalize_email_address(email)
    if preferred:
        return preferred, None

    fallback = _normalize_email_address(email_inst_raw)
    if fallback:
        if (email or "").strip():
            return fallback, "email_fallback_to_institucional"
        return fallback, None

    if (email or "").strip():
        return None, "email_invalid_and_email_institucional_invalid"
    return None, "email_institucional_invalid"


def _resolve_email_targets(
    conn: psycopg.Connection,
    recipients: Sequence[uuid.UUID],
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    if not recipients:
        return [], []

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, COALESCE(name, '') AS name, email, email_institucional
            FROM users
            WHERE id = ANY(%s)
            """,
            (list(recipients),),
        )
        rows = cur.fetchall() or []

    ready: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []

    for user_id, name, email, email_institucional in rows:
        selected, reason = _select_recipient_email(
            email=email,
            email_institucional=email_institucional,
        )
        if not selected:
            skipped.append(
                {
                    "user_id": str(user_id),
                    "name": str(name or "").strip(),
                    "reason": reason or "email_not_available",
                    "has_email": "1" if str(email or "").strip() else "0",
                    "has_email_institucional": "1" if str(email_institucional or "").strip() else "0",
                }
            )
            continue

        if reason == "email_fallback_to_institucional":
            logger.info(
                "[NOTIFICATIONS] Fallback para email_institucional aplicado | user_id=%s | nome=%s",
                user_id,
                str(name or "").strip() or "-",
            )

        ready.append(
            {
                "user_id": str(user_id),
                "name": str(name or "").strip(),
                "email": selected,
            }
        )

    return ready, skipped


def _notification_email_subject(title: str) -> str:
    ttl = (title or "").strip()
    return f"[Plataforma Agepar] {ttl}" if ttl else "[Plataforma Agepar] Nova notificacao"


def _absolute_action_url(action_url: Optional[str]) -> Optional[str]:
    url = (action_url or "").strip()
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url

    base = (os.getenv("PORTAL_PUBLIC_BASE_URL", "") or "").strip()
    if base:
        return urljoin(base.rstrip("/") + "/", url.lstrip("/"))

    return url


def _notification_email_body(
    *,
    recipient_name: str,
    title: str,
    message: str,
    level: str,
    action_url: Optional[str],
    meta: Optional[Dict[str, Any]] = None,
) -> str:
    opened_url = _absolute_action_url(action_url)
    meta_obj = meta or {}
    kind = str(meta_obj.get("kind") or "").strip().lower()
    task_event = str(meta_obj.get("taskEvent") or "").strip().lower()

    intro = "Você recebeu uma nova notificação na Plataforma AGEPAR."
    if kind == "tasks":
        if task_event in {"task_assigned", "task_reassigned", "task_created", "task_completed"}:
            intro = "Você recebeu uma atualização do módulo de Gestão de Tarefas da Plataforma AGEPAR."
        else:
            intro = "Você recebeu uma notificação do módulo de Gestão de Tarefas da Plataforma AGEPAR."

    lines = [
        f"Olá, {recipient_name or 'servidor(a)'}.",
        "",
        intro,
        "",
        f"Título: {title}",
        f"Mensagem: {message}",
        f"Nível: {level}",
        f"Gerado em: {datetime.now(timezone.utc).astimezone().strftime('%d/%m/%Y %H:%M:%S')}",
    ]
    if opened_url:
        lines.extend(["", f"Abrir na plataforma: {opened_url}"])
    elif (action_url or "").strip():
        lines.extend(["", f"Caminho na plataforma: {action_url}"])

    lines.extend(
        [
            "",
            "Este e-mail foi enviado automaticamente pela Plataforma AGEPAR.",
            "Caso você já tenha tratado essa pendência, desconsidere esta mensagem.",
        ]
    )
    return "\n".join(lines)


def _dispatch_notification_emails(
    *,
    notification_id: str,
    title: str,
    message: str,
    level: str,
    action_url: Optional[str],
    email_targets: Sequence[Dict[str, str]],
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    client = get_expresso_mail_client()
    if not client.enabled:
        logger.info(
            "[NOTIFICATIONS] Integracao de e-mail do Expresso desabilitada/incompleta | notif=%s | recipients=%d",
            notification_id,
            len(email_targets),
        )
        return

    subject = _notification_email_subject(title)
    sent = 0
    failed = 0

    for target in email_targets:
        body_plain = _notification_email_body(
            recipient_name=target.get("name", ""),
            title=title,
            message=message,
            level=level,
            action_url=action_url,
            meta=meta,
        )
        body_html = build_notification_email_html(body_plain)

        try:
            client.send_mail(
                to=target["email"],
                subject=subject,
                body=body_html,
                msg_type="html",
            )
            sent += 1
            logger.info(
                "[NOTIFICATIONS] E-mail enviado via Expresso | notif=%s | user_id=%s",
                notification_id,
                target.get("user_id"),
            )
        except ExpressoMailError as exc:
            failed += 1
            logger.error(
                "[NOTIFICATIONS] Falha ao enviar e-mail via Expresso | notif=%s | user_id=%s | error=%s",
                notification_id,
                target.get("user_id"),
                exc,
            )
        except Exception:
            failed += 1
            logger.exception(
                "[NOTIFICATIONS] Erro inesperado ao enviar e-mail | notif=%s | user_id=%s",
                notification_id,
                target.get("user_id"),
            )

    logger.info(
        "[NOTIFICATIONS] Resumo do disparo de e-mails | notif=%s | sent=%d | failed=%d",
        notification_id,
        sent,
        failed,
    )


def _dispatch_notification_emails_async(
    *,
    notification_id: str,
    title: str,
    message: str,
    level: str,
    action_url: Optional[str],
    email_targets: Sequence[Dict[str, str]],
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    if not email_targets:
        return

    threading.Thread(
        target=_dispatch_notification_emails,
        kwargs={
            "notification_id": notification_id,
            "title": title,
            "message": message,
            "level": level,
            "action_url": action_url,
            "email_targets": list(email_targets),
            "meta": meta,
        },
        name=f"notif-email-{notification_id[:8]}",
        daemon=True,
    ).start()


def _resolve_role_user_ids(conn: psycopg.Connection, role_names: Sequence[str]) -> Set[uuid.UUID]:
    wanted = {r.strip().lower() for r in role_names if r and r.strip()}
    if not wanted:
        return set()

    default_roles = _parse_default_roles()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              u.id,
              u.is_superuser,
              COALESCE(array_agg(r.name) FILTER (WHERE r.name IS NOT NULL), ARRAY[]::text[]) AS roles
            FROM users u
            LEFT JOIN user_roles ur ON ur.user_id = u.id
            LEFT JOIN roles r ON r.id = ur.role_id
            WHERE u.status = 'active'
            GROUP BY u.id, u.is_superuser
            """
        )
        rows = cur.fetchall()

    out: Set[uuid.UUID] = set()
    for user_id, is_superuser, roles in rows:
        eff = {str(r).strip().lower() for r in (roles or []) if str(r).strip()} | set(default_roles)
        if is_superuser:
            eff.add("admin")
        if eff.intersection(wanted):
            out.add(user_id)

    return out


def _validate_user_ids(conn: psycopg.Connection, user_ids: Sequence[str]) -> Tuple[Set[uuid.UUID], List[str]]:
    raw = [s.strip() for s in user_ids if s and str(s).strip()]
    if not raw:
        return set(), []

    parsed: List[uuid.UUID] = []
    invalid: List[str] = []
    for s in raw:
        try:
            parsed.append(uuid.UUID(str(s)))
        except Exception:
            invalid.append(s)

    if invalid:
        return set(), invalid

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM users
            WHERE id = ANY(%s)
              AND status = 'active'
            """,
            (parsed,),
        )
        rows = cur.fetchall()

    ok = {r[0] for r in rows}
    missing = [str(u) for u in parsed if u not in ok]
    return ok, missing


def send_notification(
    *,
    actor: Optional[Dict[str, Any]],
    title: str,
    message: str,
    user_ids: Iterable[str] = (),
    role_names: Iterable[str] = (),
    level: str = "info",
    action_url: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    conn: Optional[psycopg.Connection] = None,
    ip: Optional[str] = None,
    ua: Optional[str] = None,
) -> Tuple[str, int]:
    ttl = (title or "").strip()
    msg = (message or "").strip()
    if not ttl:
        raise ValueError("title is required")
    if not msg:
        raise ValueError("message is required")

    lv = _normalize_level(level)

    role_names_l = list(role_names)
    user_ids_l = list(user_ids)

    owned_conn = False
    if conn is None:
        conn = _pg_conn()
        owned_conn = True

    try:
        role_user_ids = _resolve_role_user_ids(conn, role_names_l)

        direct_user_ids, invalid_or_missing_users = _validate_user_ids(conn, user_ids_l)
        if invalid_or_missing_users:
            raise HTTPException(status_code=422, detail={"userIds": {"invalid_or_missing": invalid_or_missing_users}})

        recipients: Set[uuid.UUID] = set(role_user_ids) | set(direct_user_ids)
        if not recipients:
            raise HTTPException(status_code=422, detail="targets produced no recipients")

        email_targets, email_skips = _resolve_email_targets(conn, list(recipients))

        actor_user_id = None
        actor_cpf = None
        actor_nome = None
        actor_email = None
        if actor:
            try:
                actor_user_id = uuid.UUID(str(actor.get("id"))) if actor.get("id") else None
            except Exception:
                actor_user_id = None
            actor_cpf = actor.get("cpf")
            actor_nome = actor.get("nome") or actor.get("name")
            actor_email = actor.get("email")

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notifications (created_by_user_id, actor_cpf, actor_nome, actor_email, title, message, level, action_url, meta)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    actor_user_id,
                    actor_cpf,
                    actor_nome,
                    actor_email,
                    ttl,
                    msg,
                    lv,
                    action_url,
                    psycopg.types.json.Json(meta or {}),
                ),
            )
            notif_id = cur.fetchone()[0]

            rows = [(notif_id, uid) for uid in recipients]
            cur.executemany(
                """
                INSERT INTO notification_recipients (notification_id, user_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                rows,
            )

        for skipped in email_skips:
            logger.warning(
                "[NOTIFICATIONS] E-mail não enviado para destinatário da notificação | notif=%s | user_id=%s | nome=%s | reason=%s | has_email=%s | has_email_institucional=%s",
                notif_id,
                skipped.get("user_id"),
                skipped.get("name") or "-",
                skipped.get("reason"),
                skipped.get("has_email"),
                skipped.get("has_email_institucional"),
            )

        _insert_audit_event(
            conn,
            actor_user_id=actor_user_id,
            action="notification.send",
            obj_type="notification",
            obj_id=str(notif_id),
            message=f"notification delivered to {len(recipients)} user(s)",
            metadata={
                "delivered": len(recipients),
                "role_names": role_names_l,
                "user_ids": user_ids_l,
                "level": lv,
                "action_url": action_url,
                "email": {
                    "planned": len(email_targets),
                    "skipped": len(email_skips),
                    "skip_reasons": sorted({item.get("reason", "unknown") for item in email_skips}),
                    "integration_enabled": get_expresso_mail_client().enabled,
                },
            },
            ip=ip,
            ua=ua,
        )

        _dispatch_notification_emails_async(
            notification_id=str(notif_id),
            title=ttl,
            message=msg,
            level=lv,
            action_url=action_url,
            email_targets=email_targets,
            meta=meta,
        )

        return str(notif_id), len(recipients)
    finally:
        if owned_conn and conn is not None:
            conn.close()


@router.get("", response_model=List[NotificationOut])
def list_my_notifications(
    request: Request,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    user: Dict[str, Any] = Depends(require_auth),
):
    uid = _user_uuid_from_session_user(user)

    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    with _pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT n.id, n.title, n.message, n.level, n.action_url, n.created_at, r.read_at, n.meta
            FROM notification_recipients r
            JOIN notifications n ON n.id = r.notification_id
            WHERE r.user_id = %s
              AND (%s = false OR r.read_at IS NULL)
            ORDER BY n.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (uid, unread_only, limit, offset),
        )
        rows = cur.fetchall()

    out: List[Dict[str, Any]] = []
    for (nid, title, message, level, action_url, created_at, read_at, meta) in rows:
        out.append(
            {
                "id": str(nid),
                "title": title,
                "message": message,
                "level": level,
                "actionUrl": action_url,
                "createdAt": created_at.isoformat() if created_at else None,
                "readAt": read_at.isoformat() if read_at else None,
                "meta": meta,
            }
        )
    return out


@router.get("/unread-count")
def unread_count(user: Dict[str, Any] = Depends(require_auth)) -> Dict[str, int]:
    uid = _user_uuid_from_session_user(user)
    with _pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM notification_recipients
            WHERE user_id = %s
              AND read_at IS NULL
            """,
            (uid,),
        )
        n = int(cur.fetchone()[0])
    return {"unread": n}


@router.post("/{notification_id}/read", status_code=204, response_class=Response)
def mark_read(notification_id: str, user: Dict[str, Any] = Depends(require_auth)):
    uid = _user_uuid_from_session_user(user)
    try:
        nid = uuid.UUID(notification_id)
    except Exception:
        raise HTTPException(status_code=422, detail="invalid notification id")

    with _pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE notification_recipients
            SET read_at = COALESCE(read_at, now())
            WHERE user_id = %s AND notification_id = %s
            """,
            (uid, nid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="notification not found for user")
    return Response(status_code=204)


@router.post("/read-all", status_code=204, response_class=Response)
def mark_all_read(user: Dict[str, Any] = Depends(require_auth)):
    uid = _user_uuid_from_session_user(user)
    with _pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE notification_recipients
            SET read_at = COALESCE(read_at, now())
            WHERE user_id = %s AND read_at IS NULL
            """,
            (uid,),
        )
    return Response(status_code=204)


@router.delete("/read", status_code=204, response_class=Response)
def delete_all_read_notifications(request: Request, user: Dict[str, Any] = Depends(require_auth)):
    uid = _user_uuid_from_session_user(user)
    actor_user_id = _user_uuid_from_session_user(user)

    with _pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM notification_recipients
            WHERE user_id = %s
              AND read_at IS NOT NULL
            """,
            (uid,),
        )
        removed = int(cur.rowcount or 0)

        cur.execute(
            """
            DELETE FROM notifications n
            WHERE NOT EXISTS (
              SELECT 1
              FROM notification_recipients r
              WHERE r.notification_id = n.id
            )
            """
        )

        _insert_audit_event(
            conn,
            actor_user_id=actor_user_id,
            action="delete",
            obj_type="notification",
            obj_id="bulk-read",
            message="Notificações lidas removidas da caixa de entrada do usuário",
            metadata={"removed": removed},
            ip=request.client.host if request.client else None,
            ua=request.headers.get("user-agent"),
        )

    return Response(status_code=204)


@router.delete("/{notification_id}", status_code=204, response_class=Response)
def delete_notification(notification_id: str, request: Request, user: Dict[str, Any] = Depends(require_auth)):
    uid = _user_uuid_from_session_user(user)
    actor_user_id = _user_uuid_from_session_user(user)
    try:
        nid = uuid.UUID(notification_id)
    except Exception:
        raise HTTPException(status_code=422, detail="invalid notification id")

    with _pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM notification_recipients
            WHERE user_id = %s AND notification_id = %s
            """,
            (uid, nid),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="notification not found for user")

        cur.execute(
            """
            DELETE FROM notifications n
            WHERE n.id = %s
              AND NOT EXISTS (
                SELECT 1
                FROM notification_recipients r
                WHERE r.notification_id = n.id
              )
            """,
            (nid,),
        )

        _insert_audit_event(
            conn,
            actor_user_id=actor_user_id,
            action="delete",
            obj_type="notification",
            obj_id=str(nid),
            message="Notificação removida da caixa de entrada do usuário",
            metadata={"notification_id": str(nid)},
            ip=request.client.host if request.client else None,
            ua=request.headers.get("user-agent"),
        )

    return Response(status_code=204)

@router.post(
    "/send",
    response_model=SendNotificationOut,
    dependencies=[Depends(require_roles_any("admin", "coordenador"))],
)
def send_notification_http(payload: SendNotificationIn, request: Request, user: Dict[str, Any] = Depends(require_auth)):
    try:
        notif_id, delivered = send_notification(
            actor=user,
            title=payload.title,
            message=payload.message,
            user_ids=payload.targets.user_ids,
            role_names=payload.targets.role_names,
            level=payload.level or "info",
            action_url=payload.action_url,
            meta=payload.meta,
            ip=request.client.host if request.client else None,
            ua=request.headers.get("user-agent"),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {"id": notif_id, "delivered": int(delivered)}
