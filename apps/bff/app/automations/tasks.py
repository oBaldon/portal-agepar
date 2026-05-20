# apps/bff/app/automations/tasks.py
from __future__ import annotations

"""
Automação "Tarefas" — gestão operacional simples.

Escopo da Fase 1B
-----------------
- CRUD básico de tarefas
- alteração de status
- comentários
- histórico de eventos
- exclusão lógica
- UI HTML simples (lista + kanban + calendário semanal/mensal)

Observações
-----------
- O módulo foi desenhado para usuários autenticados.
- Admin/coordenador possuem visão ampliada; demais usuários veem tarefas que
  criaram ou que lhes foram atribuídas.
- A base foi preparada para evoluir no futuro com calendário, métricas e
  gatilhos de notificação.
"""

import logging
import pathlib
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from psycopg.types.json import Json
from pydantic import BaseModel, ConfigDict, model_validator, field_validator

from app.auth.rbac import require_password_changed
from app.db import _pg, add_audit
from app.notifications import send_notification

logger = logging.getLogger(__name__)

KIND = "tasks"
TASKS_VERSION = "0.7.0"

router = APIRouter(
    prefix="/api/automations/tasks",
    tags=["automations:tasks"],
    dependencies=[Depends(require_password_changed)],
)

_TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates" / "tasks"

_STATUS_VALUES = ("a_fazer", "em_andamento", "em_revisao", "concluida", "cancelada")
_STATUS_SET = set(_STATUS_VALUES)
_PRIORITY_VALUES = {"baixa", "media", "alta", "urgente"}
_STATUS_LABELS = {
    "a_fazer": "A fazer",
    "em_andamento": "Em andamento",
    "em_revisao": "Em revisão",
    "concluida": "Concluída",
    "cancelada": "Cancelada",
}
_STATUS_FLOW = {
    "a_fazer": {"next": "em_andamento", "label": "Iniciar"},
    "em_andamento": {"next": "concluida", "label": "Concluir"},
    "concluida": {"next": "em_revisao", "label": "Revisar"},
    "em_revisao": {"next": "concluida", "label": "Aprovar revisão"},
    "cancelada": None,
}

_EVENT_CATALOG: Dict[str, Dict[str, str]] = {
    "task_created": {"label": "Tarefa criada", "category": "lifecycle", "severity": "info"},
    "task_updated": {"label": "Tarefa atualizada", "category": "change", "severity": "info"},
    "task_status_changed": {"label": "Status alterado", "category": "workflow", "severity": "info"},
    "task_assigned": {"label": "Responsável definido", "category": "assignment", "severity": "info"},
    "task_reassigned": {"label": "Responsável alterado", "category": "assignment", "severity": "warning"},
    "task_completed": {"label": "Tarefa concluída", "category": "workflow", "severity": "success"},
    "task_cancelled": {"label": "Tarefa cancelada", "category": "workflow", "severity": "warning"},
    "task_deleted": {"label": "Tarefa excluída logicamente", "category": "lifecycle", "severity": "danger"},
    "task_restored": {"label": "Tarefa restaurada", "category": "lifecycle", "severity": "success"},
    "task_comment_added": {"label": "Comentário adicionado", "category": "collaboration", "severity": "info"},
    "task_in_review": {"label": "Tarefa em revisão", "category": "workflow", "severity": "warning"},
    "task_due_date_changed": {"label": "Prazo alterado", "category": "change", "severity": "warning"},
}

_TASK_NOTIFICATION_RULES: Dict[str, Dict[str, Any]] = {
    "task_created": {
        "enabled": True,
        "notifyAssignee": True,
        "notifyAssignedRole": True,
        "notifyCreator": False,
        "title": "Nova tarefa atribuída",
    },
    "task_assigned": {
        "enabled": True,
        "notifyAssignee": True,
        "notifyAssignedRole": True,
        "notifyCreator": False,
        "title": "Você recebeu uma tarefa",
    },
    "task_reassigned": {
        "enabled": True,
        "notifyAssignee": True,
        "notifyAssignedRole": True,
        "notifyCreator": False,
        "title": "Tarefa reatribuída",
    },
    "task_completed": {
        "enabled": True,
        "notifyAssignee": False,
        "notifyAssignedRole": False,
        "notifyCreator": True,
        "title": "Tarefa concluída",
    },
    "task_cancelled": {
        "enabled": True,
        "notifyAssignee": True,
        "notifyAssignedRole": True,
        "notifyCreator": True,
        "title": "Tarefa cancelada",
    },
    "task_restored": {
        "enabled": True,
        "notifyAssignee": True,
        "notifyAssignedRole": True,
        "notifyCreator": True,
        "title": "Tarefa restaurada",
    },
    "task_comment_added": {
        "enabled": True,
        "notifyAssignee": True,
        "notifyAssignedRole": False,
        "notifyCreator": True,
        "title": "Novo comentário em tarefa",
    },
    "task_in_review": {
        "enabled": True,
        "notifyAssignee": False,
        "notifyAssignedRole": True,
        "notifyCreator": True,
        "title": "Tarefa em revisão",
    },
}


def _read_html(name: str) -> str:
    return (_TEMPLATES_DIR / name).read_text(encoding="utf-8")


def _parse_uuid(raw: Any, field_name: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except Exception:
        raise HTTPException(status_code=422, detail=f"invalid {field_name}")


def _user_id_from_session(user: Dict[str, Any]) -> uuid.UUID:
    raw = user.get("id")
    if not raw:
        raise HTTPException(status_code=409, detail="user has no id in session")
    return _parse_uuid(raw, "user id")


def _norm_roles(user: Dict[str, Any]) -> set[str]:
    roles = user.get("roles") or []
    return {str(r).strip().lower() for r in roles if str(r).strip()}


def _is_elevated(user: Dict[str, Any]) -> bool:
    if user.get("is_superuser") is True:
        return True
    roles = _norm_roles(user)
    return bool({"admin", "coordenador"} & roles)


def _ensure_elevated(user: Dict[str, Any]) -> None:
    if not _is_elevated(user):
        raise HTTPException(status_code=403, detail="forbidden")


def _status_label(value: Optional[str]) -> str:
    key = str(value or "").strip().lower()
    return _STATUS_LABELS.get(key, key or "-")


def _normalize_status(value: Optional[str]) -> str:
    status = (value or "a_fazer").strip().lower()
    if status == "backlog":
        status = "a_fazer"
    if status not in _STATUS_SET:
        raise HTTPException(status_code=422, detail={"status": f"invalid (use {list(_STATUS_VALUES)})"})
    return status


def _normalize_priority(value: Optional[str]) -> str:
    priority = (value or "media").strip().lower()
    if priority not in _PRIORITY_VALUES:
        raise HTTPException(status_code=422, detail={"priority": f"invalid (use {sorted(_PRIORITY_VALUES)})"})
    return priority


def _normalize_text(value: Optional[str], *, field_name: str, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise HTTPException(status_code=422, detail={field_name: "required"})
    return text


def _iso_dt(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _iso_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _task_scope_where(user: Dict[str, Any]) -> tuple[str, list[Any]]:
    if _is_elevated(user):
        return "TRUE", []

    uid = _user_id_from_session(user)
    return "(t.created_by_user_id = %s OR t.assigned_to_user_id = %s)", [uid, uid]


def _task_event_scope_where(user: Dict[str, Any]) -> tuple[str, list[Any]]:
    if _is_elevated(user):
        return "TRUE", []

    uid = _user_id_from_session(user)
    return "(t.created_by_user_id = %s OR t.assigned_to_user_id = %s)", [uid, uid]


def _load_task_row(task_id: uuid.UUID) -> Optional[Dict[str, Any]]:
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
            (task_id,),
        )
        return cur.fetchone()


def _ensure_visible(task: Dict[str, Any], user: Dict[str, Any]) -> None:
    if _is_elevated(user):
        return
    uid = _user_id_from_session(user)
    if task["created_by_user_id"] != uid and task["assigned_to_user_id"] != uid:
        raise HTTPException(status_code=403, detail="forbidden")


def _ensure_not_deleted(task: Dict[str, Any]) -> None:
    if task.get("deleted_at") is not None:
        raise HTTPException(status_code=409, detail="task is deleted")


def _ensure_can_edit(task: Dict[str, Any], user: Dict[str, Any]) -> None:
    if _is_elevated(user):
        return
    uid = _user_id_from_session(user)
    if task["created_by_user_id"] != uid:
        raise HTTPException(status_code=403, detail="only the creator can edit this task")


def _ensure_can_change_status(task: Dict[str, Any], user: Dict[str, Any]) -> None:
    if _is_elevated(user):
        return
    uid = _user_id_from_session(user)
    if task["created_by_user_id"] != uid and task["assigned_to_user_id"] != uid:
        raise HTTPException(status_code=403, detail="only the creator or assignee can change task status")


def _ensure_can_delete(task: Dict[str, Any], user: Dict[str, Any]) -> None:
    if _is_elevated(user):
        return
    uid = _user_id_from_session(user)
    if task["created_by_user_id"] != uid:
        raise HTTPException(status_code=403, detail="only the creator can delete this task")


def _ensure_can_restore(task: Dict[str, Any], user: Dict[str, Any]) -> None:
    if _is_elevated(user):
        return
    uid = _user_id_from_session(user)
    if task["created_by_user_id"] != uid:
        raise HTTPException(status_code=403, detail="only the creator can restore this task")


def _task_flags(task: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, bool]:
    is_deleted = task.get("deleted_at") is not None
    if _is_elevated(user):
        return {
            "canEdit": not is_deleted,
            "canChangeStatus": not is_deleted,
            "canDelete": not is_deleted,
            "canRestore": bool(is_deleted),
        }

    uid = _user_id_from_session(user)
    is_creator = task["created_by_user_id"] == uid
    is_assignee = task["assigned_to_user_id"] == uid
    return {
        "canEdit": bool(is_creator and not is_deleted),
        "canChangeStatus": bool((is_creator or is_assignee) and not is_deleted),
        "canDelete": bool(is_creator and not is_deleted),
        "canRestore": bool(is_creator and is_deleted),
    }


def _task_to_out(task: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    flags = _task_flags(task, user)
    task_status = "a_fazer" if task.get("status") == "backlog" else task.get("status")
    due_date = task.get("due_date")
    is_overdue = (
        due_date is not None
        and task.get("completed_at") is None
        and task.get("deleted_at") is None
        and due_date < date.today()
    )
    return {
        "id": str(task["id"]),
        "title": task["title"],
        "description": task.get("description") or "",
        "status": task_status,
        "priority": task["priority"],
        "startDate": _iso_date(task.get("start_date")),
        "dueDate": _iso_date(task.get("due_date")),
        "completedAt": _iso_dt(task.get("completed_at")),
        "createdAt": _iso_dt(task.get("created_at")),
        "updatedAt": _iso_dt(task.get("updated_at")),
        "deletedAt": _iso_dt(task.get("deleted_at")),
        "createdByUserId": str(task["created_by_user_id"]) if task.get("created_by_user_id") else None,
        "assignedToUserId": str(task["assigned_to_user_id"]) if task.get("assigned_to_user_id") else None,
        "lastUpdatedByUserId": str(task["last_updated_by_user_id"]) if task.get("last_updated_by_user_id") else None,
        "deletedByUserId": str(task["deleted_by_user_id"]) if task.get("deleted_by_user_id") else None,
        "createdByName": task.get("created_by_name"),
        "assignedToName": task.get("assigned_to_name"),
        "lastUpdatedByName": task.get("last_updated_by_name"),
        "deletedByName": task.get("deleted_by_name"),
        "sourceKind": task.get("source_kind"),
        "sourceId": task.get("source_id"),
        "assignedRoleName": task.get("assigned_role_name"),
        "isOverdue": is_overdue,
        **flags,
    }


def _serialize_json(value: Optional[Dict[str, Any]]) -> Any:
    return Json(value or {})


def _record_task_event(
    *,
    task_id: uuid.UUID,
    actor_user_id: Optional[uuid.UUID],
    event_type: str,
    old_value: Optional[Dict[str, Any]] = None,
    new_value: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO task_events (task_id, actor_user_id, event_type, old_value, new_value, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                task_id,
                actor_user_id,
                event_type,
                _serialize_json(old_value),
                _serialize_json(new_value),
                _serialize_json(metadata),
            ),
        )


def _task_snapshot(task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": task.get("title"),
        "description": task.get("description"),
        "status": task.get("status"),
        "priority": task.get("priority"),
        "startDate": _iso_date(task.get("start_date")),
        "dueDate": _iso_date(task.get("due_date")),
        "completedAt": _iso_dt(task.get("completed_at")),
        "assignedToUserId": str(task["assigned_to_user_id"]) if task.get("assigned_to_user_id") else None,
        "assignedRoleName": task.get("assigned_role_name"),
        "sourceKind": task.get("source_kind"),
        "sourceId": task.get("source_id"),
        "deletedAt": _iso_dt(task.get("deleted_at")),
    }


def _event_descriptor(event_type: str) -> Dict[str, str]:
    base = _EVENT_CATALOG.get(event_type)
    if base:
        return dict(base)
    return {"label": event_type, "category": "other", "severity": "info"}


def _event_summary(
    event_type: str,
    old_value: Optional[Dict[str, Any]],
    new_value: Optional[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]],
) -> str:
    old_value = old_value or {}
    new_value = new_value or {}
    metadata = metadata or {}

    if event_type == "task_status_changed":
        old_status = old_value.get("status")
        new_status = new_value.get("status")
        if old_status and new_status:
            return f"Status: {old_status} → {new_status}"
    if event_type in {"task_assigned", "task_reassigned"}:
        old_name = (old_value.get("assigned_to_name") or old_value.get("assignedToName") or "").strip()
        new_name = (new_value.get("assigned_to_name") or new_value.get("assignedToName") or "").strip()
        if old_name and new_name:
            return f"Responsável: {old_name} → {new_name}"
        if new_name:
            return f"Responsável definido: {new_name}"
    if event_type == "task_comment_added":
        body = str(
            metadata.get("comment_preview")
            or metadata.get("commentPreview")
            or new_value.get("body")
            or ""
        ).strip()
        if body:
            return body[:180]
        return "Comentário registrado na tarefa."
    if event_type == "task_deleted":
        return "Tarefa removida das visualizações ativas."
    if event_type == "task_restored":
        return "Tarefa restaurada para as visualizações ativas."
    if event_type == "task_completed":
        return "Tarefa marcada como concluída."
    if event_type == "task_cancelled":
        return "Tarefa cancelada."
    if event_type == "task_created":
        return "Tarefa criada."
    if event_type == "task_updated":
        changed = metadata.get("changed_fields") or metadata.get("changedFields") or []
        if isinstance(changed, list) and changed:
            return "Campos alterados: " + ", ".join(str(x) for x in changed[:6])
        return "Dados da tarefa atualizados."
    return ""


def _normalize_role_name(value: Optional[str]) -> Optional[str]:
    role = str(value or "").strip().lower()
    return role or None


def _task_notification_targets(
    *,
    event_type: str,
    task: Dict[str, Any],
    actor_user_id: Optional[uuid.UUID],
) -> tuple[list[str], list[str]]:
    rule = _TASK_NOTIFICATION_RULES.get(event_type) or {}
    if not rule.get("enabled"):
        return [], []

    actor_raw = str(actor_user_id) if actor_user_id else None
    creator_raw = str(task["created_by_user_id"]) if task.get("created_by_user_id") else None
    assignee_raw = str(task["assigned_to_user_id"]) if task.get("assigned_to_user_id") else None
    role_name = _normalize_role_name(task.get("assigned_role_name"))

    user_ids: list[str] = []
    role_names: list[str] = []

    if rule.get("notifyAssignee") and assignee_raw and assignee_raw != actor_raw:
        user_ids.append(assignee_raw)
    if rule.get("notifyCreator") and creator_raw and creator_raw != actor_raw:
        user_ids.append(creator_raw)
    if rule.get("notifyAssignedRole") and role_name:
        role_names.append(role_name)

    user_ids = list(dict.fromkeys(user_ids))
    role_names = list(dict.fromkeys(role_names))
    return user_ids, role_names


def _task_notification_message(
    *,
    event_type: str,
    task: Dict[str, Any],
    actor: Dict[str, Any],
) -> str:
    title = str(task.get("title") or "").strip() or "Sem título"
    due_date = _iso_date(task.get("due_date"))
    actor_name = str(actor.get("nome") or actor.get("name") or "um usuário").strip() or "um usuário"

    if event_type in {"task_created", "task_assigned", "task_reassigned"}:
        base = f'A tarefa "{title}" foi atribuída para acompanhamento.'
    elif event_type == "task_completed":
        base = f'A tarefa "{title}" foi concluída por {actor_name}.'
    elif event_type == "task_cancelled":
        base = f'A tarefa "{title}" foi cancelada por {actor_name}.'
    elif event_type == "task_restored":
        base = f'A tarefa "{title}" foi restaurada por {actor_name}.'
    elif event_type == "task_comment_added":
        base = f'{actor_name} adicionou um comentário na tarefa "{title}".'
    else:
        base = f'Houve uma atualização na tarefa "{title}".'

    if due_date:
        base += f" Prazo: {due_date}."
    if task.get("source_kind"):
        base += f" Origem: {task.get('source_kind')}."
    return base


def _dispatch_task_notification(
    *,
    event_type: str,
    task: Dict[str, Any],
    actor: Dict[str, Any],
) -> None:
    rule = _TASK_NOTIFICATION_RULES.get(event_type)
    if not rule or not rule.get("enabled"):
        return

    actor_user_id = _user_id_from_session(actor)
    user_ids, role_names = _task_notification_targets(
        event_type=event_type,
        task=task,
        actor_user_id=actor_user_id,
    )
    if not user_ids and not role_names:
        return

    notif_title = str(rule.get("title") or "Atualização de tarefa").strip()
    notif_message = _task_notification_message(event_type=event_type, task=task, actor=actor)

    notif_level = "info"
    if event_type in {"task_completed", "task_restored"}:
        notif_level = "success"
    elif event_type in {"task_cancelled", "task_in_review", "task_due_date_changed"}:
        notif_level = "warning"

    try:
        notif_id, delivered = send_notification(
            actor=actor,
            title=notif_title,
            message=notif_message,
            user_ids=user_ids,
            role_names=role_names,
            level=notif_level,
            action_url="/tarefas",
            meta={
                "kind": "tasks",
                "taskId": str(task["id"]),
                "taskEvent": event_type,
                "sourceKind": task.get("source_kind"),
                "sourceId": task.get("source_id"),
                "assignedRoleName": task.get("assigned_role_name"),
            },
        )
        logger.info(
            "[TASKS] Notificação disparada | task=%s | event=%s | notif=%s | delivered=%d",
            task["id"],
            event_type,
            notif_id,
            delivered,
        )
    except Exception:
        logger.exception(
            "[TASKS] Falha não bloqueante ao disparar notificação | task=%s | event=%s",
            task.get("id"),
            event_type,
        )


def _validate_dates(start_date: Optional[date], due_date: Optional[date]) -> None:
    if start_date and due_date and start_date > due_date:
        raise HTTPException(status_code=422, detail={"dueDate": "must be greater than or equal to startDate"})


def _load_users_for_picker(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, email
            FROM users
            WHERE status = 'active'
            ORDER BY name ASC
            """
        )
        rows = cur.fetchall() or []

    return [{"id": str(r["id"]), "name": r["name"], "email": r.get("email")} for r in rows]


class TaskCreateIn(BaseModel):
    title: str
    description: Optional[str] = ""
    priority: Optional[str] = "media"
    status: Optional[str] = "a_fazer"
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    assigned_to_user_id: Optional[str] = None
    source_kind: Optional[str] = None
    source_id: Optional[str] = None
    assigned_role_name: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _map_input_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        key_map = {
            "startDate": "start_date",
            "dueDate": "due_date",
            "assignedToUserId": "assigned_to_user_id",
            "sourceKind": "source_kind",
            "sourceId": "source_id",
            "assignedRoleName": "assigned_role_name",
        }
        for src, dst in key_map.items():
            if src in data and dst not in data:
                data[dst] = data[src]
        return data

    @field_validator("assigned_to_user_id")
    @classmethod
    def _normalize_assigned_to_user_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise ValueError("required")
        return value

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: Optional[str]) -> str:
        return str(value or "").strip()

    @field_validator("source_kind", "source_id", "assigned_role_name")
    @classmethod
    def _validate_optional_refs(cls, value: Optional[str]) -> Optional[str]:
        value = str(value or "").strip()
        return value or None

    @field_validator("priority")
    @classmethod
    def _validate_priority(cls, value: Optional[str]) -> str:
        return _normalize_priority(value)

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: Optional[str]) -> str:
        return _normalize_status(value)


class TaskUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    assigned_to_user_id: Optional[str] = None
    clear_assigned_to_user_id: bool = False
    source_kind: Optional[str] = None
    source_id: Optional[str] = None
    assigned_role_name: Optional[str] = None
    clear_source_kind: bool = False
    clear_source_id: bool = False
    clear_assigned_role_name: bool = False

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _map_input_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        key_map = {
            "startDate": "start_date",
            "dueDate": "due_date",
            "assignedToUserId": "assigned_to_user_id",
            "clearAssignedToUserId": "clear_assigned_to_user_id",
            "sourceKind": "source_kind",
            "sourceId": "source_id",
            "assignedRoleName": "assigned_role_name",
            "clearSourceKind": "clear_source_kind",
            "clearSourceId": "clear_source_id",
            "clearAssignedRoleName": "clear_assigned_role_name",
        }
        for src, dst in key_map.items():
            if src in data and dst not in data:
                data[dst] = data[src]
        return data

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        if not value:
            raise ValueError("required")
        return value

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return str(value).strip()

    @field_validator("source_kind", "source_id", "assigned_role_name")
    @classmethod
    def _validate_optional_refs(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("priority")
    @classmethod
    def _validate_priority(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _normalize_priority(value)


class TaskStatusIn(BaseModel):
    status: Literal["a_fazer", "em_andamento", "em_revisao", "concluida", "cancelada"]

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class TaskCommentIn(BaseModel):
    body: str

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("body")
    @classmethod
    def _validate_body(cls, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise ValueError("required")
        return value


@router.get("/ui", response_class=HTMLResponse)
def get_ui() -> HTMLResponse:
    return HTMLResponse(_read_html("ui.html"))


@router.get("/schema")
def get_schema() -> Dict[str, Any]:
    return {
        "kind": KIND,
        "version": TASKS_VERSION,
        "statusValues": list(_STATUS_VALUES),
        "statusFlow": _STATUS_FLOW,
        "priorityValues": sorted(_PRIORITY_VALUES),
        "phase": "2B-polish",
        "views": ["list", "kanban", "calendar-week", "calendar-month", "insights-prep", "management-prep"],
        "futureViews": ["control-panel", "analytics-consolidated"],
        "notificationRules": _TASK_NOTIFICATION_RULES,
        "permissions": {
            "creatorCanEdit": True,
            "creatorCanDelete": True,
            "assigneeCanChangeStatus": True,
            "elevatedRoles": ["admin", "coordenador"],
        },
    }


@router.get("/config")
def get_config(user: Dict[str, Any] = Depends(require_password_changed)) -> Dict[str, Any]:
    return {
        "me": {
            "id": str(_user_id_from_session(user)),
            "name": user.get("nome") or user.get("name"),
            "roles": sorted(_norm_roles(user)),
            "elevated": _is_elevated(user),
        },
        "users": _load_users_for_picker(user),
        "statusValues": list(_STATUS_VALUES),
        "statusFlow": _STATUS_FLOW,
        "priorityValues": sorted(_PRIORITY_VALUES),
        "eventCatalog": _EVENT_CATALOG,
        "notificationRules": _TASK_NOTIFICATION_RULES,
    }


@router.get("/summary")
def get_summary(user: Dict[str, Any] = Depends(require_password_changed)) -> Dict[str, Any]:
    where_sql, params = _task_scope_where(user)
    user_id = _user_id_from_session(user)
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL) AS total_active,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.created_by_user_id = %s) AS created_by_me,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.assigned_to_user_id = %s) AS assigned_to_me,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NULL AND t.due_date < CURRENT_DATE AND t.status <> 'cancelada') AS overdue,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NULL AND t.due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days' AND t.status <> 'cancelada') AS due_next_7_days,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NOT NULL AND t.completed_at >= now() - INTERVAL '7 days') AS completed_last_7_days,
              COUNT(*) FILTER (WHERE t.deleted_at IS NOT NULL) AS deleted_total
            FROM tasks t
            WHERE {where_sql}
            """,
            [user_id, user_id, *params],
        )
        stats = cur.fetchone()

        cur.execute(
            f"""
            SELECT t.status, COUNT(*)::int AS total
            FROM tasks t
            WHERE {where_sql}
              AND t.deleted_at IS NULL
            GROUP BY t.status
            ORDER BY t.status
            """,
            params,
        )
        by_status = {r["status"]: int(r["total"]) for r in (cur.fetchall() or [])}

    return {
        "totals": {
            "active": int(stats["total_active"] or 0),
            "createdByMe": int(stats["created_by_me"] or 0),
            "assignedToMe": int(stats["assigned_to_me"] or 0),
            "overdue": int(stats["overdue"] or 0),
            "dueNext7Days": int(stats["due_next_7_days"] or 0),
            "completedLast7Days": int(stats["completed_last_7_days"] or 0),
            "deleted": int(stats["deleted_total"] or 0),
        },
        "byStatus": by_status,
    }


@router.get("/insights")
def get_insights(
    period_days: int = Query(default=30, ge=7, le=365, alias="periodDays"),
    limit: int = Query(default=10, ge=3, le=25),
    user: Dict[str, Any] = Depends(require_password_changed),
) -> Dict[str, Any]:
    where_sql, params = _task_scope_where(user)
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NULL) AS open_tasks,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NOT NULL AND t.completed_at >= now() - (%s || ' days')::interval) AS completed_in_period,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NULL AND t.due_date < CURRENT_DATE AND t.status <> 'cancelada') AS overdue_tasks,
              COALESCE(AVG(EXTRACT(EPOCH FROM (t.completed_at - t.created_at))) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NOT NULL AND t.completed_at >= now() - (%s || ' days')::interval), 0) AS avg_lead_seconds
            FROM tasks t
            WHERE {where_sql}
            """,
            [period_days, period_days, *params],
        )
        totals = cur.fetchone()

        cur.execute(
            f"""
            SELECT
              COALESCE(u.name, 'Sem responsável') AS label,
              COUNT(*)::int AS total
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_to_user_id
            WHERE {where_sql}
              AND t.deleted_at IS NULL
              AND t.completed_at IS NULL
            GROUP BY COALESCE(u.name, 'Sem responsável')
            ORDER BY total DESC, label ASC
            LIMIT %s
            """,
            [*params, limit],
        )
        open_by_assignee = [{"label": r["label"], "total": int(r["total"] or 0)} for r in (cur.fetchall() or [])]

        cur.execute(
            f"""
            SELECT
              COALESCE(u.name, 'Sem responsável') AS label,
              COUNT(*)::int AS total
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_to_user_id
            WHERE {where_sql}
              AND t.deleted_at IS NULL
              AND t.completed_at IS NULL
              AND t.due_date < CURRENT_DATE
              AND t.status <> 'cancelada'
            GROUP BY COALESCE(u.name, 'Sem responsável')
            ORDER BY total DESC, label ASC
            LIMIT %s
            """,
            [*params, limit],
        )
        overdue_by_assignee = [{"label": r["label"], "total": int(r["total"] or 0)} for r in (cur.fetchall() or [])]

        cur.execute(
            f"""
            SELECT
              COALESCE(u.name, 'Sem responsável') AS label,
              COUNT(*)::int AS total
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_to_user_id
            WHERE {where_sql}
              AND t.deleted_at IS NULL
              AND t.completed_at IS NOT NULL
              AND t.completed_at >= now() - (%s || ' days')::interval
            GROUP BY COALESCE(u.name, 'Sem responsável')
            ORDER BY total DESC, label ASC
            LIMIT %s
            """,
            [*params, period_days, limit],
        )
        completed_by_assignee = [{"label": r["label"], "total": int(r["total"] or 0)} for r in (cur.fetchall() or [])]

        cur.execute(
            f"""
            SELECT
              COALESCE(NULLIF(t.source_kind, ''), 'manual') AS label,
              COUNT(*)::int AS total
            FROM tasks t
            WHERE {where_sql}
              AND t.deleted_at IS NULL
            GROUP BY COALESCE(NULLIF(t.source_kind, ''), 'manual')
            ORDER BY total DESC, label ASC
            LIMIT %s
            """,
            [*params, limit],
        )
        by_source = [{"label": r["label"], "total": int(r["total"] or 0)} for r in (cur.fetchall() or [])]

    return {
        "periodDays": period_days,
        "totals": {
            "open": int(totals["open_tasks"] or 0),
            "completedInPeriod": int(totals["completed_in_period"] or 0),
            "overdue": int(totals["overdue_tasks"] or 0),
            "avgLeadHours": round(float(totals["avg_lead_seconds"] or 0) / 3600, 2),
        },
        "openByAssignee": open_by_assignee,
        "overdueByAssignee": overdue_by_assignee,
        "completedByAssignee": completed_by_assignee,
        "bySource": by_source,
    }


@router.get("/management-overview")
def get_management_overview(
    period_days: int = Query(default=30, ge=7, le=365, alias="periodDays"),
    limit: int = Query(default=12, ge=5, le=50),
    user: Dict[str, Any] = Depends(require_password_changed),
) -> Dict[str, Any]:
    _ensure_elevated(user)

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NULL) AS open_tasks,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.created_at >= now() - (%s || ' days')::interval) AS created_in_period,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NOT NULL AND t.completed_at >= now() - (%s || ' days')::interval) AS completed_in_period,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NULL AND t.due_date < CURRENT_DATE AND t.status <> 'cancelada') AS overdue_tasks,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NULL AND t.due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days' AND t.status <> 'cancelada') AS due_soon_tasks,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NULL AND t.status = 'em_revisao') AS in_review_tasks,
              COALESCE(AVG(EXTRACT(EPOCH FROM (t.completed_at - t.created_at))) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NOT NULL AND t.completed_at >= now() - (%s || ' days')::interval), 0) AS avg_lead_seconds
            FROM tasks t
            """,
            [period_days, period_days, period_days],
        )
        totals = cur.fetchone()

        cur.execute(
            """
            SELECT
              COALESCE(u.name, 'Sem responsável') AS assignee_name,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NULL) AS open_tasks,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NULL AND t.due_date < CURRENT_DATE AND t.status <> 'cancelada') AS overdue_tasks,
              COUNT(*) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NOT NULL AND t.completed_at >= now() - (%s || ' days')::interval) AS completed_in_period,
              COALESCE(AVG(EXTRACT(EPOCH FROM (t.completed_at - t.created_at))) FILTER (WHERE t.deleted_at IS NULL AND t.completed_at IS NOT NULL AND t.completed_at >= now() - (%s || ' days')::interval), 0) AS avg_lead_seconds
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_to_user_id
            GROUP BY COALESCE(u.name, 'Sem responsável')
            HAVING COUNT(*) FILTER (WHERE t.deleted_at IS NULL) > 0
            ORDER BY open_tasks DESC, overdue_tasks DESC, assignee_name ASC
            LIMIT %s
            """,
            [period_days, period_days, limit],
        )
        by_user_rows = cur.fetchall() or []

        cur.execute(
            """
            SELECT t.status, COUNT(*)::int AS total
            FROM tasks t
            WHERE t.deleted_at IS NULL
            GROUP BY t.status
            ORDER BY total DESC, t.status ASC
            """
        )
        status_rows = cur.fetchall() or []

        cur.execute(
            """
            SELECT COALESCE(t.priority, 'media') AS priority, COUNT(*)::int AS total
            FROM tasks t
            WHERE t.deleted_at IS NULL
            GROUP BY COALESCE(t.priority, 'media')
            ORDER BY total DESC, priority ASC
            """
        )
        priority_rows = cur.fetchall() or []

        cur.execute(
            """
            SELECT COALESCE(t.assigned_role_name, 'sem_papel') AS role_name, COUNT(*)::int AS total
            FROM tasks t
            WHERE t.deleted_at IS NULL
            GROUP BY COALESCE(t.assigned_role_name, 'sem_papel')
            ORDER BY total DESC, role_name ASC
            LIMIT %s
            """,
            [min(limit, 20)],
        )
        by_role_rows = cur.fetchall() or []

        cur.execute(
            """
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
              FROM tasks
              WHERE deleted_at IS NULL
                AND created_at >= now() - (%s || ' days')::interval
              GROUP BY created_at::date
            ) created ON created.ref_date = d.ref_date
            LEFT JOIN (
              SELECT completed_at::date AS ref_date, COUNT(*)::int AS total
              FROM tasks
              WHERE deleted_at IS NULL
                AND completed_at IS NOT NULL
                AND completed_at >= now() - (%s || ' days')::interval
              GROUP BY completed_at::date
            ) completed ON completed.ref_date = d.ref_date
            ORDER BY d.ref_date ASC
            """,
            [period_days, period_days, period_days],
        )
        daily_rows = cur.fetchall() or []

        cur.execute(
            """
            SELECT
              t.id,
              t.title,
              t.completed_at,
              COALESCE(u.name, 'Sem responsável') AS assignee_name,
              EXTRACT(EPOCH FROM (t.completed_at - t.created_at)) AS lead_seconds
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_to_user_id
            WHERE t.deleted_at IS NULL
              AND t.completed_at IS NOT NULL
              AND t.completed_at >= now() - (%s || ' days')::interval
            ORDER BY t.completed_at DESC
            LIMIT %s
            """,
            [period_days, min(limit, 15)],
        )
        recent_completed_rows = cur.fetchall() or []

    created_in_period = int(totals["created_in_period"] or 0)
    completed_in_period = int(totals["completed_in_period"] or 0)
    completion_rate = round((completed_in_period / created_in_period) * 100, 1) if created_in_period else 0.0

    return {
        "periodDays": period_days,
        "totals": {
            "open": int(totals["open_tasks"] or 0),
            "createdInPeriod": created_in_period,
            "completedInPeriod": completed_in_period,
            "overdue": int(totals["overdue_tasks"] or 0),
            "dueSoon": int(totals["due_soon_tasks"] or 0),
            "inReview": int(totals["in_review_tasks"] or 0),
            "avgLeadHours": round(float(totals["avg_lead_seconds"] or 0) / 3600, 2),
            "completionRatePercent": completion_rate,
        },
        "byUser": [
            {
                "label": r["assignee_name"],
                "open": int(r["open_tasks"] or 0),
                "overdue": int(r["overdue_tasks"] or 0),
                "completedInPeriod": int(r["completed_in_period"] or 0),
                "avgLeadHours": round(float(r["avg_lead_seconds"] or 0) / 3600, 2),
            }
            for r in by_user_rows
        ],
        "byStatus": [
            {"status": r["status"], "label": _status_label(r["status"]), "total": int(r["total"] or 0)}
            for r in status_rows
        ],
        "byPriority": [
            {"priority": r["priority"], "label": str(r["priority"]).capitalize(), "total": int(r["total"] or 0)}
            for r in priority_rows
        ],
        "byAssignedRole": [
            {"roleName": r["role_name"], "label": r["role_name"], "total": int(r["total"] or 0)}
            for r in by_role_rows
        ],
        "dailySeries": [
            {
                "date": _iso_date(r["ref_date"]),
                "created": int(r["created_total"] or 0),
                "completed": int(r["completed_total"] or 0),
            }
            for r in daily_rows
        ],
        "recentCompleted": [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "completedAt": _iso_dt(r["completed_at"]),
                "assigneeName": r["assignee_name"],
                "leadHours": round(float(r["lead_seconds"] or 0) / 3600, 2),
            }
            for r in recent_completed_rows
        ],
    }


@router.get("/activity")
def get_activity(
    limit: int = Query(default=20, ge=1, le=100),
    user: Dict[str, Any] = Depends(require_password_changed),
) -> Dict[str, Any]:
    where_sql, params = _task_event_scope_where(user)
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              e.id,
              e.task_id,
              t.title AS task_title,
              e.event_type,
              e.old_value,
              e.new_value,
              e.metadata,
              e.created_at,
              e.actor_user_id,
              u.name AS actor_name
            FROM task_events e
            JOIN tasks t ON t.id = e.task_id
            LEFT JOIN users u ON u.id = e.actor_user_id
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
                "eventType": r["event_type"],
                "eventLabel": _event_descriptor(r["event_type"]).get("label"),
                "eventCategory": _event_descriptor(r["event_type"]).get("category"),
                "eventSeverity": _event_descriptor(r["event_type"]).get("severity"),
                "oldValue": r.get("old_value"),
                "newValue": r.get("new_value"),
                "metadata": r.get("metadata"),
                "createdAt": _iso_dt(r["created_at"]),
                "actorUserId": str(r["actor_user_id"]) if r.get("actor_user_id") else None,
                "actorName": r.get("actor_name"),
            }
            for r in rows
        ]
    }


@router.get("/tasks")
def list_tasks(
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
    user: Dict[str, Any] = Depends(require_password_changed),
) -> Dict[str, Any]:
    where_parts = []
    params: list[Any] = []

    scope_sql, scope_params = _task_scope_where(user)
    where_parts.append(scope_sql)
    params.extend(scope_params)

    if not include_deleted:
        where_parts.append("t.deleted_at IS NULL")

    if q and str(q).strip():
        where_parts.append("(t.title ILIKE %s OR COALESCE(t.description,'') ILIKE %s)")
        like = f"%{str(q).strip()}%"
        params.extend([like, like])

    if status and str(status).strip():
        where_parts.append("t.status = %s")
        params.append(_normalize_status(status))

    if priority and str(priority).strip():
        where_parts.append("t.priority = %s")
        params.append(_normalize_priority(priority))

    if assigned_to_user_id and str(assigned_to_user_id).strip():
        where_parts.append("t.assigned_to_user_id = %s")
        params.append(_parse_uuid(assigned_to_user_id, "assignedToUserId"))

    if source_kind and str(source_kind).strip():
        where_parts.append("COALESCE(t.source_kind, '') = %s")
        params.append(str(source_kind).strip())

    if source_id and str(source_id).strip():
        where_parts.append("COALESCE(t.source_id, '') = %s")
        params.append(str(source_id).strip())

    if overdue_only:
        where_parts.append(
            "t.due_date < CURRENT_DATE AND t.completed_at IS NULL AND t.deleted_at IS NULL AND t.status <> 'cancelada'"
        )

    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail={"dateRange": "dateFrom must be less than or equal to dateTo"})

    effective_start_expr = "COALESCE(t.start_date, t.due_date, DATE(t.created_at))"
    effective_end_expr = "COALESCE(t.due_date, t.start_date, DATE(t.created_at))"
    if date_from:
        where_parts.append(f"{effective_end_expr} >= %s")
        params.append(date_from)
    if date_to:
        where_parts.append(f"{effective_start_expr} <= %s")
        params.append(date_to)

    uid = _user_id_from_session(user)
    if mine:
        where_parts.append("(t.created_by_user_id = %s OR t.assigned_to_user_id = %s)")
        params.extend([uid, uid])
    if created_by_me:
        where_parts.append("t.created_by_user_id = %s")
        params.append(uid)
    if assigned_to_me:
        where_parts.append("t.assigned_to_user_id = %s")
        params.append(uid)

    where_sql = " AND ".join(where_parts) if where_parts else "TRUE"

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
                WHEN 'em_revisao' THEN 2
                WHEN 'a_fazer' THEN 3
                WHEN 'backlog' THEN 4
                WHEN 'concluida' THEN 5
                WHEN 'cancelada' THEN 6
                ELSE 99
              END ASC,
              t.due_date ASC NULLS LAST,
              t.updated_at DESC
            """,
            params,
        )
        rows = cur.fetchall() or []

    items = []
    for row in rows:
        item = _task_to_out(row, user)
        item["commentCount"] = int(row.get("comment_count") or 0)
        items.append(item)

    return {"items": items, "total": len(items)}


@router.post("/tasks", status_code=201)
def create_task(payload: TaskCreateIn, user: Dict[str, Any] = Depends(require_password_changed)) -> Dict[str, Any]:
    actor_id = _user_id_from_session(user)

    if "assigned_to_user_id" in payload.model_fields_set:
        assigned_to_uuid = _parse_uuid(payload.assigned_to_user_id, "assignedToUserId") if payload.assigned_to_user_id else None
    else:
        assigned_to_uuid = actor_id

    _validate_dates(payload.start_date, payload.due_date)

    completed_at = datetime.now(timezone.utc) if payload.status == "concluida" else None

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tasks (
              title, description, status, priority, start_date, due_date, completed_at,
              created_by_user_id, assigned_to_user_id, last_updated_by_user_id,
              source_kind, source_id, assigned_role_name
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                payload.title.strip(),
                payload.description or "",
                payload.status,
                payload.priority,
                payload.start_date,
                payload.due_date,
                completed_at,
                actor_id,
                assigned_to_uuid,
                actor_id,
                payload.source_kind,
                payload.source_id,
                payload.assigned_role_name,
            ),
        )
        task_id = cur.fetchone()["id"]

    task = _load_task_row(task_id)
    if not task:
        raise HTTPException(status_code=500, detail="task was created but could not be loaded")

    _record_task_event(
        task_id=task_id,
        actor_user_id=actor_id,
        event_type="task_created",
        new_value=_task_snapshot(task),
    )
    _dispatch_task_notification(event_type="task_created", task=task, actor=user)

    add_audit(
        KIND,
        "create",
        user,
        {
            "task_id": str(task_id),
            "status": task["status"],
            "assigned_to_user_id": str(assigned_to_uuid) if assigned_to_uuid else None,
            "source_kind": payload.source_kind,
            "source_id": payload.source_id,
            "assigned_role_name": payload.assigned_role_name,
        },
    )
    logger.info("[TASKS] Tarefa criada | task=%s | actor=%s", task_id, actor_id)

    return {"item": _task_to_out(task, user)}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, user: Dict[str, Any] = Depends(require_password_changed)) -> Dict[str, Any]:
    task_uuid = _parse_uuid(task_id, "task id")
    task = _load_task_row(task_uuid)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    _ensure_visible(task, user)

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.body, c.created_at, c.actor_user_id, u.name AS actor_name
            FROM task_comments c
            LEFT JOIN users u ON u.id = c.actor_user_id
            WHERE c.task_id = %s
            ORDER BY c.created_at ASC
            """,
            (task_uuid,),
        )
        comments = cur.fetchall() or []

    return {
        "item": _task_to_out(task, user),
        "comments": [
            {
                "id": int(c["id"]),
                "body": c["body"],
                "createdAt": _iso_dt(c["created_at"]),
                "actorUserId": str(c["actor_user_id"]) if c.get("actor_user_id") else None,
                "actorName": c.get("actor_name"),
            }
            for c in comments
        ],
    }


@router.put("/tasks/{task_id}")
def update_task(task_id: str, payload: TaskUpdateIn, user: Dict[str, Any] = Depends(require_password_changed)) -> Dict[str, Any]:
    task_uuid = _parse_uuid(task_id, "task id")
    actor_id = _user_id_from_session(user)

    task = _load_task_row(task_uuid)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")

    _ensure_visible(task, user)
    _ensure_not_deleted(task)
    _ensure_can_edit(task, user)

    new_title = task["title"] if payload.title is None else payload.title
    new_description = task["description"] if payload.description is None else payload.description
    new_priority = task["priority"] if payload.priority is None else payload.priority
    new_start_date = task["start_date"] if payload.start_date is None else payload.start_date
    new_due_date = task["due_date"] if payload.due_date is None else payload.due_date

    if payload.clear_assigned_to_user_id:
        new_assigned_to = None
    elif payload.assigned_to_user_id is None:
        new_assigned_to = task["assigned_to_user_id"]
    else:
        new_assigned_to = _parse_uuid(payload.assigned_to_user_id, "assignedToUserId")

    if payload.clear_source_kind:
        new_source_kind = None
    elif payload.source_kind is None:
        new_source_kind = task.get("source_kind")
    else:
        new_source_kind = payload.source_kind

    if payload.clear_source_id:
        new_source_id = None
    elif payload.source_id is None:
        new_source_id = task.get("source_id")
    else:
        new_source_id = payload.source_id

    if payload.clear_assigned_role_name:
        new_assigned_role_name = None
    elif payload.assigned_role_name is None:
        new_assigned_role_name = task.get("assigned_role_name")
    else:
        new_assigned_role_name = payload.assigned_role_name

    _validate_dates(new_start_date, new_due_date)

    before = _task_snapshot(task)

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tasks
            SET
              title = %s,
              description = %s,
              priority = %s,
              start_date = %s,
              due_date = %s,
              assigned_to_user_id = %s,
              source_kind = %s,
              source_id = %s,
              assigned_role_name = %s,
              last_updated_by_user_id = %s
            WHERE id = %s
            """,
            (
                new_title,
                new_description,
                new_priority,
                new_start_date,
                new_due_date,
                new_assigned_to,
                new_source_kind,
                new_source_id,
                new_assigned_role_name,
                actor_id,
                task_uuid,
            ),
        )

    updated = _load_task_row(task_uuid)
    if not updated:
        raise HTTPException(status_code=500, detail="task was updated but could not be loaded")

    after = _task_snapshot(updated)
    _record_task_event(
        task_id=task_uuid,
        actor_user_id=actor_id,
        event_type="task_updated",
        old_value=before,
        new_value=after,
    )

    if before.get("dueDate") != after.get("dueDate"):
        _record_task_event(
            task_id=task_uuid,
            actor_user_id=actor_id,
            event_type="task_due_date_changed",
            old_value={"dueDate": before.get("dueDate")},
            new_value={"dueDate": after.get("dueDate")},
        )

    if before.get("assignedToUserId") != after.get("assignedToUserId"):
        assignment_event = "task_reassigned" if before.get("assignedToUserId") else "task_assigned"
        _record_task_event(
            task_id=task_uuid,
            actor_user_id=actor_id,
            event_type=assignment_event,
            old_value={"assignedToUserId": before.get("assignedToUserId")},
            new_value={"assignedToUserId": after.get("assignedToUserId")},
        )
        _dispatch_task_notification(event_type=assignment_event, task=updated, actor=user)

    add_audit(KIND, "update", user, {"task_id": str(task_uuid)})
    logger.info("[TASKS] Tarefa atualizada | task=%s | actor=%s", task_uuid, actor_id)

    return {"item": _task_to_out(updated, user)}


@router.patch("/tasks/{task_id}/status")
def update_task_status(task_id: str, payload: TaskStatusIn, user: Dict[str, Any] = Depends(require_password_changed)) -> Dict[str, Any]:
    task_uuid = _parse_uuid(task_id, "task id")
    actor_id = _user_id_from_session(user)

    task = _load_task_row(task_uuid)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")

    _ensure_visible(task, user)
    _ensure_not_deleted(task)
    _ensure_can_change_status(task, user)

    old_status = task["status"]
    new_status = _normalize_status(payload.status)
    if old_status == new_status:
        return {"item": _task_to_out(task, user)}

    completed_at = datetime.now(timezone.utc) if new_status == "concluida" else None

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tasks
            SET status = %s, completed_at = %s, last_updated_by_user_id = %s
            WHERE id = %s
            """,
            (new_status, completed_at, actor_id, task_uuid),
        )

    updated = _load_task_row(task_uuid)
    if not updated:
        raise HTTPException(status_code=500, detail="task status was updated but could not be loaded")

    _record_task_event(
        task_id=task_uuid,
        actor_user_id=actor_id,
        event_type="task_status_changed",
        old_value={"status": old_status},
        new_value={"status": new_status},
    )

    if new_status == "concluida":
        _record_task_event(
            task_id=task_uuid,
            actor_user_id=actor_id,
            event_type="task_completed",
            new_value={"completedAt": _iso_dt(updated.get("completed_at"))},
        )
        _dispatch_task_notification(event_type="task_completed", task=updated, actor=user)
    elif new_status == "cancelada":
        _record_task_event(
            task_id=task_uuid,
            actor_user_id=actor_id,
            event_type="task_cancelled",
            new_value={"status": "cancelada"},
        )
        _dispatch_task_notification(event_type="task_cancelled", task=updated, actor=user)
    elif new_status == "em_revisao":
        _record_task_event(
            task_id=task_uuid,
            actor_user_id=actor_id,
            event_type="task_in_review",
            new_value={"status": "em_revisao"},
        )
        _dispatch_task_notification(event_type="task_in_review", task=updated, actor=user)

    add_audit(KIND, "status", user, {"task_id": str(task_uuid), "old_status": old_status, "new_status": new_status})
    logger.info("[TASKS] Status alterado | task=%s | from=%s | to=%s | actor=%s", task_uuid, old_status, new_status, actor_id)

    return {"item": _task_to_out(updated, user)}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, user: Dict[str, Any] = Depends(require_password_changed)) -> Dict[str, Any]:
    task_uuid = _parse_uuid(task_id, "task id")
    actor_id = _user_id_from_session(user)

    task = _load_task_row(task_uuid)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")

    _ensure_visible(task, user)
    _ensure_not_deleted(task)
    _ensure_can_delete(task, user)

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tasks
            SET deleted_at = now(), deleted_by_user_id = %s, last_updated_by_user_id = %s
            WHERE id = %s
            """,
            (actor_id, actor_id, task_uuid),
        )

    updated = _load_task_row(task_uuid)
    if not updated:
        raise HTTPException(status_code=500, detail="task was deleted but could not be loaded")

    _record_task_event(
        task_id=task_uuid,
        actor_user_id=actor_id,
        event_type="task_deleted",
        old_value=_task_snapshot(task),
        new_value={"deletedAt": _iso_dt(updated.get("deleted_at"))},
    )

    add_audit(KIND, "delete", user, {"task_id": str(task_uuid)})
    logger.info("[TASKS] Tarefa excluída logicamente | task=%s | actor=%s", task_uuid, actor_id)

    return {"ok": True, "item": _task_to_out(updated, user)}


@router.post("/tasks/{task_id}/restore")
def restore_task(task_id: str, user: Dict[str, Any] = Depends(require_password_changed)) -> Dict[str, Any]:
    task_uuid = _parse_uuid(task_id, "task id")
    actor_id = _user_id_from_session(user)

    task = _load_task_row(task_uuid)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")

    _ensure_visible(task, user)
    if task.get("deleted_at") is None:
        raise HTTPException(status_code=409, detail="task is not deleted")
    _ensure_can_restore(task, user)

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tasks
            SET deleted_at = NULL, deleted_by_user_id = NULL, last_updated_by_user_id = %s
            WHERE id = %s
            """,
            (actor_id, task_uuid),
        )

    updated = _load_task_row(task_uuid)
    if not updated:
        raise HTTPException(status_code=500, detail="task was restored but could not be loaded")

    _record_task_event(
        task_id=task_uuid,
        actor_user_id=actor_id,
        event_type="task_restored",
        old_value={"deletedAt": _iso_dt(task.get("deleted_at"))},
        new_value=_task_snapshot(updated),
    )
    _dispatch_task_notification(event_type="task_restored", task=updated, actor=user)

    add_audit(KIND, "restore", user, {"task_id": str(task_uuid)})
    logger.info("[TASKS] Tarefa restaurada | task=%s | actor=%s", task_uuid, actor_id)

    return {"ok": True, "item": _task_to_out(updated, user)}


@router.post("/tasks/{task_id}/comments", status_code=201)
def add_comment(task_id: str, payload: TaskCommentIn, user: Dict[str, Any] = Depends(require_password_changed)) -> Dict[str, Any]:
    task_uuid = _parse_uuid(task_id, "task id")
    actor_id = _user_id_from_session(user)

    task = _load_task_row(task_uuid)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")

    _ensure_visible(task, user)
    _ensure_not_deleted(task)

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO task_comments (task_id, actor_user_id, body)
            VALUES (%s, %s, %s)
            RETURNING id, body, created_at, actor_user_id
            """,
            (task_uuid, actor_id, payload.body),
        )
        comment = cur.fetchone()

        cur.execute(
            """
            UPDATE tasks
            SET last_updated_by_user_id = %s
            WHERE id = %s
            """,
            (actor_id, task_uuid),
        )

    _record_task_event(
        task_id=task_uuid,
        actor_user_id=actor_id,
        event_type="task_comment_added",
        new_value={"commentId": int(comment["id"]), "body": comment["body"]},
    )

    updated = _load_task_row(task_uuid)
    if updated:
        _dispatch_task_notification(event_type="task_comment_added", task=updated, actor=user)

    add_audit(KIND, "comment", user, {"task_id": str(task_uuid), "comment_id": int(comment["id"])})
    logger.info("[TASKS] Comentário adicionado | task=%s | actor=%s", task_uuid, actor_id)

    actor_name = user.get("nome") or user.get("name")
    return {
        "item": {
            "id": int(comment["id"]),
            "body": comment["body"],
            "createdAt": _iso_dt(comment["created_at"]),
            "actorUserId": str(comment["actor_user_id"]) if comment.get("actor_user_id") else None,
            "actorName": actor_name,
        }
    }


@router.get("/tasks/{task_id}/history")
def get_task_history(task_id: str, user: Dict[str, Any] = Depends(require_password_changed)) -> Dict[str, Any]:
    task_uuid = _parse_uuid(task_id, "task id")
    task = _load_task_row(task_uuid)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")

    _ensure_visible(task, user)

    with _pg() as conn, conn.cursor() as cur:
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
                "eventLabel": _event_descriptor(r["event_type"]).get("label"),
                "eventCategory": _event_descriptor(r["event_type"]).get("category"),
                "eventSeverity": _event_descriptor(r["event_type"]).get("severity"),
                "summary": _event_summary(r["event_type"], r.get("old_value"), r.get("new_value"), r.get("metadata")),
                "oldValue": r.get("old_value"),
                "newValue": r.get("new_value"),
                "metadata": r.get("metadata"),
                "createdAt": _iso_dt(r["created_at"]),
                "actorUserId": str(r["actor_user_id"]) if r.get("actor_user_id") else None,
                "actorName": r.get("actor_name"),
            }
            for r in rows
        ]
    }
