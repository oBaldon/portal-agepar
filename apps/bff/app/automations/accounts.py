# apps/bff/app/automations/accounts.py
"""
Automação de Administração de Contas & Roles (RBAC) — Portal AGEPAR.

Visão geral
-----------
Esta automação expõe uma UI simples (HTML) e um conjunto de endpoints JSON para:
- Listar e gerenciar usuários (criar — legado, atualizar, excluir, alterar senha).
- Listar/criar/excluir roles do sistema e atribuí-las a usuários.

Segurança
---------
- Protegida por RBAC: apenas usuários com o papel `"admin"` podem acessar.
- Papéis "virtuais" como `is_superuser` são bloqueados para edição nos endpoints de roles.

Decisões de projeto
-------------------
- A criação de contas por esta automação é um recurso **LEGADO**. Por padrão está desativada e,
  quando habilitada por configuração, responde com *headers* de depreciação.
- Normalização de CPF e nomes de roles para garantir entradas previsíveis.
- Respostas de erro consistentes via `err_json(...)` com campos `error`, `message` e `details`.

Dependências externas
---------------------
- Banco de dados (PostgreSQL) acessado via `app.db._pg()`.
- Auditoria e submissões (`insert_submission`, `add_audit`) para rastreabilidade.
- Hash de senhas com Argon2 (`argon2-cffi`).

Endpoints principais
--------------------
GET  /api/automations/accounts/ui
GET  /api/automations/accounts/schema
GET  /api/automations/accounts/config
GET  /api/automations/accounts/users
GET  /api/automations/accounts/users/{user_id}
POST /api/automations/accounts/users                 (LEGADO; desativado por padrão)
PUT  /api/automations/accounts/users/{user_id}
DELETE /api/automations/accounts/users/{user_id}
PUT  /api/automations/accounts/users/{user_id}/password
PUT  /api/automations/accounts/users/{user_id}/roles
GET  /api/automations/accounts/roles
POST /api/automations/accounts/roles
DELETE /api/automations/accounts/roles/{role_name}
GET  /api/automations/accounts/submissions
GET  /api/automations/accounts/submissions/{submission_id}
POST /api/automations/accounts/submissions/{submission_id}/download
"""

from __future__ import annotations

import logging
import pathlib
import re
from typing import Any, Dict, List, Optional, Literal
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from argon2 import PasswordHasher

from app.db import insert_submission, get_submission, list_submissions_admin, add_audit, _pg  # type: ignore
from app.auth.rbac import require_roles_any

logger = logging.getLogger(__name__)

ACCOUNTS_MAX_LIST = int(os.getenv("ACCOUNTS_MAX_LIST", "5000"))

REQUIRED_ROLES = ("admin",)
BLOCKED_ROLES = {"is_superuser"}

TPL_DIR = pathlib.Path(__file__).resolve().parent / "templates" / "accounts"

router = APIRouter(
    prefix="/api/automations/accounts",
    tags=["automations:accounts"],
    dependencies=[Depends(require_roles_any(*REQUIRED_ROLES))],
)

hasher = PasswordHasher()

LEGACY_CREATE_ENABLED = (os.getenv("ACCOUNTS_CREATE_LEGACY_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"})
LEGACY_CREATE_SINCE = "2025-10-20"


def _legacy_gone(message: str = "A criação de contas via automação 'accounts' é LEGADO e foi desativada."):
    """
    Constrói uma resposta 410 (Gone) padronizada para o fluxo LEGADO de criação de contas.

    Parâmetros
    ----------
    message : str
        Mensagem amigável informando a descontinuação.

    Retorna
    -------
    JSONResponse
        Resposta com *headers* de depreciação e *payload* contendo dica de ação alternativa.
    """
    return JSONResponse(
        status_code=410,
        content={
            "error": "deprecated",
            "message": message,
            "hint": "Use o provedor de identidade oficial (OIDC/SSO) ou peça a um administrador para criar a conta pelo fluxo suportado.",
            "since": LEGACY_CREATE_SINCE,
            "action": "create_user",
        },
        headers={
            "Deprecation": "true",
            "X-Deprecated": "accounts.create_user",
        },
    )


def _with_deprecation_headers(payload: Dict[str, Any]) -> JSONResponse:
    """
    Anexa *headers* de depreciação a uma resposta JSON.

    Parâmetros
    ----------
    payload : Dict[str, Any]
        Corpo da resposta.

    Retorna
    -------
    JSONResponse
        Resposta JSON com *headers* `Deprecation` e `X-Deprecated`.
    """
    resp = JSONResponse(content=payload)
    resp.headers["Deprecation"] = "true"
    resp.headers["X-Deprecated"] = "accounts.create_user"
    return resp


CPF_RE = re.compile(r"\D+")
ROLE_OK_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{1,99}$")


def norm_cpf(v: Optional[str]) -> Optional[str]:
    """
    Normaliza um CPF removendo caracteres não numéricos e validando seu comprimento.

    Parâmetros
    ----------
    v : Optional[str]
        Valor bruto informado pelo cliente.

    Retorna
    -------
    Optional[str]
        CPF com 11 dígitos, ou None quando vazio após normalização.

    Levanta
    -------
    HTTPException
        422 se o valor informado não possuir exatamente 11 dígitos numéricos.
    """
    if v is None:
        return None
    v = CPF_RE.sub("", v or "")
    if v == "":
        return None
    if len(v) != 11 or not v.isdigit():
        raise HTTPException(status_code=422, detail="CPF deve conter 11 dígitos numéricos.")
    return v


def safe_digits(s: str) -> str:
    """
    Remove todos os caracteres não numéricos de uma string.

    Parâmetros
    ----------
    s : str
        Texto de entrada.

    Retorna
    -------
    str
        Texto contendo apenas dígitos.
    """
    return CPF_RE.sub("", s or "")


def clamp(n: int, lo: int, hi: int) -> int:
    """
    Restringe um inteiro a um intervalo [lo, hi].

    Parâmetros
    ----------
    n : int
        Valor alvo.
    lo : int
        Limite inferior.
    hi : int
        Limite superior.

    Retorna
    -------
    int
        Valor ajustado dentro do intervalo.
    """
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
    """
    Constrói uma resposta JSON de erro consistente.

    Parâmetros
    ----------
    status : int
        Código HTTP.
    code : str
        Código curto do erro.
    message : str
        Mensagem amigável.
    details : Any, opcional
        Detalhes para depuração ou UI.
    hint : Optional[str], opcional
        Sugestão de correção.
    received : Any, opcional
        *Echo* do que foi recebido, quando útil.

    Retorna
    -------
    JSONResponse
        Resposta pronta para retorno em endpoints.
    """
    content: Dict[str, Any] = {"error": code, "message": message}
    if details is not None:
        content["details"] = details
    if hint is not None:
        content["hint"] = hint
    if received is not None:
        content["received"] = received
    return JSONResponse(status_code=status, content=content)


def _read_html(name: str) -> str:
    """
    Carrega um arquivo HTML do diretório de templates da automação.

    Parâmetros
    ----------
    name : str
        Nome do arquivo dentro de `TPL_DIR`.

    Retorna
    -------
    str
        Conteúdo HTML.
    """
    path = TPL_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def is_last_admin(cur, user_id: str) -> bool:
    """
    Verifica se o sistema ficaria sem administradores ao remover `admin` do usuário alvo.

    Parâmetros
    ----------
    cur : psycopg.Cursor
        Cursor com *row factory* de dict.
    user_id : str
        Identificador do usuário alvo.

    Retorna
    -------
    bool
        True se a remoção deixaria o sistema sem nenhum `admin`.
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
    Normaliza uma lista de roles:
    - Remove vazios e espaços, força `lower()`.
    - Filtra nomes inválidos e bloqueados.
    - Remove duplicados.

    Parâmetros
    ----------
    input_roles : List[str]
        Lista bruta de papéis.

    Retorna
    -------
    List[str]
        Lista normalizada e ordenada.
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


def _env_default_roles() -> List[str]:
    """
    Obtém roles padrão do ambiente (`AUTH_DEFAULT_ROLES`) já normalizadas.

    Retorna
    -------
    List[str]
        Lista de roles herdadas do ambiente.
    """
    raw = (os.getenv("AUTH_DEFAULT_ROLES") or "").split(",")
    return normalize_roles([r for r in raw if isinstance(r, str)])


class UserOut(BaseModel):
    """
    Representação de um usuário para retorno na API.

    Campos
    ------
    id : str
    cpf : Optional[str]
    email : Optional[EmailStr]
    name : str
    status : Optional[str]
    is_superuser : bool
    created_at : Optional[str]
    updated_at : Optional[str]
    roles : List[str]
    """
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
    """
    Entrada para criação de usuário (LEGADO).

    Campos
    ------
    name : str
    email : Optional[EmailStr]
    cpf : Optional[str]
    password : str
    roles : List[str]
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    name: str = Field(min_length=2, max_length=200)
    email: Optional[EmailStr] = None
    cpf: Optional[str] = None
    password: str = Field(min_length=8, max_length=128)
    roles: List[str] = []

    def normalize(self):
        """
        Normaliza CPF e valida que ao menos e-mail ou CPF foi informado.

        Levanta
        -------
        HTTPException
            422 quando CPF inválido ou ambos e-mail/CPF ausentes.
        """
        self.cpf = norm_cpf(self.cpf)
        if not self.email and not self.cpf:
            raise HTTPException(status_code=422, detail="Informe e-mail ou CPF.")


class UpdateUserIn(BaseModel):
    """
    Entrada para atualização de um usuário.

    Campos
    ------
    name : Optional[str]
    email : Optional[EmailStr]
    cpf : Optional[str]
    status : Optional[Literal['active','blocked','pending']]
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    email: Optional[EmailStr] = None
    cpf: Optional[str] = None
    status: Optional[Literal["active", "blocked", "pending"]] = None

    def normalize(self):
        """
        Normaliza CPF quando fornecido.
        """
        self.cpf = norm_cpf(self.cpf) if self.cpf is not None else None


class SetPasswordIn(BaseModel):
    """
    Entrada para definição de nova senha do usuário (administração).

    Campos
    ------
    password : str
        Nova senha em texto claro; será hasheada com Argon2.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    password: str = Field(min_length=8, max_length=128)


class RoleIn(BaseModel):
    """
    Entrada para criação de role do sistema.

    Campos
    ------
    name : str
        Nome do role (min 2, máx 100; aceita caracteres `[a-z0-9_.:-]`).
    description : Optional[str]
        Descrição opcional.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None


@router.get("/ui")
def ui() -> HTMLResponse:
    """
    Retorna a UI HTML estática da automação de contas.

    Retorna
    -------
    HTMLResponse
        Documento HTML renderizado pelo navegador.
    """
    html = _read_html("ui.html")
    return HTMLResponse(content=html)


@router.get("/schema")
def schema() -> Dict[str, Any]:
    """
    Expõe metadados da automação para consumo por outras partes do sistema.

    Retorna
    -------
    Dict[str, Any]
        Estrutura com nome, versão e ações suportadas, incluindo marcação deprecatória do fluxo legado.
    """
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
        "deprecated_actions": {
            "create_user": {
                "since": LEGACY_CREATE_SINCE,
                "enabled": LEGACY_CREATE_ENABLED,
            }
        },
        "notes": "Administração de contas e papéis (roles). Somente admins. A criação de contas é LEGADO.",
    }
    

@router.get("/config")
def config() -> Dict[str, Any]:
    """
    Retorna configurações relevantes à UI:
    - `default_roles`: papéis herdados do ambiente (somente leitura).
    - `legacy.create_user`: status do modo legado de criação de contas.

    Retorna
    -------
    Dict[str, Any]
    """
    return {
        "auth_mode": os.getenv("AUTH_MODE", "local"),
        "default_roles": _env_default_roles(),
        "legacy": {
            "create_user": {
                "since": LEGACY_CREATE_SINCE,
                "enabled": LEGACY_CREATE_ENABLED,
            }
        },
    }


@router.get("/users")
def list_users(
    q: Optional[str] = Query(default=None),
    limit: int = 5000,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Lista usuários com filtros opcionais por nome, e-mail ou CPF.

    Parâmetros
    ----------
    q : Optional[str]
        Texto de busca; se contiver 11 dígitos, filtra por CPF, caso contrário por nome/e-mail.
    limit : int
        Limite de registros (clamp ao máximo configurado).
    offset : int
        Deslocamento inicial.

    Retorna
    -------
    Dict[str, Any]
        `items`: lista de usuários; `count`: total retornado.
    """
    limit = clamp(limit, 1, ACCOUNTS_MAX_LIST)
    offset = max(0, offset)

    wheres = ["1=1"]
    params: List[Any] = []
    if q:
        only = safe_digits(q)
        if len(only) == 11:
            wheres.append("u.cpf = %s")
            params.append(only)
        else:
            wheres.append("(u.name ILIKE %s OR email ILIKE %s)")
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
      ORDER BY u.name ASC NULLS LAST
      LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() or []
        items = []
        env_defaults = _env_default_roles()
        for row in rows:
            d = dict(row)
            d["roles"] = list(d.get("roles") or [])
            d["roles_env"] = env_defaults
            d["roles_effective"] = sorted(set(d["roles"]) | set(env_defaults))
            items.append(d)
        return {"items": items, "count": len(items)}


@router.get("/users/{user_id}")
def get_user(user_id: str) -> Dict[str, Any]:
    """
    Obtém um usuário por ID com suas roles atribuídas e herdadas do ambiente.

    Parâmetros
    ----------
    user_id : str

    Retorna
    -------
    Dict[str, Any]

    Levanta
    -------
    HTTPException
        404 quando o usuário não for encontrado.
    """
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
        env_defaults = _env_default_roles()
        d["roles_env"] = env_defaults
        d["roles_effective"] = sorted(set(d["roles"]) | set(env_defaults))
        return d


@router.post("/users")
def create_user(payload: CreateUserIn, request: Request):
    """
    Cria usuário (fluxo LEGADO). Desativado por padrão; quando desativado retorna 410.

    Parâmetros
    ----------
    payload : CreateUserIn
    request : Request

    Retorna
    -------
    JSONResponse | Dict[str, Any]
        410 (Gone) quando desativado; quando ativo, objeto com `ok=True` e `user_id`.
    """
    if not LEGACY_CREATE_ENABLED:
        return _legacy_gone()

    try:
        payload.normalize()
    except HTTPException as e:
        raise e
    except Exception as e:
        return err_json(422, code="validation_error", message=str(e))

    with _pg() as conn, conn.cursor() as cur:
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
        user_id = row.get("id")
        if not user_id:
            raise HTTPException(status_code=500, detail="Falha ao criar usuário (sem id).")

        roles = normalize_roles(payload.roles or [])
        if roles:
            cur.execute("SELECT name FROM roles WHERE name = ANY(%s)", (roles,))
            existing_names = {r["name"] for r in (cur.fetchall() or [])}
            to_create = [r for r in roles if r not in existing_names]
            for r in to_create:
                cur.execute(
                    "INSERT INTO roles (name, description) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
                    (r, None),
                )
            cur.execute("SELECT id, name FROM roles WHERE name = ANY(%s)", (roles,))
            role_map = {row["name"]: row["id"] for row in (cur.fetchall() or [])}
            for r in roles:
                rid = role_map.get(r)
                if rid:
                    cur.execute(
                        "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (user_id, rid),
                    )

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
                    "deprecated": True,
                    "since": LEGACY_CREATE_SINCE,
                },
                "status": "done",
                "result": {"user_id": user_id},
                "error": None,
            }
        )
        add_audit("accounts", "create_user", actor, {"user_id": user_id, "roles": roles, "deprecated": True})
        return _with_deprecation_headers({"ok": True, "user_id": user_id})


@router.put("/users/{user_id}")
def update_user(user_id: str, payload: UpdateUserIn, request: Request):
    """
    Atualiza campos do usuário alvo.

    Parâmetros
    ----------
    user_id : str
    payload : UpdateUserIn
    request : Request

    Retorna
    -------
    Dict[str, Any]
        `{"ok": True}` mesmo quando nenhum campo foi enviado.

    Erros
    -----
    - 409: conflito de e-mail/CPF com outro usuário.
    - 404: usuário não encontrado no momento da escrita (raro).
    """
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
    Exclui um usuário com validações de segurança:
    - Impede autoexclusão.
    - Impede exclusão do último administrador.
    - Ajusta dependências para preservar histórico e evitar violações de integridade.

    Parâmetros
    ----------
    user_id : str
    request : Request

    Retorna
    -------
    Dict[str, Any]
        `{"ok": True}` em caso de sucesso.

    Erros
    -----
    - 400: autoexclusão ou tentativa de remover o último admin.
    - 404: usuário não encontrado.
    """
    actor = request.session.get("user") or {}
    if str(actor.get("id") or actor.get("user_id") or "") == user_id:
        raise HTTPException(status_code=400, detail="Você não pode excluir sua própria conta.")

    with _pg() as conn, conn.cursor() as cur:
        if is_last_admin(cur, user_id):
            raise HTTPException(status_code=400, detail="Não é possível excluir o último administrador.")

        try:
            cur.execute("DELETE FROM login_attempts WHERE user_id = %s", (user_id,))
        except Exception:
            logger.exception("Falha ao remover login_attempts (não bloqueante)")

        try:
            cur.execute("UPDATE audit_events SET actor_user_id = NULL WHERE actor_user_id = %s", (user_id,))
        except Exception:
            logger.exception("Falha ao desvincular audit_events (não bloqueante)")

        cur.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

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
    """
    Define uma nova senha para o usuário alvo.

    Parâmetros
    ----------
    user_id : str
    payload : SetPasswordIn
    request : Request

    Retorna
    -------
    Dict[str, Any]
        `{"ok": True}` em caso de sucesso.

    Erros
    -----
    - 404: usuário não encontrado.
    """
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
    """
    Define o conjunto completo de roles de um usuário, substituindo os vínculos existentes.

    Regras de segurança
    -------------------
    - Impede que o próprio usuário remova seu `admin` se já o possuir.
    - Impede que o sistema fique sem administradores.

    Parâmetros
    ----------
    user_id : str
    body : Dict[str, Any]
        Estrutura com `roles: List[str]`.
    request : Request

    Retorna
    -------
    Dict[str, Any]
        Estrutura com `ok` e `roles` efetivos.

    Erros
    -----
    - 404: usuário inexistente.
    - 400: violação de regras (auto-remoção do `admin` ou último admin).
    """
    roles = normalize_roles([r for r in (body.get("roles") or []) if isinstance(r, str)])
    actor = request.session.get("user") or {}

    with _pg() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

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

        if "admin" not in roles and is_last_admin(cur, user_id):
            raise HTTPException(status_code=400, detail="O sistema deve manter ao menos um administrador.")

        if roles:
            cur.execute("SELECT name FROM roles WHERE name = ANY(%s)", (roles,))
            existing_names = {r["name"] for r in (cur.fetchall() or [])}
            to_create = [r for r in roles if r not in existing_names]
            for r in to_create:
                cur.execute(
                    "INSERT INTO roles (name, description) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
                    (r, None),
                )

        role_map: Dict[str, Any] = {}
        if roles:
            cur.execute("SELECT id, name FROM roles WHERE name = ANY(%s)", (roles,))
            role_map = {row["name"]: row["id"] for row in (cur.fetchall() or [])}

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


@router.get("/roles")
def list_roles() -> Dict[str, Any]:
    """
    Lista todos os roles do sistema.

    Retorna
    -------
    Dict[str, Any]
        `items`: lista de roles; `count`: total.
    """
    with _pg() as conn, conn.cursor() as cur:
        cur.execute("SELECT id::text, name, description, created_at FROM roles ORDER BY name ASC")
        rows = [dict(r) for r in (cur.fetchall() or [])]
        return {"items": rows, "count": len(rows)}


@router.post("/roles")
def create_role(payload: RoleIn, request: Request):
    """
    Cria um novo role do sistema.

    Parâmetros
    ----------
    payload : RoleIn
    request : Request

    Retorna
    -------
    Dict[str, Any]
        `{"ok": True, "role_id": "<id>"}`

    Erros
    -----
    - 400: nome reservado (`is_superuser`) ou inválido.
    - 409: conflito de unicidade.
    """
    name_norm = (payload.name or "").strip().lower()
    if name_norm in BLOCKED_ROLES:
        raise HTTPException(status_code=400, detail="Role reservado.")
    if not ROLE_OK_RE.match(name_norm):
        raise HTTPException(status_code=422, detail="Nome do role inválido (use letras/números/._:-).")

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
    """
    Remove um role do sistema, desvinculando-o dos usuários.

    Parâmetros
    ----------
    role_name : str
    request : Request

    Retorna
    -------
    Dict[str, Any]
        `{"ok": True}`

    Erros
    -----
    - 400: role reservado ou `admin`.
    - 404: role inexistente.
    """
    role_name = (role_name or "").strip().lower()
    if role_name in BLOCKED_ROLES:
        raise HTTPException(status_code=400, detail="Role reservado.")
    if role_name == "admin":
        raise HTTPException(status_code=400, detail="Não é permitido remover o role 'admin'.")

    with _pg() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM roles WHERE name = %s", (role_name,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Role não encontrada.")
        role_id = row["id"]

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


@router.get("/submissions")
def submissions(limit: int = 5000, offset: int = 0) -> Dict[str, Any]:
    """
    Lista submissões registradas pela automação para auditoria/observabilidade.

    Parâmetros
    ----------
    limit : int
    offset : int

    Retorna
    -------
    Dict[str, Any]
        Estrutura `{ "items": [...]}`
    """
    limit = clamp(limit, 1, ACCOUNTS_MAX_LIST)
    offset = max(0, offset)
    return {"items": list_submissions_admin(kind="accounts", limit=limit, offset=offset)}


@router.get("/submissions/{submission_id}")
def get_sub(submission_id: str) -> Dict[str, Any]:
    """
    Obtém uma submissão específica por ID.

    Parâmetros
    ----------
    submission_id : str

    Retorna
    -------
    Dict[str, Any]

    Levanta
    -------
    HTTPException
        404 quando a submissão não pertence à automação `accounts` ou não existe.
    """
    sub = get_submission(submission_id)
    if not sub or sub.get("kind") != "accounts":
        raise HTTPException(status_code=404, detail="submission not found")
    return sub


@router.post("/submissions/{submission_id}/download")
def download(_submission_id: str):
    """
    Ponto de compatibilidade para *downloads* desta automação.

    Notas
    -----
    Esta automação não gera artefatos para download.

    Levanta
    -------
    HTTPException
        404 invariavelmente.
    """
    raise HTTPException(status_code=404, detail="sem artefatos para download nesta automação")
