# apps/bff/app/auth/rbac.py
"""
Dependências de autenticação e autorização (RBAC) para o BFF do Portal AGEPAR.

Visão geral
-----------
Este módulo define dependências para FastAPI/Starlette que:
- Garantem que a requisição está autenticada.
- Exigem que o usuário tenha trocado a senha (bloqueio por `must_change_password`).
- Aplicam checagem de papéis de acesso (RBAC) no modelo *ANY-of* ou *ALL-of*.

As funções principais são:
- `require_auth`                → valida autenticação (401 caso contrário).
- `require_password_changed`    → bloqueia se `must_change_password` estiver ativo (403).
- `require_roles_any(*roles)`   → exige ao menos um dos papéis.
- `require_roles_all(*roles)`   → exige todos os papéis informados.

Integração com sessão e banco
-----------------------------
O usuário autenticado é lido de `request.session["user"]` (preenchido no login).
Para reforçar a exigência de troca de senha, pode-se consultar diretamente o BD
associando a sessão persistida (`auth_sessions`) ao usuário (`users`).

Variáveis de ambiente
---------------------
- DATABASE_URL : string de conexão do PostgreSQL (necessária para validação no BD).
- AUTH_ENFORCE_PASSWORD_CHANGED_DB : "1"/"true" para consultar o BD ao checar
  `must_change_password`. Se ausente/erro, cai no flag presente no payload
  da sessão web.

Erros e segurança
-----------------
- Não autenticado → `HTTPException(401, "not authenticated")`.
- Sessão inválida no BD → `HTTPException(401, "invalid_session")`.
- Senha precisa ser trocada → `HTTPException(403, "PASSWORD_CHANGE_REQUIRED")`.
- Sem os papéis requeridos → `HTTPException(403, "forbidden")`.
- Usuários com `is_superuser=True` ou papel `"admin"` possuem bypass de RBAC.

Exemplos de uso (FastAPI)
-------------------------
    router = APIRouter(
        prefix="/api/area",
        dependencies=[Depends(require_password_changed), Depends(require_roles_any("area.viewer","area.editor"))],
    )

    @router.get("/itens")
    def listar_itens(user = Depends(require_roles_any("area.viewer"))):
        ...

"""

from __future__ import annotations

import os
from typing import Iterable, Set, Dict, Any, Optional

import psycopg
from fastapi import HTTPException, Request

DATABASE_URL = os.getenv("DATABASE_URL")
AUTH_ENFORCE_PASSWORD_CHANGED_DB = os.getenv("AUTH_ENFORCE_PASSWORD_CHANGED_DB", "1") in ("1", "true", "True")


def _pg_conn():
    """
    Cria uma conexão curta com PostgreSQL usando `DATABASE_URL`.

    Retorna
    -------
    psycopg.Connection
        Conexão com `autocommit=True`.

    Levanta
    -------
    RuntimeError
        Se `DATABASE_URL` não estiver configurada.
    """
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL, autocommit=True)


def _get_user(req: Request) -> Dict[str, Any]:
    """
    Obtém o payload de usuário autenticado da sessão.

    Parâmetros
    ----------
    req : Request
        Requisição atual.

    Retorna
    -------
    Dict[str, Any]
        Dicionário do usuário armazenado em `request.session["user"]`.

    Levanta
    -------
    HTTPException
        401 se a sessão não contiver um usuário autenticado.
    """
    user = req.session.get("user") if hasattr(req, "session") else None
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


def require_auth(req: Request) -> Dict[str, Any]:
    """
    Dependência: exige que a requisição esteja autenticada.

    Parâmetros
    ----------
    req : Request
        Requisição atual.

    Retorna
    -------
    Dict[str, Any]
        Payload do usuário autenticado.
    """
    return _get_user(req)


def _must_change_password_from_db(req: Request) -> Optional[bool]:
    """
    Tenta ler `must_change_password` diretamente do BD usando a sessão persistida.

    Parâmetros
    ----------
    req : Request
        Requisição atual (usa `request.session["db_session_id"]`).

    Retorna
    -------
    Optional[bool]
        - True  → deve trocar a senha.
        - False → não precisa trocar.
        - None  → não foi possível determinar via BD (sem sessão/sem DB/erro).

    Levanta
    -------
    HTTPException
        401 com `invalid_session` se a sessão no BD estiver inválida/expirada.
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
                raise HTTPException(status_code=401, detail="invalid_session")
            (must_change_password,) = row
            return bool(must_change_password)
    except HTTPException:
        raise
    except Exception:
        return None


def require_password_changed(req: Request) -> Dict[str, Any]:
    """
    Dependência: bloqueia acesso se o usuário precisar trocar a senha.

    Estratégia
    ----------
    1) Tenta ler `must_change_password` do BD (se habilitado).
    2) Em caso de falha/indisponibilidade, cai no flag presente no payload da
       sessão HTTP.

    Parâmetros
    ----------
    req : Request
        Requisição atual.

    Retorna
    -------
    Dict[str, Any]
        Payload do usuário (para encadear com outras dependências).

    Levanta
    -------
    HTTPException
        401 se não autenticado/sem sessão válida.
        403 com `PASSWORD_CHANGE_REQUIRED` quando a troca for obrigatória.
    """
    user = _get_user(req)
    mcp_db = _must_change_password_from_db(req)
    if mcp_db is True:
        raise HTTPException(status_code=403, detail="PASSWORD_CHANGE_REQUIRED")
    if mcp_db is None:
        if user.get("must_change_password") is True:
            raise HTTPException(status_code=403, detail="PASSWORD_CHANGE_REQUIRED")
    return user


def _norm(roles: Optional[Iterable[str]]) -> Set[str]:
    """
    Normaliza uma coleção de papéis para um conjunto em minúsculas sem vazios.

    Parâmetros
    ----------
    roles : Optional[Iterable[str]]
        Coleção de papéis (strings).

    Retorna
    -------
    Set[str]
        Conjunto normalizado.
    """
    if not roles:
        return set()
    return {str(r).strip().lower() for r in roles if str(r).strip()}


def require_roles_any(*roles_required: str):
    """
    Dependência de RBAC: exige ao menos **um** dos papéis informados.

    Regras
    ------
    - `admin` ou `is_superuser=True` têm bypass.
    - Encadeia com `require_password_changed` para reforçar fluxo de segurança.

    Parâmetros
    ----------
    *roles_required : str
        Papéis aceitos (qualquer um satisfaz).

    Retorna
    -------
    Callable[[Request], Dict[str, Any]]
        Função-dependência para uso com `Depends(...)`.

    Exemplo
    -------
        dependencies=[Depends(require_password_changed), Depends(require_roles_any("compras.viewer","compras.editor"))]
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
    Dependência de RBAC: exige **todos** os papéis informados.

    Regras
    ------
    - `admin` ou `is_superuser=True` têm bypass.
    - Encadeia com `require_password_changed`.

    Parâmetros
    ----------
    *roles_required : str
        Papéis exigidos (interseção completa).

    Retorna
    -------
    Callable[[Request], Dict[str, Any]]
        Função-dependência para uso com `Depends(...)`.
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
