# apps/bff/app/auth/routes.py
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import psycopg
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

router = APIRouter()

# -------- Config --------
DATABASE_URL = os.getenv("DATABASE_URL")
ENV = os.getenv("ENV", "dev")
AUTH_DEV_ALLOW_ANY_PASSWORD = os.getenv("AUTH_DEV_ALLOW_ANY_PASSWORD", "1") in ("1", "true", "True")
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "8"))
REMEMBER_ME_TTL_DAYS = int(os.getenv("REMEMBER_ME_TTL_DAYS", "30"))

ph = PasswordHasher()  # Argon2id
CPF_RE = re.compile(r"^\d{11}$")


def _pg_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL, autocommit=True)


def _now() -> datetime:
    return datetime.utcnow()


def _normalize_identifier(identifier: str) -> Dict[str, Optional[str]]:
    ident = (identifier or "").strip()
    if CPF_RE.fullmatch(ident):
        return {"cpf": ident, "email": None}
    return {"cpf": None, "email": ident}


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
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_events (actor_user_id, action, object_type, object_id, message, metadata, ip, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (actor_user_id, action, obj_type, obj_id, message, psycopg.types.json.Json(metadata), ip, ua),
        )


def _insert_login_attempt(
    conn,
    user_id: Optional[str],
    identifier: str,
    success: bool,
    reason: Optional[str],
    ip: Optional[str],
    ua: Optional[str],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO login_attempts (user_id, login_identifier, success, reason, ip, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, identifier, success, reason, ip, ua),
        )
    try:
        conn.commit()
    except Exception:
        pass


def _load_roles(conn, user_id: str) -> List[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.name
            FROM roles r
            JOIN user_roles ur ON ur.role_id = r.id
            WHERE ur.user_id = %s
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        return [r[0] for r in rows] if rows else []


def _rate_limited(conn, identifier: str, ip: Optional[str], window_minutes: int = 15, max_attempts: int = 5) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM login_attempts
            WHERE at >= now() - (%s || ' minutes')::interval
              AND success = false
              AND (login_identifier = %s OR (ip IS NOT NULL AND ip = %s))
            """,
            (window_minutes, identifier, ip),
        )
        (count,) = cur.fetchone()
        return (count or 0) >= max_attempts


# ---------------------------- Schemas ----------------------------

class RegisterIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    name: str = Field(min_length=2)
    email: Optional[EmailStr] = None
    cpf: Optional[str] = Field(default=None, description="CPF com 11 dígitos numéricos")
    password: str = Field(min_length=8, max_length=128)

    def validate_business(self):
        if not self.email and not self.cpf:
            raise HTTPException(status_code=422, detail="Informe email ou CPF.")
        if self.cpf and not CPF_RE.fullmatch(self.cpf):
            raise HTTPException(status_code=422, detail="CPF deve ter exatamente 11 dígitos numéricos.")


class RegisterOut(BaseModel):
    id: uuid.UUID
    name: str
    email: Optional[str] = None
    cpf: Optional[str] = None
    status: str


class LoginIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    identifier: str = Field(description="e-mail ou CPF (11 dígitos)")
    password: str = Field(min_length=1, max_length=128)
    remember_me: bool = False


class LoginOut(BaseModel):
    cpf: Optional[str] = None
    nome: str
    email: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    unidades: List[str] = Field(default_factory=list)
    auth_mode: str
    is_superuser: bool = False  # <- inclui no response_model para evitar extra


# ---------------------------- Routes ----------------------------

@router.post(
    "/api/auth/register",
    response_model=RegisterOut,
    responses={400: {"description": "Erro de validação"}, 409: {"description": "Conflito (email/CPF já em uso)"}, 422: {"description": "Entrada inválida"}},
)
def register_user(payload: RegisterIn, request: Request):
    payload.validate_business()
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        pwd_hash = ph.hash(payload.password)
    except Exception:
        raise HTTPException(status_code=400, detail="Falha ao processar a senha.")

    with _pg_conn() as conn, conn.cursor() as cur:
        if payload.email:
            cur.execute("SELECT id FROM users WHERE email = %s", (payload.email,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="E-mail já cadastrado.")
        if payload.cpf:
            cur.execute("SELECT id FROM users WHERE cpf = %s", (payload.cpf,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="CPF já cadastrado.")

        user_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO users (id, cpf, email, name, password_hash, status, source, is_superuser, attrs, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, 'active', 'local', FALSE, '{}'::jsonb, now(), now())
            """,
            (str(user_id), payload.cpf, payload.email, payload.name, pwd_hash),
        )

        _insert_audit(
            conn,
            actor_user_id=str(user_id),
            action="user.register",
            obj_type="user",
            obj_id=str(user_id),
            message="Registro de usuário (local)",
            metadata={},
            ip=ip,
            ua=ua,
        )

        return RegisterOut(id=user_id, name=payload.name, email=payload.email, cpf=payload.cpf, status="active")


@router.post(
    "/api/auth/login",
    response_model=LoginOut,
    responses={
        401: {"description": "Credenciais inválidas"},
        403: {"description": "Usuário bloqueado"},
        429: {"description": "Muitas tentativas. Tente novamente mais tarde."},
    },
)
def login_user(payload: LoginIn, request: Request):
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    ident = _normalize_identifier(payload.identifier)
    email, cpf = ident["email"], ident["cpf"]

    with _pg_conn() as conn, conn.cursor() as cur:
        if _rate_limited(conn, payload.identifier, ip):
            _insert_login_attempt(conn, None, payload.identifier, False, "rate_limited", ip, ua)
            raise HTTPException(status_code=429, detail="Muitas tentativas. Tente novamente mais tarde.")

        if email:
            cur.execute("""SELECT id, cpf, email, name, password_hash, status, is_superuser FROM users WHERE email = %s""", (email,))
        else:
            cur.execute("""SELECT id, cpf, email, name, password_hash, status, is_superuser FROM users WHERE cpf = %s""", (cpf,))
        row = cur.fetchone()

        if not row:
            _insert_login_attempt(conn, None, payload.identifier, False, "not_found", ip, ua)
            raise HTTPException(status_code=401, detail="Credenciais inválidas.")

        user_id, u_cpf, u_email, u_name, pwd_hash, status, is_superuser = row

        if status != "active":
            _insert_login_attempt(conn, str(user_id), payload.identifier, False, f"status_{status}", ip, ua)
            raise HTTPException(status_code=403, detail=f"Usuário {status}.")

        ok = False
        if u_email == "dev@local" and ENV == "dev" and AUTH_DEV_ALLOW_ANY_PASSWORD:
            ok = True
        else:
            try:
                if not pwd_hash:
                    raise VerifyMismatchError
                ph.verify(pwd_hash, payload.password)
                ok = True
            except VerifyMismatchError:
                ok = False

        if not ok:
            _insert_login_attempt(conn, str(user_id), payload.identifier, False, "bad_credentials", ip, ua)
            raise HTTPException(status_code=401, detail="Credenciais inválidas.")

        # Session
        sess_id = uuid.uuid4()
        ttl = timedelta(days=REMEMBER_ME_TTL_DAYS) if payload.remember_me else timedelta(hours=SESSION_TTL_HOURS)
        expires = _now() + ttl
        cur.execute(
            """
            INSERT INTO auth_sessions (id, user_id, created_at, last_seen_at, expires_at, ip, user_agent)
            VALUES (%s, %s, now(), now(), %s, %s, %s)
            """,
            (str(sess_id), user_id, expires, ip, ua),
        )

        roles = _load_roles(conn, user_id)

        # HARDENING: superuser recebe 'admin' (bypass RBAC)
        if is_superuser and "admin" not in roles:
            roles = ["admin", *roles]

        user_payload = {
            "cpf": u_cpf,
            "nome": u_name,
            "email": u_email,
            "roles": roles or ["user"],
            "unidades": ["AGEPAR"],
            "auth_mode": "local",
            "is_superuser": bool(is_superuser),
        }
        request.session["user"] = user_payload
        request.session["db_session_id"] = str(sess_id)

        _insert_login_attempt(conn, str(user_id), payload.identifier, True, "ok", ip, ua)
        _insert_audit(
            conn,
            actor_user_id=str(user_id),
            action="auth.login",
            obj_type="user",
            obj_id=str(user_id),
            message="Login (local)",
            metadata={},
            ip=ip,
            ua=ua,
        )

        return LoginOut(**user_payload)


@router.post("/api/auth/logout", status_code=204, response_class=Response)
def logout_user(request: Request):
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    db_sess_id = request.session.get("db_session_id")

    with _pg_conn() as conn:
        actor_id = None
        if db_sess_id:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE auth_sessions SET revoked_at = now() WHERE id = %s RETURNING user_id",
                    (db_sess_id,),
                )
                row = cur.fetchone()
                if row:
                    actor_id = row[0]
        _insert_audit(
            conn,
            actor_user_id=str(actor_id) if actor_id else None,
            action="auth.logout",
            obj_type="user",
            obj_id=None,
            message="Logout",
            metadata={},
            ip=ip,
            ua=ua,
        )

    request.session.clear()
    return Response(status_code=204)
