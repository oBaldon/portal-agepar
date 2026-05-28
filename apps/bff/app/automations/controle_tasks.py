# apps/bff/app/automations/controle_tasks.py
from __future__ import annotations

"""
Painel de Controle — Tarefas (visão consolidada refinada).

Propósito
---------
Fornece uma UI e endpoints para a visão consolidada do módulo de tarefas dentro
do Painel de Controle/Auditoria, reutilizando e ampliando a camada gerencial da
automação `tasks`.

Escopo atual
------------
- UI HTML com visão gerencial refinada.
- API JSON para overview com filtros gerenciais.
- API JSON para atividade recente com filtros.
- API JSON para listagem drill-down de tarefas.
- API JSON para histórico de tarefa.
- Exportação semanal do compilado por cargo a notificar.
- Disparo manual controlado do e-mail semanal (admin/superuser).
"""

import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from app.auth.rbac import require_password_changed
from app.automations import tasks as tasks_automation
from app.automations.task_weekly_report import build_weekly_export_context, generate_weekly_task_report
from app.automations.task_weekly_email import send_weekly_task_emails
from app.db import _pg

logger = logging.getLogger(__name__)


_CONTROL_TASKS_ALLOWED_ROLES = {
    "admin",
    "coordenador",
    *{str(role).strip().lower() for role in tasks_automation._load_role_options()},
}


def require_control_tasks_access(request: Request) -> Dict[str, Any]:
    user = require_password_changed(request)
    roles = {str(r).strip().lower() for r in (user.get("roles") or []) if str(r).strip()}
    if user.get("is_superuser") is True or not roles.isdisjoint(_CONTROL_TASKS_ALLOWED_ROLES):
        return user
    raise HTTPException(status_code=403, detail="forbidden")


def require_control_tasks_email_admin(request: Request) -> Dict[str, Any]:
    user = require_control_tasks_access(request)
    roles = {str(r).strip().lower() for r in (user.get("roles") or []) if str(r).strip()}
    if user.get("is_superuser") is True or "admin" in roles:
        return user
    raise HTTPException(status_code=403, detail="forbidden")


router = APIRouter(
    prefix="/api/automations/controle/tarefas",
    tags=["automations", "controle", "tarefas"],
    dependencies=[Depends(require_control_tasks_access)],
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _parse_optional_uuid(value: Optional[str], field: str) -> Optional[UUID]:
    if value is None or not str(value).strip():
        return None
    try:
        return UUID(str(value).strip())
    except Exception:
        raise HTTPException(status_code=422, detail={field: "invalid uuid"})


def _parse_required_uuid(value: str, field: str) -> UUID:
    parsed = _parse_optional_uuid(value, field)
    if parsed is None:
        raise HTTPException(status_code=422, detail={field: "required"})
    return parsed


def _control_scope_context(user: Dict[str, Any]) -> Dict[str, Any]:
    return build_weekly_export_context(user)


def _control_scope_role_names(user: Dict[str, Any]) -> list[str]:
    context = _control_scope_context(user)
    return [str(role).strip().lower() for role in (context.get("roleNames") or []) if str(role).strip()]


def _has_full_control_scope(user: Dict[str, Any]) -> bool:
    return _control_scope_context(user).get("scope") == "full"


def _control_scope_where(user: Dict[str, Any], *, table_alias: str = "t") -> tuple[list[str], list[Any]]:
    if _has_full_control_scope(user):
        return ["TRUE"], []

    role_names = _control_scope_role_names(user)
    if not role_names:
        return ["FALSE"], []

    placeholders = ", ".join(["%s"] * len(role_names))
    return [f"COALESCE({table_alias}.assigned_role_name, '') IN ({placeholders})"], [*role_names]


def _task_is_in_control_scope(task: Dict[str, Any], user: Dict[str, Any]) -> bool:
    if _has_full_control_scope(user):
        return True

    task_role = str(task.get("assigned_role_name") or "").strip().lower()
    if not task_role:
        return False

    return task_role in set(_control_scope_role_names(user))


def _ensure_control_scope_visible(task: Dict[str, Any], user: Dict[str, Any]) -> None:
    if _task_is_in_control_scope(task, user):
        return
    raise HTTPException(status_code=403, detail="forbidden")


def _build_task_filters(
    *,
    user: Dict[str, Any],
    q: Optional[str] = None,
    status: Optional[str] = None,
    assigned_to_user_id: Optional[str] = None,
    source_kind: Optional[str] = None,
    overdue_only: bool = False,
    include_deleted: bool = False,
    table_alias: str = "t",
) -> tuple[list[str], list[Any]]:
    clauses, params = _control_scope_where(user, table_alias=table_alias)

    if not include_deleted:
        clauses.append(f"{table_alias}.deleted_at IS NULL")

    if q and str(q).strip():
        like = f"%{str(q).strip()}%"
        clauses.append(f"({table_alias}.title ILIKE %s OR COALESCE({table_alias}.description, '') ILIKE %s)")
        params.extend([like, like])

    if status and str(status).strip():
        clauses.append(f"{table_alias}.status = %s")
        params.append(tasks_automation._normalize_status(status))

    parsed_assignee = _parse_optional_uuid(assigned_to_user_id, "assignedToUserId")
    if parsed_assignee:
        clauses.append(f"{table_alias}.assigned_to_user_id = %s")
        params.append(parsed_assignee)

    if source_kind and str(source_kind).strip():
        clauses.append(f"COALESCE({table_alias}.source_kind, '') = %s")
        params.append(str(source_kind).strip())

    if overdue_only:
        clauses.append(
            f"{table_alias}.completed_at IS NULL AND {table_alias}.status <> 'cancelada' AND {table_alias}.due_date < CURRENT_DATE"
        )

    return clauses, params


@router.get("/ui", response_class=HTMLResponse)
def get_ui(request: Request):
    return templates.TemplateResponse("controle_tasks/ui.html", {"request": request})


@router.get("/schema")
def get_schema() -> Dict[str, Any]:
    return {
        "kind": "controle-tarefas",
        "phase": "3-weekly-export-and-email",
        "views": ["overview", "activity", "drilldown", "history", "weekly-export", "weekly-email"],
        "sourceAutomation": "tasks",
        "notes": (
            "Visão consolidada refinada do módulo de tarefas dentro do Painel de Controle, "
            "com exportação semanal por cargo a notificar e disparo manual controlado do e-mail semanal."
        ),
        "weeklyEmail": {
            "manualTriggerRequires": ["admin", "superuser"],
            "manualTriggerBehavior": (
                "Um envio manual real (dryRun=false) marca o cargo/período como já enviado. "
                "O scheduler automático poderá ignorar esse mesmo cargo na mesma semana, salvo uso de force=true."
            ),
        },
    }


@router.get("/config")
def get_config(user: Dict[str, Any] = Depends(require_control_tasks_access)) -> Dict[str, Any]:
    base = tasks_automation.get_config(user=user)
    return {
        "me": base.get("me", {}),
        "users": base.get("users", []),
        "statusValues": base.get("statusValues", []),
        "priorityValues": base.get("priorityValues", []),
        "eventCatalog": base.get("eventCatalog", {}),
        "defaultPeriodDays": 30,
        "weeklyExport": build_weekly_export_context(user),
        "weeklyEmail": {
            "manualTriggerRequires": ["admin", "superuser"],
            "manualTriggerBehavior": (
                "Envio manual real (dryRun=false) marca o cargo/período como já enviado. "
                "O scheduler automático poderá ignorar esse mesmo cargo na mesma semana, salvo uso de force=true."
            ),
        },
    }


@router.get("/overview")
def get_overview(
    period_days: int = Query(default=30, ge=7, le=365, alias="periodDays"),
    limit: int = Query(default=12, ge=5, le=50),
    q: Optional[str] = None,
    status: Optional[str] = None,
    assigned_to_user_id: Optional[str] = Query(default=None, alias="assignedToUserId"),
    source_kind: Optional[str] = Query(default=None, alias="sourceKind"),
    overdue_only: bool = Query(default=False, alias="overdueOnly"),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    user: Dict[str, Any] = Depends(require_control_tasks_access),
):
    clauses, params = _build_task_filters(
        user=user,
        q=q,
        status=status,
        assigned_to_user_id=assigned_to_user_id,
        source_kind=source_kind,
        overdue_only=overdue_only,
        include_deleted=include_deleted,
    )
    where_sql = " AND ".join(clauses)

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              COUNT(*) FILTER (WHERE t.completed_at IS NULL) AS open_tasks,
              COUNT(*) FILTER (WHERE t.created_at >= now() - (%s || ' days')::interval) AS created_in_period,
              COUNT(*) FILTER (WHERE t.completed_at IS NOT NULL AND t.completed_at >= now() - (%s || ' days')::interval) AS completed_in_period,
              COUNT(*) FILTER (WHERE t.completed_at IS NULL AND t.due_date < CURRENT_DATE AND t.status <> 'cancelada') AS overdue_tasks,
              COUNT(*) FILTER (WHERE t.completed_at IS NULL AND t.due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days' AND t.status <> 'cancelada') AS due_soon_tasks,
              COALESCE(AVG(EXTRACT(EPOCH FROM (t.completed_at - t.created_at))) FILTER (WHERE t.completed_at IS NOT NULL AND t.completed_at >= now() - (%s || ' days')::interval), 0) AS avg_lead_seconds
            FROM tasks t
            WHERE {where_sql}
            """,
            [period_days, period_days, period_days, *params],
        )
        totals = cur.fetchone()

        cur.execute(
            f"""
            SELECT
              t.assigned_to_user_id,
              COALESCE(u.name, 'Sem responsável') AS assignee_name,
              COUNT(*) FILTER (WHERE t.completed_at IS NULL) AS open_tasks,
              COUNT(*) FILTER (WHERE t.completed_at IS NULL AND t.due_date < CURRENT_DATE AND t.status <> 'cancelada') AS overdue_tasks,
              COUNT(*) FILTER (WHERE t.completed_at IS NOT NULL AND t.completed_at >= now() - (%s || ' days')::interval) AS completed_in_period,
              COALESCE(AVG(EXTRACT(EPOCH FROM (t.completed_at - t.created_at))) FILTER (WHERE t.completed_at IS NOT NULL AND t.completed_at >= now() - (%s || ' days')::interval), 0) AS avg_lead_seconds
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_to_user_id
            WHERE {where_sql}
            GROUP BY t.assigned_to_user_id, COALESCE(u.name, 'Sem responsável')
            HAVING COUNT(*) > 0
            ORDER BY open_tasks DESC, overdue_tasks DESC, assignee_name ASC
            LIMIT %s
            """,
            [period_days, period_days, *params, limit],
        )
        by_user_rows = cur.fetchall() or []

        cur.execute(
            f"""
            SELECT t.status, COUNT(*)::int AS total
            FROM tasks t
            WHERE {where_sql}
            GROUP BY t.status
            ORDER BY total DESC, t.status ASC
            """,
            params,
        )
        status_rows = cur.fetchall() or []

        cur.execute(
            f"""
            SELECT COALESCE(t.priority, 'media') AS priority, COUNT(*)::int AS total
            FROM tasks t
            WHERE {where_sql}
            GROUP BY COALESCE(t.priority, 'media')
            ORDER BY total DESC, priority ASC
            """,
            params,
        )
        priority_rows = cur.fetchall() or []

        cur.execute(
            f"""
            SELECT
              COALESCE(t.source_kind, 'manual') AS source_kind,
              COUNT(*)::int AS total
            FROM tasks t
            WHERE {where_sql}
            GROUP BY COALESCE(t.source_kind, 'manual')
            ORDER BY total DESC, source_kind ASC
            LIMIT %s
            """,
            [*params, min(limit, 20)],
        )
        source_rows = cur.fetchall() or []

        cur.execute(
            f"""
            SELECT
              COALESCE(t.assigned_role_name, 'sem_papel') AS role_name,
              COUNT(*)::int AS total
            FROM tasks t
            WHERE {where_sql}
            GROUP BY COALESCE(t.assigned_role_name, 'sem_papel')
            ORDER BY total DESC, role_name ASC
            LIMIT %s
            """,
            [*params, min(limit, 20)],
        )
        role_rows = cur.fetchall() or []

        cur.execute(
            f"""
            WITH days AS (
              SELECT generate_series(CURRENT_DATE - (%s::int - 1), CURRENT_DATE, INTERVAL '1 day')::date AS ref_date
            )
            SELECT
              d.ref_date,
              COALESCE(created.total, 0)::int AS created_total,
              COALESCE(completed.total, 0)::int AS completed_total
            FROM days d
            LEFT JOIN (
              SELECT created_at::date AS ref_date, COUNT(*)::int AS total
              FROM tasks t
              WHERE {where_sql}
                AND t.created_at >= now() - (%s || ' days')::interval
              GROUP BY created_at::date
            ) created ON created.ref_date = d.ref_date
            LEFT JOIN (
              SELECT completed_at::date AS ref_date, COUNT(*)::int AS total
              FROM tasks t
              WHERE {where_sql}
                AND t.completed_at IS NOT NULL
                AND t.completed_at >= now() - (%s || ' days')::interval
              GROUP BY completed_at::date
            ) completed ON completed.ref_date = d.ref_date
            ORDER BY d.ref_date ASC
            """,
            [period_days, *params, period_days, *params, period_days],
        )
        daily_rows = cur.fetchall() or []

        cur.execute(
            f"""
            SELECT
              t.id,
              t.title,
              t.status,
              t.completed_at,
              COALESCE(u.name, 'Sem responsável') AS assignee_name,
              EXTRACT(EPOCH FROM (t.completed_at - t.created_at)) AS lead_seconds
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_to_user_id
            WHERE {where_sql}
              AND t.completed_at IS NOT NULL
              AND t.completed_at >= now() - (%s || ' days')::interval
            ORDER BY t.completed_at DESC
            LIMIT %s
            """,
            [*params, period_days, min(limit, 15)],
        )
        recent_completed_rows = cur.fetchall() or []

    created_in_period = int(totals["created_in_period"] or 0)
    completed_in_period = int(totals["completed_in_period"] or 0)
    completion_rate = round((completed_in_period / created_in_period) * 100, 1) if created_in_period else 0.0

    return {
        "periodDays": period_days,
        "filters": {
            "q": q or "",
            "status": status or "",
            "assignedToUserId": assigned_to_user_id or "",
            "sourceKind": source_kind or "",
            "overdueOnly": overdue_only,
            "includeDeleted": include_deleted,
        },
        "totals": {
            "open": int(totals["open_tasks"] or 0),
            "createdInPeriod": created_in_period,
            "completedInPeriod": completed_in_period,
            "overdue": int(totals["overdue_tasks"] or 0),
            "dueSoon": int(totals["due_soon_tasks"] or 0),
            "avgLeadHours": round(float(totals["avg_lead_seconds"] or 0) / 3600, 2),
            "completionRatePercent": completion_rate,
        },
        "byUser": [
            {
                "userId": str(r["assigned_to_user_id"]) if r["assigned_to_user_id"] else "",
                "label": r["assignee_name"],
                "open": int(r["open_tasks"] or 0),
                "overdue": int(r["overdue_tasks"] or 0),
                "completedInPeriod": int(r["completed_in_period"] or 0),
                "avgLeadHours": round(float(r["avg_lead_seconds"] or 0) / 3600, 2),
            }
            for r in by_user_rows
        ],
        "byStatus": [
            {
                "status": r["status"],
                "label": tasks_automation._status_label(r["status"]),
                "total": int(r["total"] or 0),
            }
            for r in status_rows
        ],
        "byPriority": [
            {
                "priority": r["priority"],
                "label": str(r["priority"]).capitalize(),
                "total": int(r["total"] or 0),
            }
            for r in priority_rows
        ],
        "bySource": [
            {"sourceKind": r["source_kind"], "label": r["source_kind"], "total": int(r["total"] or 0)}
            for r in source_rows
        ],
        "byAssignedRole": [
            {"roleName": r["role_name"], "label": r["role_name"], "total": int(r["total"] or 0)}
            for r in role_rows
        ],
        "dailySeries": [
            {
                "date": tasks_automation._iso_date(r["ref_date"]),
                "created": int(r["created_total"] or 0),
                "completed": int(r["completed_total"] or 0),
            }
            for r in daily_rows
        ],
        "recentCompleted": [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "status": r["status"],
                "completedAt": tasks_automation._iso_dt(r["completed_at"]),
                "assigneeName": r["assignee_name"],
                "leadHours": round(float(r["lead_seconds"] or 0) / 3600, 2),
            }
            for r in recent_completed_rows
        ],
    }

@router.get("/activity")
def get_activity(
    limit: int = Query(default=25, ge=1, le=100),
    period_days: int = Query(default=30, ge=7, le=365, alias="periodDays"),
    q: Optional[str] = None,
    status: Optional[str] = None,
    assigned_to_user_id: Optional[str] = Query(default=None, alias="assignedToUserId"),
    event_type: Optional[str] = Query(default=None, alias="eventType"),
    user: Dict[str, Any] = Depends(require_control_tasks_access),
):
    clauses, params = _build_task_filters(
        user=user,
        q=q,
        status=status,
        assigned_to_user_id=assigned_to_user_id,
        include_deleted=True,
        table_alias="t",
    )
    clauses.append("e.created_at >= now() - (%s || ' days')::interval")
    params.append(period_days)

    if event_type and str(event_type).strip():
        clauses.append("e.event_type = %s")
        params.append(str(event_type).strip())

    where_sql = " AND ".join(clauses)

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              e.id,
              e.task_id,
              t.title AS task_title,
              t.status,
              t.assigned_to_user_id,
              e.event_type,
              e.old_value,
              e.new_value,
              e.metadata,
              e.created_at,
              e.actor_user_id,
              u.name AS actor_name,
              au.name AS assignee_name
            FROM task_events e
            JOIN tasks t ON t.id = e.task_id
            LEFT JOIN users u ON u.id = e.actor_user_id
            LEFT JOIN users au ON au.id = t.assigned_to_user_id
            WHERE {where_sql}
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT %s
            """,
            [*params, limit],
        )
        rows = cur.fetchall() or []

    return {
        "items": [
            {
                "id": int(r["id"]),
                "taskId": str(r["task_id"]),
                "taskTitle": r["task_title"],
                "taskStatus": r["status"],
                "assigneeName": r["assignee_name"],
                "assignedToUserId": str(r["assigned_to_user_id"]) if r["assigned_to_user_id"] else "",
                "eventType": r["event_type"],
                "eventLabel": tasks_automation._event_descriptor(r["event_type"]).get("label"),
                "eventCategory": tasks_automation._event_descriptor(r["event_type"]).get("category"),
                "eventSeverity": tasks_automation._event_descriptor(r["event_type"]).get("severity"),
                "oldValue": r.get("old_value"),
                "newValue": r.get("new_value"),
                "metadata": r.get("metadata"),
                "createdAt": tasks_automation._iso_dt(r["created_at"]),
                "actorUserId": str(r["actor_user_id"]) if r.get("actor_user_id") else None,
                "actorName": r.get("actor_name"),
            }
            for r in rows
        ]
    }


@router.get("/tasks")
def get_tasks(
    q: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    mine: bool = False,
    created_by_me: bool = Query(default=False, alias="createdByMe"),
    assigned_to_me: bool = Query(default=False, alias="assignedToMe"),
    assigned_to_user_id: Optional[str] = Query(default=None, alias="assignedToUserId"),
    source_kind: Optional[str] = Query(default=None, alias="sourceKind"),
    source_id: Optional[str] = Query(default=None, alias="sourceId"),
    overdue_only: bool = Query(default=False, alias="overdueOnly"),
    date_from: Optional[date] = Query(default=None, alias="dateFrom"),
    date_to: Optional[date] = Query(default=None, alias="dateTo"),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    user: Dict[str, Any] = Depends(require_control_tasks_access),
):
    clauses, params = _build_task_filters(
        user=user,
        q=q,
        status=status,
        assigned_to_user_id=assigned_to_user_id,
        source_kind=source_kind,
        overdue_only=overdue_only,
        include_deleted=include_deleted,
        table_alias="t",
    )

    if priority and str(priority).strip():
        clauses.append("t.priority = %s")
        params.append(tasks_automation._normalize_priority(priority))

    if source_id and str(source_id).strip():
        clauses.append("COALESCE(t.source_id, '') = %s")
        params.append(str(source_id).strip())

    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail={"dateRange": "dateFrom must be less than or equal to dateTo"})

    effective_start_expr = "COALESCE(t.start_date, t.due_date, DATE(t.created_at))"
    effective_end_expr = "COALESCE(t.due_date, t.start_date, DATE(t.created_at))"
    if date_from:
        clauses.append(f"{effective_end_expr} >= %s")
        params.append(date_from)
    if date_to:
        clauses.append(f"{effective_start_expr} <= %s")
        params.append(date_to)

    uid = tasks_automation._user_id_from_session(user)
    if mine:
        clauses.append("(t.created_by_user_id = %s OR t.assigned_to_user_id = %s)")
        params.extend([uid, uid])
    if created_by_me:
        clauses.append("t.created_by_user_id = %s")
        params.append(uid)
    if assigned_to_me:
        clauses.append("t.assigned_to_user_id = %s")
        params.append(uid)

    where_sql = " AND ".join(clauses) if clauses else "TRUE"

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              t.*,
              cu.name AS created_by_name,
              au.name AS assigned_to_name,
              lu.name AS last_updated_by_name,
              du.name AS deleted_by_name,
              COALESCE(cc.comment_count, 0) AS comment_count
            FROM tasks t
            LEFT JOIN users cu ON cu.id = t.created_by_user_id
            LEFT JOIN users au ON au.id = t.assigned_to_user_id
            LEFT JOIN users lu ON lu.id = t.last_updated_by_user_id
            LEFT JOIN users du ON du.id = t.deleted_by_user_id
            LEFT JOIN (
              SELECT task_id, COUNT(*)::int AS comment_count
              FROM task_comments
              GROUP BY task_id
            ) cc ON cc.task_id = t.id
            WHERE {where_sql}
            ORDER BY
              CASE t.status
                WHEN 'em_andamento' THEN 1
                WHEN 'a_fazer' THEN 2
                WHEN 'backlog' THEN 3
                WHEN 'concluida' THEN 4
                WHEN 'cancelada' THEN 5
                ELSE 99
              END ASC,
              t.due_date ASC NULLS LAST,
              t.updated_at DESC
            """,
            params,
        )
        rows = cur.fetchall() or []

    items: list[dict[str, Any]] = []
    for row in rows:
        item = tasks_automation._task_to_out(row, user)
        item["commentCount"] = int(row.get("comment_count") or 0)
        items.append(item)

    return {"items": items, "total": len(items)}


@router.get("/export-weekly")
def export_weekly_report(user: Dict[str, Any] = Depends(require_control_tasks_access)) -> Response:
    content, filename, _context = generate_weekly_task_report(user)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.post("/weekly-email/send")
def trigger_weekly_email_send(
    role_name: Optional[str] = Query(default=None, alias="roleName"),
    dry_run: bool = Query(default=False, alias="dryRun"),
    force: bool = Query(default=False),
    user: Dict[str, Any] = Depends(require_control_tasks_email_admin),
) -> Dict[str, Any]:
    return send_weekly_task_emails(
        actor=user,
        role_name=role_name,
        dry_run=dry_run,
        force=force,
    )


@router.get("/tasks/{task_id}/history")
def get_task_history(task_id: str, user: Dict[str, Any] = Depends(require_control_tasks_access)):
    task_uuid = _parse_required_uuid(task_id, "task id")

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              t.*,
              cu.name AS created_by_name,
              au.name AS assigned_to_name,
              lu.name AS last_updated_by_name,
              du.name AS deleted_by_name
            FROM tasks t
            LEFT JOIN users cu ON cu.id = t.created_by_user_id
            LEFT JOIN users au ON au.id = t.assigned_to_user_id
            LEFT JOIN users lu ON lu.id = t.last_updated_by_user_id
            LEFT JOIN users du ON du.id = t.deleted_by_user_id
            WHERE t.id = %s
            """,
            (task_uuid,),
        )
        task = cur.fetchone()

        if not task:
            raise HTTPException(status_code=404, detail="task not found")

        _ensure_control_scope_visible(task, user)

        cur.execute(
            """
            SELECT e.id, e.event_type, e.old_value, e.new_value, e.metadata, e.created_at, e.actor_user_id, u.name AS actor_name
            FROM task_events e
            LEFT JOIN users u ON u.id = e.actor_user_id
            WHERE e.task_id = %s
            ORDER BY e.created_at DESC, e.id DESC
            """,
            (task_uuid,),
        )
        rows = cur.fetchall() or []

    return {
        "items": [
            {
                "id": int(r["id"]),
                "eventType": r["event_type"],
                "eventLabel": tasks_automation._event_descriptor(r["event_type"]).get("label"),
                "eventCategory": tasks_automation._event_descriptor(r["event_type"]).get("category"),
                "eventSeverity": tasks_automation._event_descriptor(r["event_type"]).get("severity"),
                "summary": tasks_automation._event_summary(
                    r["event_type"],
                    r.get("old_value"),
                    r.get("new_value"),
                    r.get("metadata"),
                ),
                "oldValue": r.get("old_value"),
                "newValue": r.get("new_value"),
                "metadata": r.get("metadata"),
                "createdAt": tasks_automation._iso_dt(r["created_at"]),
                "actorUserId": str(r["actor_user_id"]) if r.get("actor_user_id") else None,
                "actorName": r.get("actor_name"),
            }
            for r in rows
        ]
    }
