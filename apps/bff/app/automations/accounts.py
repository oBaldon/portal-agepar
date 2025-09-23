# apps/bff/app/automations/accounts.py
from __future__ import annotations

import logging
import pathlib
import re
from typing import Any, Dict, List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from argon2 import PasswordHasher

from app.db import insert_submission, get_submission, list_submissions_admin, add_audit, _pg  # type: ignore
from app.auth.rbac import require_roles_any

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Config & RBAC
# -----------------------------------------------------------------------------
REQUIRED_ROLES = ("admin",)  # somente administradores
BLOCKED_ROLES = {"is_superuser"}  # papel "virtual" controlado por coluna dedicada

# Diretório com os HTMLs desta automação
TPL_DIR = pathlib.Path(__file__).resolve().parent / "templates" / "accounts"

router = APIRouter(
    prefix="/api/automations/accounts",
    tags=["automations:accounts"],
    dependencies=[Depends(require_roles_any(*REQUIRED_ROLES))],
)

hasher = PasswordHasher()

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
CPF_RE = re.compile(r"\D+")
ROLE_OK_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{1,99}$")  # nomes simples e previsíveis


def norm_cpf(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = CPF_RE.sub("", v or "")
    if v == "":
        return None
    if len(v) != 11 or not v.isdigit():
        raise HTTPException(status_code=422, detail="CPF deve conter 11 dígitos numéricos.")
    return v


def safe_digits(s: str) -> str:
    return CPF_RE.sub("", s or "")


def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def err_json(
    status: int,
    *,
    code: str,
    message: str,
    details: Any = None,
    hint: Optional[str] = None,
    received: Any = None,
):
    content: Dict[str, Any] = {"error": code, "message": message}
    if details is not None:
        content["details"] = details
    if hint is not None:
        content["hint"] = hint
    if received is not None:
        content["received"] = received
    return JSONResponse(status_code=status, content=content)


def _read_html(name: str) -> str:
    """Carrega um arquivo HTML de TPL_DIR."""
    path = TPL_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def is_last_admin(cur, user_id: str) -> bool:
    """
    True se o sistema ficaria sem NENHUM admin ao remover o 'admin' deste usuário
    ou se tentar excluir o último admin.
    """
    cur.execute(
        """
        SELECT COUNT(*) AS admins
        FROM (
          SELECT DISTINCT u.id
          FROM users u
          JOIN user_roles ur ON ur.user_id = u.id
          JOIN roles r ON r.id = ur.role_id
          WHERE r.name = 'admin'
        ) q
        """
    )
    total_admins = (cur.fetchone() or {}).get("admins", 0) or 0
    if total_admins <= 1:
        cur.execute(
            """
            SELECT 1
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = %s AND r.name = 'admin'
            LIMIT 1
            """,
            (user_id,),
        )
        return bool(cur.fetchone())
    return False


def normalize_roles(input_roles: List[str]) -> List[str]:
    """
    - remove vazios, espaços
    - força lower()
    - filtra nomes inválidos e bloqueados (ex.: 'is_superuser')
    - remove duplicados
    """
    out: List[str] = []
    for r in input_roles or []:
        if not isinstance(r, str):
            continue
        r2 = r.strip().lower()
        if not r2:
            continue
        if r2 in BLOCKED_ROLES:
            continue
        if not ROLE_OK_RE.match(r2):
            continue
        out.append(r2)
    return sorted(set(out))


# -----------------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------------
class UserOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    id: str
    cpf: Optional[str] = None
    email: Optional[EmailStr] = None
    name: str
    status: Optional[str] = None
    is_superuser: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    roles: List[str] = []


class CreateUserIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    name: str = Field(min_length=2, max_length=200)
    email: Optional[EmailStr] = None
    cpf: Optional[str] = None
    password: str = Field(min_length=8, max_length=128)
    roles: List[str] = []

    def normalize(self):
        self.cpf = norm_cpf(self.cpf)
        if not self.email and not self.cpf:
            raise HTTPException(status_code=422, detail="Informe e-mail ou CPF.")


class UpdateUserIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    email: Optional[EmailStr] = None
    cpf: Optional[str] = None
    status: Optional[Literal["active", "blocked", "pending"]] = None

    def normalize(self):
        self.cpf = norm_cpf(self.cpf) if self.cpf is not None else None


class SetPasswordIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    password: str = Field(min_length=8, max_length=128)


class RoleIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
@router.get("/ui")
def ui() -> HTMLResponse:
    html = _read_html("ui.html")
    return HTMLResponse(content=html)


# -----------------------------------------------------------------------------
# JSON endpoints
# -----------------------------------------------------------------------------
@router.get("/schema")
def schema() -> Dict[str, Any]:
    return {
        "name": "accounts",
        "version": "1.0.0",
        "actions": [
            "create_user",
            "update_user",
            "delete_user",
            "set_password",
            "set_roles",
            "create_role",
            "delete_role",
        ],
        "notes": "Administração de contas e papéis (roles). Somente admins.",
    }


# -- users: list & get
@router.get("/users")
def list_users(
    q: Optional[str] = Query(default=None),
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    limit = clamp(limit, 1, 200)
    offset = max(0, offset)

    wheres = ["1=1"]
    params: List[Any] = []
    if q:
        only = safe_digits(q)
        if len(only) == 11:
            wheres.append("cpf = %s")
            params.append(only)
        else:
            wheres.append("(name ILIKE %s OR email ILIKE %s)")
            like = f"%{q}%"
            params.extend([like, like])

    where_sql = " AND ".join(wheres)
    sql = f"""
      SELECT u.id::text, u.cpf, u.email, u.name, u.status,
             COALESCE(u.is_superuser, false) as is_superuser,
             u.created_at, u.updated_at,
             COALESCE(array_agg(r.name ORDER BY r.name)
                      FILTER (WHERE r.name IS NOT NULL), '{{}}') AS roles
      FROM users u
      LEFT JOIN user_roles ur ON ur.user_id = u.id
      LEFT JOIN roles r ON r.id = ur.role_id
      WHERE {where_sql}
      GROUP BY u.id
      ORDER BY u.created_at DESC
      LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() or []
        items = []
        for row in rows:
            d = dict(row)
            d["roles"] = list(d.get("roles") or [])
            items.append(d)
        return {"items": items, "count": len(items)}


@router.get("/users/{user_id}")
def get_user(user_id: str) -> UserOut:
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.id::text, u.cpf, u.email, u.name, u.status,
                   COALESCE(u.is_superuser,false) AS is_superuser,
                   u.created_at, u.updated_at,
                   COALESCE(array_agg(r.name ORDER BY r.name)
                            FILTER (WHERE r.name IS NOT NULL), '{{}}') AS roles
            FROM users u
            LEFT JOIN user_roles ur ON ur.user_id = u.id
            LEFT JOIN roles r ON r.id = ur.role_id
            WHERE u.id = %s
            GROUP BY u.id
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        d = dict(row)
        d["roles"] = list(d.get("roles") or [])
        return d


@router.post("/users")
def create_user(payload: CreateUserIn, request: Request):
    try:
        payload.normalize()
    except HTTPException as e:
        raise e
    except Exception as e:
        return err_json(422, code="validation_error", message=str(e))

    with _pg() as conn, conn.cursor() as cur:
        # unicidade por email/cpf
        if payload.email:
            cur.execute("SELECT 1 FROM users WHERE email = %s", (str(payload.email),))
            if cur.fetchone():
                return err_json(409, code="conflict", message="Email já cadastrado.")
        if payload.cpf:
            cur.execute("SELECT 1 FROM users WHERE cpf = %s", (payload.cpf,))
            if cur.fetchone():
                return err_json(409, code="conflict", message="CPF já cadastrado.")

        pwd_hash = hasher.hash(payload.password)
        cur.execute(
            """INSERT INTO users (cpf, email, name, password_hash, status, is_superuser)
               VALUES (%s, %s, %s, %s, 'active', false)
               RETURNING id::text""",
            (payload.cpf, str(payload.email) if payload.email else None, payload.name, pwd_hash),
        )
        row = cur.fetchone() or {}
        user_id = row.get("id")  # dict_row -> acessar pela chave
        if not user_id:
            raise HTTPException(status_code=500, detail="Falha ao criar usuário (sem id).")

        # garantir roles existentes e aplicar
        roles = normalize_roles(payload.roles or [])
        if roles:
            # cria roles inexistentes (tolerante a corrida)
            cur.execute("SELECT name FROM roles WHERE name = ANY(%s)", (roles,))
            existing_names = {r["name"] for r in (cur.fetchall() or [])}
            to_create = [r for r in roles if r not in existing_names]
            for r in to_create:
                cur.execute(
                    "INSERT INTO roles (name, description) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
                    (r, None),
                )
            # vincula
            cur.execute("SELECT id, name FROM roles WHERE name = ANY(%s)", (roles,))
            role_map = {row["name"]: row["id"] for row in (cur.fetchall() or [])}
            for r in roles:
                rid = role_map.get(r)
                if rid:
                    cur.execute(
                        "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (user_id, rid),
                    )

        # submissão/audit
        actor = request.session.get("user") or {}
        insert_submission(
            {
                "kind": "accounts",
                "version": "1.0.0",
                "actor_cpf": actor.get("cpf"),
                "actor_nome": actor.get("name") or actor.get("nome"),
                "actor_email": actor.get("email"),
                "payload": {
                    "action": "create_user",
                    "user_id": user_id,
                    "name": payload.name,
                    "email": str(payload.email) if payload.email else None,
                    "cpf": payload.cpf,
                    "roles": roles,
                },
                "status": "done",
                "result": {"user_id": user_id},
                "error": None,
            }
        )
        add_audit("accounts", "create_user", actor, {"user_id": user_id, "roles": roles})
        return {"ok": True, "user_id": user_id}


@router.put("/users/{user_id}")
def update_user(user_id: str, payload: UpdateUserIn, request: Request):
    try:
        payload.normalize()
    except HTTPException as e:
        raise e

    fields = []
    params: List[Any] = []
    if payload.name is not None:
        fields.append("name = %s"); params.append(payload.name)
    if payload.email is not None:
        fields.append("email = %s"); params.append(str(payload.email))
    if payload.cpf is not None:
        fields.append("cpf = %s"); params.append(payload.cpf)
    if payload.status is not None:
        fields.append("status = %s"); params.append(payload.status)
    if not fields:
        return {"ok": True, "updated": 0}

    with _pg() as conn, conn.cursor() as cur:
        # checagens de conflito
        if payload.email is not None:
            cur.execute("SELECT 1 FROM users WHERE email = %s AND id <> %s", (str(payload.email), user_id))
            if cur.fetchone():
                return err_json(409, code="conflict", message="Email já cadastrado em outro usuário.")
        if payload.cpf is not None:
            cur.execute("SELECT 1 FROM users WHERE cpf = %s AND id <> %s", (payload.cpf, user_id))
            if cur.fetchone():
                return err_json(409, code="conflict", message="CPF já cadastrado em outro usuário.")

        sql = f"UPDATE users SET {', '.join(fields)} WHERE id = %s"
        params.append(user_id)
        cur.execute(sql, params)

        actor = request.session.get("user") or {}
        insert_submission(
            {
                "kind": "accounts",
                "version": "1.0.0",
                "actor_cpf": actor.get("cpf"),
                "actor_nome": actor.get("name") or actor.get("nome"),
                "actor_email": actor.get("email"),
                "payload": {
                    "action": "update_user",
                    "user_id": user_id,
                    "fields": [f.split("=")[0].strip() for f in fields],
                },
                "status": "done",
                "result": {"updated": True},
                "error": None,
            }
        )
        add_audit("accounts", "update_user", actor, {"user_id": user_id, "fields": [f.split("=")[0].strip() for f in fields]})
        return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, request: Request):
    """
    Exclusão segura de usuário:
      - Impede autoexclusão.
      - Impede excluir o último administrador.
      - Remove/ajusta dependências (login_attempts, audit_events, user_roles) antes de excluir em users
        para evitar violação de chave estrangeira e preservar histórico.
    """
    actor = request.session.get("user") or {}
    if str(actor.get("id") or actor.get("user_id") or "") == user_id:
        raise HTTPException(status_code=400, detail="Você não pode excluir sua própria conta.")

    with _pg() as conn, conn.cursor() as cur:
        # proteger “último admin”
        if is_last_admin(cur, user_id):
            raise HTTPException(status_code=400, detail="Não é possível excluir o último administrador.")

        # limpar dependências conhecidas (ordem importante)
        # 1) tentativas de login vinculadas
        try:
            cur.execute("DELETE FROM login_attempts WHERE user_id = %s", (user_id,))
        except Exception:
            # mantém tolerância: se a tabela não existir em alguns ambientes
            logger.exception("Falha ao remover login_attempts (não bloqueante)")

        # 2) eventos de auditoria: preservar histórico (SET NULL)
        try:
            cur.execute("UPDATE audit_events SET actor_user_id = NULL WHERE actor_user_id = %s", (user_id,))
        except Exception:
            logger.exception("Falha ao desvincular audit_events (não bloqueante)")

        # 3) vínculos de roles
        cur.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))

        # 4) excluir o usuário
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        # auditoria/submission
        insert_submission(
            {
                "kind": "accounts",
                "version": "1.0.0",
                "actor_cpf": actor.get("cpf"),
                "actor_nome": actor.get("name") or actor.get("nome"),
                "actor_email": actor.get("email"),
                "payload": {"action": "delete_user", "user_id": user_id},
                "status": "done",
                "result": {"deleted": True},
                "error": None,
            }
        )
        add_audit("accounts", "delete_user", actor, {"user_id": user_id})
        return {"ok": True}


@router.put("/users/{user_id}/password")
def set_password(user_id: str, payload: SetPasswordIn, request: Request):
    actor = request.session.get("user") or {}
    pwd_hash = hasher.hash(payload.password)
    with _pg() as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (pwd_hash, user_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        insert_submission(
            {
                "kind": "accounts",
                "version": "1.0.0",
                "actor_cpf": actor.get("cpf"),
                "actor_nome": actor.get("name") or actor.get("nome"),
                "actor_email": actor.get("email"),
                "payload": {"action": "set_password", "user_id": user_id},
                "status": "done",
                "result": {"updated": True},
                "error": None,
            }
        )
        add_audit("accounts", "set_password", actor, {"user_id": user_id})
        return {"ok": True}


@router.put("/users/{user_id}/roles")
def set_roles(user_id: str, body: Dict[str, Any], request: Request):
    roles = normalize_roles([r for r in (body.get("roles") or []) if isinstance(r, str)])
    actor = request.session.get("user") or {}

    with _pg() as conn, conn.cursor() as cur:
        # valida usuário alvo
        cur.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        # impedir remoção do próprio 'admin'
        if str(actor.get("id") or actor.get("user_id") or "") == user_id and "admin" not in roles:
            cur.execute(
                """
                SELECT 1
                FROM user_roles ur JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = %s AND r.name = 'admin'
                LIMIT 1
                """,
                (user_id,),
            )
            if cur.fetchone():
                raise HTTPException(
                    status_code=400,
                    detail="Você não pode remover a role 'admin' da sua própria conta.",
                )

        # proteger “último admin”
        if "admin" not in roles and is_last_admin(cur, user_id):
            raise HTTPException(status_code=400, detail="O sistema deve manter ao menos um administrador.")

        # cria roles inexistentes
        if roles:
            cur.execute("SELECT name FROM roles WHERE name = ANY(%s)", (roles,))
            existing_names = {r["name"] for r in (cur.fetchall() or [])}
            to_create = [r for r in roles if r not in existing_names]
            for r in to_create:
                cur.execute(
                    "INSERT INTO roles (name, description) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
                    (r, None),
                )

        # mapeia role->id
        role_map: Dict[str, Any] = {}
        if roles:
            cur.execute("SELECT id, name FROM roles WHERE name = ANY(%s)", (roles,))
            role_map = {row["name"]: row["id"] for row in (cur.fetchall() or [])}

        # aplica
        cur.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
        for r in roles:
            rid = role_map.get(r)
            if rid:
                cur.execute(
                    "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (user_id, rid),
                )

        insert_submission(
            {
                "kind": "accounts",
                "version": "1.0.0",
                "actor_cpf": actor.get("cpf"),
                "actor_nome": actor.get("name") or actor.get("nome"),
                "actor_email": actor.get("email"),
                "payload": {"action": "set_roles", "user_id": user_id, "roles": roles},
                "status": "done",
                "result": {"updated": True, "roles": roles},
                "error": None,
            }
        )
        add_audit("accounts", "set_roles", actor, {"user_id": user_id, "roles": roles})
        return {"ok": True, "roles": roles}


# -- roles: list/create/delete
@router.get("/roles")
def list_roles() -> Dict[str, Any]:
    with _pg() as conn, conn.cursor() as cur:
        cur.execute("SELECT id::text, name, description, created_at FROM roles ORDER BY name ASC")
        rows = [dict(r) for r in (cur.fetchall() or [])]
        return {"items": rows, "count": len(rows)}


@router.post("/roles")
def create_role(payload: RoleIn, request: Request):
    name_norm = (payload.name or "").strip().lower()
    if name_norm in BLOCKED_ROLES:
        raise HTTPException(status_code=400, detail="Role reservado.")
    if not ROLE_OK_RE.match(name_norm):
        raise HTTPException(statuscode=422, detail="Nome do role inválido (use letras/números/._:-).")

    with _pg() as conn, conn.cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO roles (name, description) VALUES (%s, %s) RETURNING id::text",
                (name_norm, payload.description),
            )
            row = cur.fetchone() or {}
            role_id = row.get("id")
            if not role_id:
                cur.execute("SELECT id::text FROM roles WHERE name = %s", (name_norm,))
                got = cur.fetchone() or {}
                role_id = got.get("id")
                if not role_id:
                    return err_json(409, code="conflict", message="Não foi possível criar ou recuperar o role.")
        except Exception as e:
            return err_json(409, code="conflict", message="Role já existe?", details=str(e))

        actor = request.session.get("user") or {}
        add_audit("accounts", "create_role", actor, {"role": name_norm})
        insert_submission(
            {
                "kind": "accounts",
                "version": "1.0.0",
                "actor_cpf": actor.get("cpf"),
                "actor_nome": actor.get("name") or actor.get("nome"),
                "actor_email": actor.get("email"),
                "payload": {"action": "create_role", "role": name_norm},
                "status": "done",
                "result": {"role_id": role_id},
                "error": None,
            }
        )
        return {"ok": True, "role_id": role_id}


@router.delete("/roles/{role_name}")
def delete_role(role_name: str, request: Request):
    role_name = (role_name or "").strip().lower()
    if role_name in BLOCKED_ROLES:
        raise HTTPException(status_code=400, detail="Role reservado.")
    if role_name == "admin":
        raise HTTPException(status_code=400, detail="Não é permitido remover o role 'admin'.")

    with _pg() as conn, conn.cursor() as cur:
        # encontra id (dict_row => acessar pelo nome da coluna!)
        cur.execute("SELECT id FROM roles WHERE name = %s", (role_name,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Role não encontrada.")
        role_id = row["id"]  # acesso por chave do dict_row

        # desvincula e remove
        cur.execute("DELETE FROM user_roles WHERE role_id = %s", (role_id,))
        cur.execute("DELETE FROM roles WHERE id = %s", (role_id,))

        actor = request.session.get("user") or {}
        add_audit("accounts", "delete_role", actor, {"role": role_name})
        insert_submission(
            {
                "kind": "accounts",
                "version": "1.0.0",
                "actor_cpf": actor.get("cpf"),
                "actor_nome": actor.get("name") or actor.get("nome"),
                "actor_email": actor.get("email"),
                "payload": {"action": "delete_role", "role": role_name},
                "status": "done",
                "result": {"deleted": True},
                "error": None,
            }
        )
        return {"ok": True}


# -----------------------------------------------------------------------------
# Compat com contrato de "automations"
# -----------------------------------------------------------------------------
@router.get("/submissions")
def submissions(limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    limit = clamp(limit, 1, 200)
    offset = max(0, offset)
    return {"items": list_submissions_admin(kind="accounts", limit=limit, offset=offset)}


@router.get("/submissions/{submission_id}")
def get_sub(submission_id: str) -> Dict[str, Any]:
    sub = get_submission(submission_id)
    if not sub or sub.get("kind") != "accounts":
        raise HTTPException(status_code=404, detail="submission not found")
    return sub


@router.post("/submissions/{submission_id}/download")
def download(_submission_id: str):
    raise HTTPException(status_code=404, detail="sem artefatos para download nesta automação")
