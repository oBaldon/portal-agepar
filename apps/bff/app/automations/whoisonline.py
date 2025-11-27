# apps/bff/app/automations/whoisonline.py
from __future__ import annotations

"""
Automação "Quem está online" (whoisonline).

Propósito
---------
Fornece páginas HTML e endpoints JSON para monitoramento de sessões ativas:
- UI embutida (iframe) para visualização.
- Listagem de sessões online com filtros.
- KPIs agregados (contagens, top agentes, janelas de atividade).
- Revogação idempotente de sessão específica.

Segurança / RBAC
----------------
- Todas as rotas deste módulo exigem *superuser* (não basta papel "admin").
- A checagem é aplicada via dependência global no `APIRouter`.

Efeitos colaterais
------------------
- Leitura/escrita no PostgreSQL via `_pg()`.
- Registro de auditoria com `add_audit` na revogação de sessão.
- Leitura de arquivos HTML do diretório de templates.

Exceções
--------
- `HTTPException(403)` quando o usuário não é superuser.
- `HTTPException(404)` para recursos inexistentes (ex.: sessão não encontrada).

Observações
-----------
A lógica original foi preservada integralmente; realizaram-se apenas:
- inclusão de docstrings completas em pt-BR;
- remoção de comentários;
- adição da referência de topo.
"""

import pathlib
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from app.db import _pg, add_audit
from app.auth.rbac import _get_user

KIND = "whoisonline"
VERSION = "0.1.0"
TPL_DIR = pathlib.Path(__file__).resolve().parent / "templates" / KIND


def require_superuser(req: Request) -> Dict[str, Any]:
    """
    Garante que o usuário autenticado seja superuser.

    Parâmetros
    ----------
    req : Request
        Requisição atual, utilizada para extrair o usuário da sessão.

    Retorna
    -------
    dict
        Objeto do usuário autenticado.

    Exceções
    --------
    HTTPException
        403 quando `is_superuser` não estiver habilitado.

    Observações
    -----------
    Esta função deve ser utilizada como dependência em rotas sensíveis.
    """
    user = _get_user(req)
    if not bool(user.get("is_superuser")):
        raise HTTPException(status_code=403, detail="superuser only")
    return user


router = APIRouter(
    prefix=f"/api/automations/{KIND}",
    tags=["automations", KIND],
    dependencies=[Depends(require_superuser)],
)


def _read_html(name: str) -> str:
    """
    Lê o conteúdo HTML de um template da automação.

    Parâmetros
    ----------
    name : str
        Nome do arquivo HTML (por exemplo, 'ui.html').

    Retorna
    -------
    str
        Conteúdo HTML carregado do disco.

    Exceções
    --------
    FileNotFoundError
        Propaga se o arquivo não existir.
    """
    path = TPL_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@router.get("/ui")
def ui() -> HTMLResponse:
    """
    Página principal da UI (iframe) para visualização das sessões.

    Retorna
    -------
    HTMLResponse
        HTML renderizado a partir de `ui.html`.

    Observações de segurança
    ------------------------
    Acesso restrito a superusers via dependência global do router.
    """
    html = _read_html("ui.html")
    return HTMLResponse(content=html)


@router.get("/schema")
def schema() -> Dict[str, Any]:
    """
    Retorna metadados da automação.

    Retorna
    -------
    dict
        Estrutura com `name`, `version`, `title` e rotas relevantes.
    """
    return {
        "name": KIND,
        "version": VERSION,
        "title": "Quem está online (Superuser)",
        "endpoints": ["/ui", "/online", "/stats", "/sessions/{id}/revoke"],
    }


class OnlineSession(BaseModel):
    """
    Modelo de sessão online retornado pelos endpoints JSON.

    Campos
    ------
    session_id : str
        Identificador da sessão.
    user_id : str
        Identificador do usuário.
    nome : str | None
        Nome do usuário.
    email : str | None
        E-mail do usuário.
    cpf : str | None
        CPF do usuário.
    roles : list[str]
        Papéis associados ao usuário.
    is_superuser : bool
        Indicador de privilégio elevado.
    created_at : str
        Instante de criação em ISO-Z (UTC).
    last_seen_at : str | None
        Último acesso visto em ISO-Z (UTC).
    expires_at : str
        Expiração da sessão em ISO-Z (UTC).
    ip : str | None
        Endereço IP associado.
    user_agent : str | None
        User-Agent original do login.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    session_id: str
    user_id: str
    nome: Optional[str] = None
    email: Optional[str] = None
    cpf: Optional[str] = None
    roles: List[str] = []
    is_superuser: bool = False
    created_at: str
    last_seen_at: Optional[str] = None
    expires_at: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None


@router.get("/online", response_model=List[OnlineSession])
def list_online(
    q: Optional[str] = Query(default=None, description="Filtro por nome/email/cpf/ip/user_agent"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> List[OnlineSession]:
    """
    Lista sessões ativas (não revogadas e não expiradas), com dados do usuário e seus roles.

    Parâmetros
    ----------
    q : str, opcional
        Termo de busca (nome, e-mail, CPF, IP ou user-agent).
    limit : int
        Quantidade máxima de registros (1..1000).

    Retorna
    -------
    list[OnlineSession]
        Coleção de sessões em andamento, ordenadas por atividade.

    Efeitos colaterais
    ------------------
    Consulta o banco (`auth_sessions`, `users`, `user_roles`, `roles`).

    Observações
    -----------
    - Tenta habilitar a extensão `unaccent` para buscas mais flexíveis.
    - Datas são retornadas normalizadas em UTC (ISO-Z).
    """
    where_extra = ""
    params: Dict[str, Any] = {"limit": limit}
    if q:
        where_extra = """
          AND (
            unaccent(lower(u.name)) LIKE unaccent(lower(%(q)s)) OR
            lower(u.email) LIKE lower(%(q)s) OR
            u.cpf LIKE %(qnum)s OR
            s.ip::text LIKE %(q)s OR
            lower(s.user_agent) LIKE lower(%(q)s)
          )
        """
        params["q"] = f"%{q}%"
        params["qnum"] = f"%{''.join(ch for ch in q if ch.isdigit())}%"

    sql = f"""
        SELECT
          s.id::text AS session_id,
          s.user_id::text AS user_id,
          u.name AS nome,
          u.email,
          u.cpf,
          COALESCE(u.is_superuser, FALSE) AS is_superuser,
          to_char(s.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS created_at,
          to_char(s.last_seen_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS last_seen_at,
          to_char(s.expires_at   AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS expires_at,
          s.ip::text AS ip,
          s.user_agent,
          COALESCE(roles.roles, ARRAY[]::text[]) AS roles
        FROM auth_sessions s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN LATERAL (
            SELECT array_agg(r.name ORDER BY r.name) AS roles
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = u.id
        ) roles ON TRUE
        WHERE s.revoked_at IS NULL
          AND s.expires_at > now()
          {where_extra}
        ORDER BY s.last_seen_at DESC NULLS LAST, s.created_at DESC
        LIMIT %(limit)s
    """
    with _pg() as conn, conn.cursor() as cur:
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
        except Exception:
            pass
        cur.execute(sql, params)
        rows = cur.fetchall() or []
    return [OnlineSession(**row) for row in rows]


@router.get("/stats")
def stats() -> Dict[str, Any]:
    """
    Retorna KPIs agregados das sessões ativas.

    Retorna
    -------
    dict
        Estrutura com:
        - `sessions`: total de sessões ativas
        - `users`: total de usuários distintos online
        - `by_superuser`: distribuição por privilégio elevado
        - `top_agents`: top 10 user-agents
        - `top_ips`: top 10 IPs
        - `window`: primeiro login e último seen
        - `version`: versão da automação

    Efeitos colaterais
    ------------------
    Executa múltiplas consultas de agregação no banco.
    """
    out: Dict[str, Any] = {}
    with _pg() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT count(*)::int AS c
            FROM auth_sessions s
            WHERE s.revoked_at IS NULL AND s.expires_at > now()
        """)
        out["sessions"] = (cur.fetchone() or {}).get("c", 0)

        cur.execute("""
            SELECT count(DISTINCT s.user_id)::int AS c
            FROM auth_sessions s
            WHERE s.revoked_at IS NULL AND s.expires_at > now()
        """)
        out["users"] = (cur.fetchone() or {}).get("c", 0)

        cur.execute("""
            SELECT
              COALESCE(u.is_superuser, FALSE) AS is_superuser,
              count(DISTINCT s.user_id)::int AS users
            FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.revoked_at IS NULL AND s.expires_at > now()
            GROUP BY 1
            ORDER BY 1 DESC
        """)
        out["by_superuser"] = cur.fetchall() or []

        cur.execute("""
            SELECT split_part(coalesce(s.user_agent,''), ' ', 1) AS agent, count(*)::int AS c
            FROM auth_sessions s
            WHERE s.revoked_at IS NULL AND s.expires_at > now()
            GROUP BY 1
            ORDER BY c DESC
            LIMIT 10
        """)
        out["top_agents"] = cur.fetchall() or []

        cur.execute("""
            SELECT COALESCE(s.ip::text, 'unknown') AS ip, count(*)::int AS c
            FROM auth_sessions s
            WHERE s.revoked_at IS NULL AND s.expires_at > now()
            GROUP BY 1
            ORDER BY c DESC
            LIMIT 10
        """)
        out["top_ips"] = cur.fetchall() or []

        cur.execute("""
            SELECT
              to_char(min(s.created_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS oldest_login,
              to_char(max(s.last_seen_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS latest_seen
            FROM auth_sessions s
            WHERE s.revoked_at IS NULL AND s.expires_at > now()
        """)
        out["window"] = cur.fetchone() or {}

    out["version"] = VERSION
    return out


@router.post("/sessions/{session_id}/revoke")
def revoke_session(session_id: str, request: Request) -> Response:
    """
    Revoga uma sessão específica (operação idempotente).

    Parâmetros
    ----------
    session_id : str
        Identificador da sessão a ser revogada.
    request : Request
        Requisição com usuário autenticado (para auditoria).

    Retorna
    -------
    Response
        Resposta vazia com status 204 quando executado.

    Exceções
    --------
    HTTPException
        404 quando a sessão não existe.

    Efeitos colaterais
    ------------------
    - Atualiza `auth_sessions.revoked_at` no banco.
    - Registra auditoria (`add_audit`) com o ator e o `session_id`.

    Observações de segurança
    ------------------------
    A rota herda a exigência de superuser via dependência global.
    """
    actor = _get_user(request)
    with _pg() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id, revoked_at FROM auth_sessions WHERE id = %s", (session_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="session not found")
        cur.execute(
            "UPDATE auth_sessions SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL",
            (session_id,),
        )
    try:
        add_audit(KIND, "revoke", actor, {"session_id": session_id})
    except Exception:
        pass
    return Response(status_code=204)
