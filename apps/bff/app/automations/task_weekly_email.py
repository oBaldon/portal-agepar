from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg
from fastapi import HTTPException

from app.automations import task_weekly_report
from app.db import DATABASE_URL, _pg
from app.integrations.email_templates import build_notification_email_html
from app.integrations.expresso_mail import ExpressoMailError, get_expresso_mail_client
from app.notifications import _resolve_email_targets

logger = logging.getLogger(__name__)

ROLE_ORDER = [str(role).strip().lower() for role in task_weekly_report._directory_roles()]
REPORT_TZ = ZoneInfo("America/Sao_Paulo")
SCHEDULER_ENABLED = str(os.getenv("TASK_WEEKLY_EMAIL_SCHEDULER_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"}
SCHEDULER_POLL_SECONDS = max(30, int(os.getenv("TASK_WEEKLY_EMAIL_SCHEDULER_POLL_SECONDS", "60")))
AUDIT_OBJECT_TYPE = "task_weekly_email"
_AUDIT_ACTOR_SYSTEM = None
_ADVISORY_LOCK_KEY = 904_170_319_501
_scheduler_thread: Optional[threading.Thread] = None
_scheduler_started = False


def _now_local(reference: Optional[datetime] = None) -> datetime:
    if reference is None:
        return datetime.now(REPORT_TZ)
    try:
        return reference.astimezone(REPORT_TZ)
    except Exception:
        return reference.replace(tzinfo=REPORT_TZ)


def _run_context(reference: Optional[datetime] = None) -> Dict[str, Any]:
    current = _now_local(reference)
    week_start, week_end = task_weekly_report._week_window(current)
    week_end_inclusive = week_end - task_weekly_report.timedelta(microseconds=1)
    return {
        "now": current,
        "weekStart": week_start,
        "weekEndExclusive": week_end,
        "weekEndInclusive": week_end_inclusive,
        "weekLabel": f"{week_start.date().isoformat()} a {week_end_inclusive.date().isoformat()}",
        "weekCadenceLabel": getattr(task_weekly_report, "BUSINESS_WEEK_LABEL", "segunda a sexta"),
        "runKey": f"{week_start.date().isoformat()}_{week_end_inclusive.date().isoformat()}",
        "timezone": "America/Sao_Paulo",
    }


def _is_full_export_user(user: Optional[Dict[str, Any]]) -> bool:
    if not user:
        return False
    return task_weekly_report._is_full_export_user(user)


def _require_scheduler_or_admin(actor: Optional[Dict[str, Any]]) -> None:
    if actor is None:
        return
    if _is_full_export_user(actor):
        return
    raise HTTPException(status_code=403, detail="forbidden")


def _normalize_role_name(role_name: str) -> str:
    role = str(role_name or "").strip().lower()
    if role not in ROLE_ORDER:
        raise HTTPException(status_code=422, detail={"roleName": f"invalid role (use {', '.join(ROLE_ORDER)})"})
    return role


def _manual_send_hint(*, dry_run: bool, force: bool) -> Optional[str]:
    if dry_run:
        return (
            "Pré-visualização manual: nenhum registro de envio é consolidado. "
            "O scheduler automático permanece elegível para esta semana."
        )
    if force:
        return (
            "Envio manual com force=true: esta execução reenviou cargos no mesmo período semanal, "
            "mesmo que já houvesse registro anterior de envio."
        )
    return (
        "Envio manual real: cada cargo enviado nesta execução passa a ser tratado como já enviado no período. "
        "Por padrão, o scheduler automático de sexta às 19h ignorará o mesmo cargo nesta semana. "
        "Use force=true apenas se precisar reenviar manualmente no mesmo período."
    )


def _attach_manual_send_note(payload: Dict[str, Any], *, actor: Optional[Dict[str, Any]], dry_run: bool, force: bool) -> None:
    if actor is None:
        return
    note = _manual_send_hint(dry_run=dry_run, force=force)
    if note:
        payload["operatorNote"] = note


def _fetch_active_user_ids_for_role(conn: psycopg.Connection, role_name: str) -> List[UUID]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.id
            FROM users u
            JOIN user_roles ur ON ur.user_id = u.id
            JOIN roles r ON r.id = ur.role_id
            WHERE u.status = 'active'
              AND LOWER(r.name) = %s
            ORDER BY u.name ASC, u.id ASC
            """,
            (role_name,),
        )
        rows = cur.fetchall() or []
    # app.db._pg() usa row_factory=dict_row; portanto cada linha aqui é um dict.
    # Antes este código acessava row[0], o que gerava KeyError(0) e aparecia
    # na API como "error": "0" durante o dryRun/envio semanal.
    return [row.get("id") for row in rows if row.get("id") is not None]


def _resolve_role_recipients(conn: psycopg.Connection, role_name: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    user_ids = _fetch_active_user_ids_for_role(conn, role_name)
    if not user_ids:
        return [], []
    ready, skipped = _resolve_email_targets(conn, user_ids)
    # dedup por e-mail para evitar reenvio duplicado em contas espelho
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in ready:
        email = str(item.get("email") or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        deduped.append(item)
    return deduped, skipped


def _role_label(role_name: str) -> str:
    return str(role_name or "").strip().upper()


def _build_role_subject(role_name: str, run_ctx: Dict[str, Any]) -> str:
    role_label = _role_label(role_name)
    return (
        f"[Plataforma Agepar] Gestão de Tarefas — Compilado semanal do cargo {role_label} "
        f"({run_ctx['weekLabel']})"
    )


def _build_role_body_plain(role_name: str, run_ctx: Dict[str, Any], *, task_count: int) -> str:
    role_label = _role_label(role_name)
    return "\n".join(
        [
            f"Prezada equipe {role_label},",
            "",
            "Encaminhamos o compilado semanal do módulo de Gestão de Tarefas da Plataforma Agepar.",
            f"Período de referência: {run_ctx['weekLabel']} ({run_ctx['weekCadenceLabel']}, horário de Brasília).",
            f"Quantidade de tarefas incluídas no anexo: {task_count}.",
            "",
            "O arquivo anexo reúne as tarefas que estiveram em andamento ou tiveram início, conclusão "
            "ou cancelamento dentro da semana útil considerada.",
            "Os dados refletem os registros disponíveis no momento da geração deste compilado.",
            "Solicitamos a gentileza de utilizar este material para acompanhamento e controle interno das atividades do cargo.",
            "",
            "Em caso de divergência nas informações, verifique o painel de Controle de Tarefas na Plataforma Agepar.",
            "",
            "Atenciosamente,",
            "Plataforma Agepar",
            "",
            "Mensagem automática. Não é necessário responder este e-mail.",
        ]
    )


def _role_attachment(role_name: str) -> tuple[bytes, str, Dict[str, Any]]:
    content, filename, context = task_weekly_report.generate_weekly_task_report_for_role(role_name)
    return content, filename, context


def _audit_event(
    conn: psycopg.Connection,
    *,
    action: str,
    message: str,
    metadata: Dict[str, Any],
    actor_user_id: Optional[str] = None,
) -> None:
    actor_uuid = None
    if actor_user_id:
        try:
            actor_uuid = UUID(str(actor_user_id))
        except Exception:
            actor_uuid = None

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_events (actor_user_id, action, object_type, object_id, message, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                actor_uuid,
                action,
                AUDIT_OBJECT_TYPE,
                str(metadata.get("runKey") or ""),
                message,
                psycopg.types.json.Json(metadata),
            ),
        )


def _sent_already(conn: psycopg.Connection, *, run_key: str, role_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM audit_events
            WHERE action = 'tasks.weekly_email.sent'
              AND object_type = %s
              AND COALESCE(metadata->>'runKey', '') = %s
              AND COALESCE(metadata->>'roleName', '') = %s
            LIMIT 1
            """,
            (AUDIT_OBJECT_TYPE, run_key, role_name),
        )
        return cur.fetchone() is not None


def send_weekly_task_email_for_role(
    role_name: str,
    *,
    actor: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
    force: bool = False,
    reference: Optional[datetime] = None,
) -> Dict[str, Any]:
    normalized_role = _normalize_role_name(role_name)
    if actor is not None:
        _require_scheduler_or_admin(actor)

    run_ctx = _run_context(reference)
    with _pg() as conn:
        trigger = "manual" if actor is not None else "scheduler"

        if (not dry_run) and (not force) and _sent_already(conn, run_key=run_ctx["runKey"], role_name=normalized_role):
            result = {
                "roleName": normalized_role,
                "status": "skipped_already_sent",
                "trigger": trigger,
                "dryRun": bool(dry_run),
                "runKey": run_ctx["runKey"],
                "weekLabel": run_ctx["weekLabel"],
                "sent": 0,
                "recipientCount": 0,
                "taskCount": 0,
                "filename": None,
                "skippedRecipients": [],
            }
            _attach_manual_send_note(result, actor=actor, dry_run=dry_run, force=force)
            _audit_event(
                conn,
                action="tasks.weekly_email.skipped",
                message=(
                    f"Compilado semanal de tarefas já enviado anteriormente para {_role_label(normalized_role)} "
                    f"no período {run_ctx['weekLabel']}. Para reenviar manualmente neste mesmo período, utilize force=true."
                ),
                metadata=result,
                actor_user_id=(actor or {}).get("id"),
            )
            return result

        recipients, skipped_recipients = _resolve_role_recipients(conn, normalized_role)
        content, filename, context = _role_attachment(normalized_role)
        task_count = int(context.get("sheetTaskCounts", {}).get(normalized_role, 0))

        result = {
            "roleName": normalized_role,
            "status": "dry_run" if dry_run else "ready",
            "trigger": trigger,
            "dryRun": bool(dry_run),
            "runKey": run_ctx["runKey"],
            "weekLabel": run_ctx["weekLabel"],
            "sent": 0,
            "recipientCount": len(recipients),
            "taskCount": task_count,
            "filename": filename,
            "skippedRecipients": skipped_recipients,
            "recipients": [
                {"userId": item.get("user_id"), "name": item.get("name"), "email": item.get("email")}
                for item in recipients
            ],
        }
        _attach_manual_send_note(result, actor=actor, dry_run=dry_run, force=force)

        if dry_run:
            _audit_event(
                conn,
                action="tasks.weekly_email.dry_run",
                message=(
                    f"Pré-visualização gerada do compilado semanal de tarefas do cargo {_role_label(normalized_role)} "
                    f"para o período {run_ctx['weekLabel']}"
                ),
                metadata=result,
                actor_user_id=(actor or {}).get("id"),
            )
            return result

        if not recipients:
            result["status"] = "skipped_no_recipients"
            _audit_event(
                conn,
                action="tasks.weekly_email.no_recipients",
                message=(
                    f"Envio semanal não realizado para o cargo {_role_label(normalized_role)}: "
                    "nenhum destinatário elegível foi encontrado."
                ),
                metadata=result,
                actor_user_id=(actor or {}).get("id"),
            )
            return result

        client = get_expresso_mail_client()
        if not client.enabled:
            result["status"] = "failed_mail_disabled"
            _audit_event(
                conn,
                action="tasks.weekly_email.failed",
                message=(
                    f"Envio semanal não realizado para o cargo {_role_label(normalized_role)}: "
                    "integração de e-mail indisponível."
                ),
                metadata=result,
                actor_user_id=(actor or {}).get("id"),
            )
            raise RuntimeError("Expresso mail integration is disabled or incomplete")

        subject = _build_role_subject(normalized_role, run_ctx)
        body_plain = _build_role_body_plain(normalized_role, run_ctx, task_count=task_count)
        body_html = build_notification_email_html(body_plain)

        try:
            client.send_mail(
                to=[item["email"] for item in recipients],
                subject=subject,
                body=body_html,
                msg_type="html",
                attachments=[
                    {
                        "filename": filename,
                        "content": content,
                        "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    }
                ],
            )
            result["status"] = "sent"
            result["sent"] = len(recipients)
            _audit_event(
                conn,
                action="tasks.weekly_email.sent",
                message=(
                    f"Compilado semanal de tarefas enviado com sucesso para o cargo {_role_label(normalized_role)} "
                    f"({len(recipients)} destinatário(s), {task_count} tarefa(s), período {run_ctx['weekLabel']})."
                ),
                metadata=result,
                actor_user_id=(actor or {}).get("id"),
            )
            logger.info(
                "[TASK_WEEKLY_EMAIL] Compilado semanal enviado | role=%s | recipients=%d | tasks=%d | run_key=%s",
                normalized_role,
                len(recipients),
                task_count,
                run_ctx["runKey"],
            )
            return result
        except ExpressoMailError as exc:
            result["status"] = "failed"
            result["error"] = str(exc)
            _audit_event(
                conn,
                action="tasks.weekly_email.failed",
                message=(
                    f"Falha ao enviar o compilado semanal de tarefas do cargo {_role_label(normalized_role)} "
                    f"para o período {run_ctx['weekLabel']}."
                ),
                metadata=result,
                actor_user_id=(actor or {}).get("id"),
            )
            logger.error(
                "[TASK_WEEKLY_EMAIL] Falha no envio semanal | role=%s | run_key=%s | error=%s",
                normalized_role,
                run_ctx["runKey"],
                exc,
            )
            raise
        except Exception as exc:
            result["status"] = "failed"
            result["error"] = str(exc)
            _audit_event(
                conn,
                action="tasks.weekly_email.failed",
                message=(
                    f"Falha inesperada ao processar o compilado semanal de tarefas do cargo {_role_label(normalized_role)} "
                    f"para o período {run_ctx['weekLabel']}."
                ),
                metadata=result,
                actor_user_id=(actor or {}).get("id"),
            )
            logger.exception(
                "[TASK_WEEKLY_EMAIL] Erro inesperado no envio semanal | role=%s | run_key=%s",
                normalized_role,
                run_ctx["runKey"],
            )
            raise


def send_weekly_task_emails(
    *,
    actor: Optional[Dict[str, Any]] = None,
    role_name: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False,
    reference: Optional[datetime] = None,
) -> Dict[str, Any]:
    if actor is not None:
        _require_scheduler_or_admin(actor)

    run_ctx = _run_context(reference)
    roles = [_normalize_role_name(role_name)] if role_name else list(ROLE_ORDER)

    items: list[Dict[str, Any]] = []
    sent = 0
    failures = 0
    skipped = 0
    dry_run_roles = 0

    for role in roles:
        try:
            item = send_weekly_task_email_for_role(
                role,
                actor=actor,
                dry_run=dry_run,
                force=force,
                reference=reference,
            )
            items.append(item)
            status = str(item.get("status") or "").strip().lower()
            if status == "sent":
                sent += 1
            elif status.startswith("failed"):
                failures += 1
            elif status == "dry_run":
                dry_run_roles += 1
            elif status.startswith("skipped"):
                skipped += 1
        except Exception as exc:
            failures += 1
            items.append(
                {
                    "roleName": role,
                    "status": "failed",
                    "dryRun": bool(dry_run),
                    "runKey": run_ctx["runKey"],
                    "weekLabel": run_ctx["weekLabel"],
                    "error": str(exc),
                }
            )

    summary = {
        "runKey": run_ctx["runKey"],
        "weekLabel": run_ctx["weekLabel"],
        "weekCadenceLabel": run_ctx["weekCadenceLabel"],
        "timezone": run_ctx["timezone"],
        "trigger": "manual" if actor is not None else "scheduler",
        "dryRun": bool(dry_run),
        "force": bool(force),
        "rolesProcessed": roles,
        "sentRoles": sent,
        "failedRoles": failures,
        "skippedRoles": skipped,
        "dryRunRoles": dry_run_roles,
        "items": items,
    }

    with _pg() as conn:
        _audit_event(
            conn,
            action="tasks.weekly_email.batch",
            message=(
                "Processamento em lote do envio semanal do compilado de tarefas "
                f"referente ao período {run_ctx['weekLabel']}"
            ),
            metadata=summary,
            actor_user_id=(actor or {}).get("id"),
        )

    return summary


def _should_run_now(now: datetime) -> bool:
    return now.weekday() == 4 and now.hour == 19


def _with_scheduler_lock(conn: psycopg.Connection) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s) AS locked", (_ADVISORY_LOCK_KEY,))
        locked = cur.fetchone()

    if not locked:
        return False
    if isinstance(locked, dict):
        return bool(locked.get("locked"))
    try:
        return bool(locked[0])
    except Exception:
        return False


def _release_scheduler_lock(conn: psycopg.Connection) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (_ADVISORY_LOCK_KEY,))
    except Exception:
        logger.exception("[TASK_WEEKLY_EMAIL] Falha ao liberar advisory lock do scheduler")


def run_scheduler_tick() -> Optional[Dict[str, Any]]:
    now = _now_local()
    if not _should_run_now(now):
        return None

    if not DATABASE_URL:
        logger.warning("[TASK_WEEKLY_EMAIL] Scheduler semanal ignorado: DATABASE_URL ausente")
        return None

    with _pg() as conn:
        if not _with_scheduler_lock(conn):
            logger.info("[TASK_WEEKLY_EMAIL] Scheduler semanal já está em execução em outra instância")
            return None

        try:
            run_ctx = _run_context(now)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM audit_events
                    WHERE action = 'tasks.weekly_email.batch'
                      AND object_type = %s
                      AND COALESCE(metadata->>'runKey', '') = %s
                      AND COALESCE(metadata->>'dryRun', 'false') = 'false'
                      AND COALESCE(metadata->>'trigger', '') = 'scheduler'
                    LIMIT 1
                    """,
                    (AUDIT_OBJECT_TYPE, run_ctx["runKey"]),
                )
                if cur.fetchone():
                    return None

            return send_weekly_task_emails(actor=None, dry_run=False, force=False, reference=now)
        finally:
            _release_scheduler_lock(conn)


def _scheduler_loop() -> None:
    logger.info(
        "[TASK_WEEKLY_EMAIL] Scheduler semanal iniciado | enabled=%s | poll_seconds=%d | timezone=%s",
        SCHEDULER_ENABLED,
        SCHEDULER_POLL_SECONDS,
        "America/Sao_Paulo",
    )
    while True:
        try:
            run_scheduler_tick()
        except Exception:
            logger.exception("[TASK_WEEKLY_EMAIL] Erro no scheduler semanal de tarefas")
        time.sleep(SCHEDULER_POLL_SECONDS)


def start_weekly_task_email_scheduler() -> None:
    global _scheduler_thread, _scheduler_started

    if _scheduler_started:
        return
    _scheduler_started = True

    if not SCHEDULER_ENABLED:
        logger.info("[TASK_WEEKLY_EMAIL] Scheduler semanal desabilitado por configuração")
        return

    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        name="task-weekly-email-scheduler",
        daemon=True,
    )
    _scheduler_thread.start()
