# apps/bff/app/auth/rbac.py
from __future__ import annotations

import os
from typing import Iterable, Set, Dict, Any, Optional

import psycopg
from fastapi import HTTPException, Request

# Config
DATABASE_URL = os.getenv("DATABASE_URL")
# Quando True, tenta consultar o must_change_password no BD (join com a sessão) para evitar staleness.
# Se não conseguir (sem DB/erro/sessão ausente), cai no flag da sessão web.
AUTH_ENFORCE_PASSWORD_CHANGED_DB = os.getenv("AUTH_ENFORCE_PASSWORD_CHANGED_DB", "1") in ("1", "true", "True")

def _pg_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL, autocommit=True)


def _get_user(req: Request) -> Dict[str, Any]:
    """
    Obtém o usuário da sessão (preenchida no login).
    401 se não autenticado.
    """
    user = req.session.get("user") if hasattr(req, "session") else None
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


def require_auth(req: Request) -> Dict[str, Any]:
    """
    Exige estar autenticado.
    Retorna o payload do usuário.
    """
    return _get_user(req)


def _must_change_password_from_db(req: Request) -> Optional[bool]:
    """
    Tenta ler o must_change_password diretamente do BD usando a sessão atual.
    Retorna:
      - True/False se conseguiu ler do BD
      - None se não foi possível (sem DB, sem sessão, erro, etc.) => caller decide fallback
    """
    if not AUTH_ENFORCE_PASSWORD_CHANGED_DB:
        return None
    db_sess_id = None
    try:
        db_sess_id = req.session.get("db_session_id") if hasattr(req, "session") else None
    except Exception:
        db_sess_id = None
    if not db_sess_id:
       return None
    if not DATABASE_URL:
        return None
    try:
        with _pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.must_change_password
                  FROM auth_sessions s
                  JOIN users u ON u.id = s.user_id
                 WHERE s.id = %s
                   AND s.revoked_at IS NULL
                   AND s.expires_at > now()
                """,
                (db_sess_id,),
            )
            row = cur.fetchone()
            if row is None:
                # Sessão inválida no BD -> tratar como não autenticado
                raise HTTPException(status_code=401, detail="invalid_session")
            (must_change_password,) = row
            return bool(must_change_password)
    except HTTPException:
        raise
    except Exception:
        # Qualquer falha -> deixa caller decidir fallback
        return None


def require_password_changed(req: Request) -> Dict[str, Any]:
    """
    Exige que o usuário já tenha trocado a senha.
    Retorna o payload do usuário (para encadear com RBAC).
    Regras:
      1) Tenta validar no BD (se habilitado por env); se falhar, usa o flag da sessão.
      2) Se 'must_change_password' estiver True => 403 "PASSWORD_CHANGE_REQUIRED".
    """
    user = _get_user(req)
    mcp_db = _must_change_password_from_db(req)
    if mcp_db is True:
        raise HTTPException(status_code=403, detail="PASSWORD_CHANGE_REQUIRED")
    if mcp_db is None:
        # Fallback: usa flag do payload da sessão
        if user.get("must_change_password") is True:
            raise HTTPException(status_code=403, detail="PASSWORD_CHANGE_REQUIRED")
    return user

def _norm(roles: Optional[Iterable[str]]) -> Set[str]:
    if not roles:
        return set()
    return {str(r).strip().lower() for r in roles if str(r).strip()}


def require_roles_any(*roles_required: str):
    """
    Exige ao menos UM dos roles informados. Bypass para 'admin' OU is_superuser.
    Uso como dependency:
        @router.get(..., dependencies=[Depends(require_password_changed), Depends(require_roles_any("compras.viewer","compras.editor"))])
    Ou capturando o usuário:
      def endpoint(user = Depends(require_password_changed), u = Depends(require_roles_any("..."))): ...
    """
    required = _norm(roles_required)

    def dep(req: Request) -> Dict[str, Any]:
        user = require_password_changed(req)
        user_roles = _norm(user.get("roles"))
        if user.get("is_superuser") is True or "admin" in user_roles:
            return user
        if not required:
            return user
        if user_roles.isdisjoint(required):
            raise HTTPException(status_code=403, detail="forbidden")
        return user

    return dep


def require_roles_all(*roles_required: str):
    """
    Exige TODOS os roles informados. Bypass para 'admin' OU is_superuser.
    """
    required = _norm(roles_required)

    def dep(req: Request) -> Dict[str, Any]:
        user = require_password_changed(req)
        user_roles = _norm(user.get("roles"))
        if user.get("is_superuser") is True or "admin" in user_roles:
            return user
        if not required.issubset(user_roles):
            raise HTTPException(status_code=403, detail="forbidden")
        return user

    return dep
