# apps/bff/app/auth/rbac.py
from __future__ import annotations

from typing import Iterable, Set, Dict, Any, Optional
from fastapi import HTTPException, Request


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


def _norm(roles: Optional[Iterable[str]]) -> Set[str]:
    if not roles:
        return set()
    return {str(r).strip().lower() for r in roles if str(r).strip()}


def require_roles_any(*roles_required: str):
    """
    Exige ao menos UM dos roles informados. Bypass para 'admin' OU is_superuser.
    Uso como dependency:
      @router.get(..., dependencies=[Depends(require_roles_any("compras.viewer","compras.editor"))])
    Ou capturando o usuário:
      def endpoint(user = Depends(require_roles_any("..."))): ...
    """
    required = _norm(roles_required)

    def dep(req: Request) -> Dict[str, Any]:
        user = _get_user(req)
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
        user = _get_user(req)
        user_roles = _norm(user.get("roles"))
        if user.get("is_superuser") is True or "admin" in user_roles:
            return user
        if not required.issubset(user_roles):
            raise HTTPException(status_code=403, detail="forbidden")
        return user

    return dep
