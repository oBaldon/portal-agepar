# apps/bff/app/auth/routes.py
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import psycopg
from fastapi import APIRouter, HTTPException, Request, Response
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from pydantic import BaseModel, ConfigDict, Field
from .schemas import (
    RegisterIn,
    RegisterOut,
    LoginIn,
    LoginOut,
)
from .password_policy import (
    evaluate_password,
    compare_new_password_and_confirm,
)

router = APIRouter()

# -------- Config --------
DATABASE_URL = os.getenv("DATABASE_URL")
ENV = os.getenv("ENV", "dev")
AUTH_DEV_ALLOW_ANY_PASSWORD = os.getenv("AUTH_DEV_ALLOW_ANY_PASSWORD", "1") in ("1", "true", "True")
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "8"))
REMEMBER_ME_TTL_DAYS = int(os.getenv("REMEMBER_ME_TTL_DAYS", "30"))
AUTH_RATE_LIMIT_SCOPE = os.getenv("AUTH_RATE_LIMIT_SCOPE", "both")  # both|identifier|ip|off
AUTH_RATE_LIMIT_WINDOW_MINUTES = int(os.getenv("AUTH_RATE_LIMIT_WINDOW_MINUTES", "15"))
AUTH_RATE_LIMIT_MAX_ATTEMPTS = int(os.getenv("AUTH_RATE_LIMIT_MAX_ATTEMPTS", "5"))
AUTH_REVOKE_ALL_ON_PASSWORD_CHANGE = os.getenv("AUTH_REVOKE_ALL_ON_PASSWORD_CHANGE", "0") in ("1", "true", "True")

# Roles padrão vindas do ambiente (ex.: "user,automations.dfd")
AUTH_DEFAULT_ROLES: List[str] = [
    r.strip() for r in os.getenv("AUTH_DEFAULT_ROLES", "").split(",") if r.strip()
]

# Toggle de auto-registro (preferência para AUTH_ENABLE_SELF_REGISTER; compat com ACCOUNTS_CREATE_LEGACY_ENABLED)
_auth_enable_self_register = os.getenv("AUTH_ENABLE_SELF_REGISTER")
_accounts_create_legacy_enabled = os.getenv("ACCOUNTS_CREATE_LEGACY_ENABLED")
if _auth_enable_self_register is not None:
    SELF_REGISTER_ENABLED = _auth_enable_self_register.lower() in ("1", "true", "yes", "y")
elif _accounts_create_legacy_enabled is not None:
    SELF_REGISTER_ENABLED = _accounts_create_legacy_enabled.lower() in ("1", "true", "yes", "y")
else:
    SELF_REGISTER_ENABLED = False

ph = PasswordHasher()  # Argon2id
CPF_RE = re.compile(r"^\d{11}$")


def _pg_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL, autocommit=True)


def _now() -> datetime:
    # UTC na aplicação; o banco usa timezone próprio via NOW().
    return datetime.utcnow()


def _normalize_identifier(identifier: str) -> Dict[str, Optional[str]]:
    ident = (identifier or "").strip()
    if CPF_RE.fullmatch(ident):
        return {"cpf": ident, "email": None}
    # e-mail/usuário: normalize para lower
    return {"cpf": None, "email": ident.lower()}


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


def _rate_limited(conn, identifier: str, ip: Optional[str],
                  window_minutes: int = AUTH_RATE_LIMIT_WINDOW_MINUTES,
                  max_attempts: int = AUTH_RATE_LIMIT_MAX_ATTEMPTS) -> bool:
    scope = AUTH_RATE_LIMIT_SCOPE  # both|identifier|ip|off
    if scope == "off":
        return False
    with conn.cursor() as cur:
        if scope == "identifier":
            cur.execute(
                """
                SELECT count(*) FROM login_attempts
                WHERE at >= now() - (%s || ' minutes')::interval
                  AND success = false
                  AND login_identifier = %s
                """,
                (window_minutes, identifier),
            )
        elif scope == "ip":
            cur.execute(
                """
                SELECT count(*) FROM login_attempts
                WHERE at >= now() - (%s || ' minutes')::interval
                  AND success = false
                  AND ip = %s
                """,
                (window_minutes, ip),
            )
        else:  # both
            cur.execute(
                """
                SELECT count(*) FROM login_attempts
                WHERE at >= now() - (%s || ' minutes')::interval
                  AND success = false
                  AND (login_identifier = %s OR (ip IS NOT NULL AND ip = %s))
                """,
                (window_minutes, identifier, ip),
            )
        (count,) = cur.fetchone()
        return (count or 0) >= max_attempts


# -------- helpers de roles --------
def _merge_default_roles(roles: Optional[List[str]]) -> List[str]:
    merged = set(roles or [])
    merged.update(AUTH_DEFAULT_ROLES)
    return sorted(merged)


# ---------------------------- Routes ----------------------------

@router.post(
    "/api/auth/register",
    response_model=RegisterOut,
    responses={
        400: {"description": "Erro de validação"},
        403: {"description": "Auto-registro desativado"},
        409: {"description": "Conflito (email/CPF já em uso)"},
        410: {"description": "Funcionalidade descontinuada"},
        422: {"description": "Entrada inválida"},
    },
)
def register_user(payload: RegisterIn, request: Request):
    if not SELF_REGISTER_ENABLED:
        raise HTTPException(status_code=410, detail="Auto-registro desativado.")

    try:
        payload.validate_business()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        pwd_hash = ph.hash(payload.password)
    except Exception:
        raise HTTPException(status_code=400, detail="Falha ao processar a senha.")

    with _pg_conn() as conn, conn.cursor() as cur:
        if payload.email:
            cur.execute("SELECT id FROM users WHERE email = %s", (payload.email.strip().lower(),))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="E-mail já cadastrado.")
        if payload.cpf:
            cur.execute("SELECT id FROM users WHERE cpf = %s", (payload.cpf.strip(),))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="CPF já cadastrado.")

        user_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO users (id, cpf, email, name, password_hash, status, source, is_superuser, attrs, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, 'active', 'local', FALSE, '{}'::jsonb, now(), now())
            """,
            (str(user_id),
             payload.cpf.strip() if payload.cpf else None,
             payload.email.strip().lower() if payload.email else None,
             payload.name,
             pwd_hash),
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

        return RegisterOut(id=user_id, name=payload.name,
                           email=(payload.email.strip().lower() if payload.email else None),
                           cpf=(payload.cpf.strip() if payload.cpf else None),
                           status="active")


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
    identifier_norm = email if email else (cpf or payload.identifier.strip())

    with _pg_conn() as conn, conn.cursor() as cur:
        if _rate_limited(conn, identifier_norm, ip):
            _insert_login_attempt(conn, None, identifier_norm, False, "rate_limited", ip, ua)
            raise HTTPException(status_code=429, detail="Muitas tentativas. Tente novamente mais tarde.")

        if email:
            cur.execute(
                """
                SELECT id, cpf, email, name, password_hash, status, is_superuser, must_change_password
                FROM users
                WHERE email = %s
                """,
                (email,),
            )
        else:
            cur.execute(
                """
                SELECT id, cpf, email, name, password_hash, status, is_superuser, must_change_password
                FROM users
                WHERE cpf = %s
                """,
                (cpf,),
            )
        row = cur.fetchone()

        if not row:
            _insert_login_attempt(conn, None, identifier_norm, False, "not_found", ip, ua)
            raise HTTPException(status_code=401, detail="Credenciais inválidas.")

        user_id, u_cpf, u_email, u_name, pwd_hash, status, is_superuser, must_change_password = row

        if status != "active":
            _insert_login_attempt(conn, str(user_id), identifier_norm, False, f"status_{status}", ip, ua)
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
            _insert_login_attempt(conn, str(user_id), identifier_norm, False, "bad_credentials", ip, ua)
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

        # Roles
        roles_db = _load_roles(conn, user_id)
        roles = _merge_default_roles(roles_db)
        if is_superuser and "admin" not in roles:
            roles = sorted(set(roles + ["admin"]))
        if not roles:
            roles = ["user"]

        user_payload = {
            "cpf": u_cpf,
            "nome": u_name,
            "email": u_email,
            "roles": roles,
            "unidades": ["AGEPAR"],
            "auth_mode": "local",
            "is_superuser": bool(is_superuser),
            "must_change_password": bool(must_change_password),
        }
        # Persistir na sessão web
        request.session.clear()
        request.session["user"] = user_payload
        request.session["db_session_id"] = str(sess_id)

        _insert_login_attempt(conn, str(user_id), identifier_norm, True, "ok", ip, ua)
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


# ---------------------------- Change Password ----------------------------

class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)
    new_password_confirm: str = Field(min_length=1, max_length=128)


@router.post(
    "/api/auth/change-password",
    response_model=LoginOut,
    responses={
        400: {"description": "Violação de política de senha"},
        401: {"description": "Sessão inválida ou credenciais atuais incorretas"},
        403: {"description": "Usuário bloqueado"},
        422: {"description": "Entrada inválida (confirm não confere, etc.)"},
    },
)
def change_password(payload: ChangePasswordIn, request: Request):
    """
    Troca a senha do usuário autenticado:
    - Verifica a senha atual
    - Aplica política à nova senha
    - Atualiza hash e marca must_change_password=false
    - Revoga a sessão atual (ou todas) e cria **nova sessão**
    - Retorna LoginOut (flat)
    """
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    db_sess_id = request.session.get("db_session_id")
    if not db_sess_id:
        raise HTTPException(status_code=401, detail="invalid_session")

    confirm_err = compare_new_password_and_confirm(payload.new_password, payload.new_password_confirm)
    if confirm_err:
        raise HTTPException(status_code=422, detail={"confirm": confirm_err})

    with _pg_conn() as conn, conn.cursor() as cur:
        # Carrega usuário pela sessão atual
        cur.execute(
            """
            SELECT u.id, u.cpf, u.email, u.name, u.password_hash, u.status, u.is_superuser, u.must_change_password
            FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = %s
              AND s.revoked_at IS NULL
              AND s.expires_at > now()
            """,
            (db_sess_id,),
        )
        row = cur.fetchone()
        if not row:
            try:
                request.session.clear()
            except Exception:
                pass
            raise HTTPException(status_code=401, detail="invalid_session")

        user_id, u_cpf, u_email, u_name, pwd_hash, status, is_superuser, must_change_password = row

        if status != "active":
            raise HTTPException(status_code=403, detail=f"Usuário {status}.")

        # Verifica senha atual
        try:
            if not pwd_hash:
                raise VerifyMismatchError
            ph.verify(pwd_hash, payload.current_password)
        except VerifyMismatchError:
            raise HTTPException(status_code=401, detail="invalid_credentials")

        # Política de senha (usa identificadores)
        policy_errors = evaluate_password(payload.new_password, identifiers=[u_email, u_cpf, u_name])
        if policy_errors:
            raise HTTPException(status_code=400, detail={"password": policy_errors})

        # Hash e update
        try:
            new_hash = ph.hash(payload.new_password)
        except Exception:
            raise HTTPException(status_code=400, detail="Falha ao processar a nova senha.")

        cur.execute(
            """
            UPDATE users
               SET password_hash = %s,
                   must_change_password = FALSE,
                   updated_at = now()
             WHERE id = %s
            """,
            (new_hash, user_id),
        )

        _insert_audit(
            conn,
            actor_user_id=str(user_id),
            action="auth.password_changed",
            obj_type="user",
            obj_id=str(user_id),
            message="Troca de senha do usuário",
            metadata={"must_change_password_before": bool(must_change_password)},
            ip=ip,
            ua=ua,
        )

        # Revogar sessões
        if AUTH_REVOKE_ALL_ON_PASSWORD_CHANGE:
            cur.execute(
                "UPDATE auth_sessions SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL",
                (user_id,),
            )
        else:
            cur.execute(
                "UPDATE auth_sessions SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL",
                (db_sess_id,),
            )

        # Criar nova sessão (TTL padrão)
        new_sess_id = uuid.uuid4()
        ttl = timedelta(hours=SESSION_TTL_HOURS)
        new_expires = _now() + ttl
        cur.execute(
            """
            INSERT INTO auth_sessions (id, user_id, created_at, last_seen_at, expires_at, ip, user_agent)
            VALUES (%s, %s, now(), now(), %s, %s, %s)
            """,
            (str(new_sess_id), user_id, new_expires, ip, ua),
        )

        # Roles
        roles_db = _load_roles(conn, user_id)
        roles = _merge_default_roles(roles_db)
        if is_superuser and "admin" not in roles:
            roles = sorted(set(roles + ["admin"]))
        if not roles:
            roles = ["user"]

        user_payload = {
            "cpf": u_cpf,
            "nome": u_name,
            "email": u_email,
            "roles": roles,
            "unidades": ["AGEPAR"],
            "auth_mode": "local",
            "is_superuser": bool(is_superuser),
            "must_change_password": False,
        }

        # Zera e grava a **nova** sessão web (evita staleness e flicker)
        request.session.clear()
        request.session["user"] = user_payload
        request.session["db_session_id"] = str(new_sess_id)

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
