# apps/bff/app/main.py
from __future__ import annotations

"""
BFF (Backend for Frontend) da Plataforma AGEPAR.

Propósito
---------
- Centralizar middlewares, autenticação de sessão e CORS.
- Expor rotas de infraestrutura (/health, /version, /api/me, /catalog/dev).
- Agregar e publicar os routers de automações sob /api/automations/*.
- Inicializar o schema Postgres utilizado pelas automações (submissions/audits/fileshare).

Referências
-----------
- FastAPI: https://fastapi.tiangolo.com/
- Starlette Sessions: https://www.starlette.io/middleware/#sessionsmiddleware
- CORS (FastAPI/Starlette): https://fastapi.tiangolo.com/tutorial/cors/
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import psycopg
from fastapi import FastAPI, Request, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

from app.automations.dfd import AUTOMATION_META as DFD_META, DFD_VERSION as DFD_VER, router as dfd_router
from app.automations.etp import AUTOMATION_META as ETP_META, ETP_VERSION as ETP_VER, router as etp_router
from app.automations.ferias import AUTOMATION_META as FERIAS_META, FERIAS_VERSION as FERIAS_VER, router as ferias_router
from app.automations.ponto_saldo import AUTOMATION_META as PONTO_SALDO_META, PONTO_SALDO_VERSION as PONTO_SALDO_VER, router as ponto_saldo_router
from app.db import init_db, DATABASE_URL
from app.automations.profile import AUTOMATION_META as PROFILE_META, PROFILE_VERSION as PROFILE_VER, router as profile_router
from app.automations.form2json import AUTOMATION_META as FORM2JSON_META, FORM2JSON_VERSION as FORM2JSON_VER, router as form2json_router
from app.automations.controle import AUTOMATION_META as CONTROLE_META, CONTROLE_VERSION as CONTROLE_VER, router as controle_router
from app.automations.controle_ferias import router as controle_ferias_router
from app.automations.controle_tasks import router as controle_tasks_router
from app.automations.accounts import AUTOMATION_META as ACCOUNTS_META, ACCOUNTS_VERSION as ACCOUNTS_VER, router as accounts_router
from app.automations.fileshare import AUTOMATION_META as FILESHARE_META, FILESHARE_VERSION as FILESHARE_VER, router as fileshare_router
from app.automations.whoisonline import AUTOMATION_META as WHOISONLINE_META, VERSION as WHOISONLINE_VER, router as whoisonline_router
from app.automations.tasks import AUTOMATION_META as TASKS_META, TASKS_VERSION as TASKS_VER, router as tasks_router
from app.automations.support import AUTOMATION_META as SUPPORT_META, SUPPORT_VERSION as SUPPORT_VER, router as support_router
from app.automations.usuarios import AUTOMATION_META as USUARIOS_META, USUARIOS_VERSION as USUARIOS_VER, router as usuarios_router
from app.automations.avisos import AUTOMATION_META as AVISOS_META, AVISOS_VERSION as AVISOS_VER, router as avisos_router
from app.notifications import router as notifications_router
from app.automations.task_weekly_email import start_weekly_task_email_scheduler
from app.games.snake import router as snake_router
from app.auth.routes import router as auth_router
from app.auth.middleware import DbSessionMiddleware
from app.auth.sessions import router as auth_sessions_router
from app.auth.rbac import require_password_changed
from app.auth.vacation_balance import (
    ensure_user_vacation_columns,
    ensure_vacation_balance,
    current_year,
)

ENV = os.getenv("ENV", "dev")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
AUTH_MODE = os.getenv("AUTH_MODE", "local")
AUTH_LEGACY_MOCK = os.getenv("AUTH_LEGACY_MOCK", "0").lower() in ("1", "true", "yes")
EP_MODE = os.getenv("EP_MODE", "mock")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
CATALOG_FILE = Path(os.getenv("CATALOG_FILE", "/catalog/catalog.dev.json"))
OIDC_ISSUER = os.getenv("OIDC_ISSUER", "")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
OIDC_JWKS_URL = os.getenv("OIDC_JWKS_URL", "")

def _auth_default_roles() -> list[str]:
    """
    Lê roles padrão para sessões mock a partir de AUTH_DEFAULT_ROLES.

    Retorna
    -------
    list[str]
        Lista de roles não vazias (limpas por strip()).
    """
    return [r.strip() for r in os.getenv("AUTH_DEFAULT_ROLES", "").split(",") if r.strip()]

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)
logger.info(
    "Starting BFF (ENV=%s, AUTH_MODE=%s, LEGACY_MOCK=%s, LOG_LEVEL=%s, EP_MODE=%s)",
    ENV, AUTH_MODE, AUTH_LEGACY_MOCK, LOG_LEVEL, EP_MODE
)
logger.info("CORS_ORIGINS=%s | CATALOG_FILE=%s", ",".join(CORS_ORIGINS), str(CATALOG_FILE))


AUTOMATIONS_INDEX_ITEMS = [
    dict(FORM2JSON_META),
    dict(PROFILE_META),
    dict(ETP_META),
    dict(DFD_META),
    dict(FERIAS_META),
    dict(CONTROLE_META),
    dict(FILESHARE_META),
    dict(SUPPORT_META),
    dict(PONTO_SALDO_META),
    dict(ACCOUNTS_META),
    dict(AVISOS_META),
    dict(TASKS_META),
    dict(WHOISONLINE_META),
    dict(USUARIOS_META),
]
AUTOMATION_META_BY_KIND = {
    item["kind"]: dict(item) for item in AUTOMATIONS_INDEX_ITEMS
}
AUTOMATION_VERSION_BY_KIND = {
    kind: meta["version"] for kind, meta in AUTOMATION_META_BY_KIND.items()
}


APP = FastAPI(title="Portal AGEPAR BFF", version="0.3.0", docs_url="/api/docs", redoc_url="/api/redoc")

APP.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

APP.add_middleware(DbSessionMiddleware)
APP.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=False,
    session_cookie="portal_agepar_session",
)

APP.include_router(snake_router)
APP.include_router(auth_router)
APP.include_router(auth_sessions_router)

@APP.on_event("startup")
def _startup() -> None:
    """
    Hook de inicialização do aplicativo.

    Efeitos colaterais
    ------------------
    - Executa `init_db()` para garantir o schema Postgres.
    - Loga versões dos motores DFD e FÉRIAS.
    """
    init_db()
    logger.info("DB initialized (Postgres)")
    try:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL não configurada")
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
            ensure_user_vacation_columns(conn)
        logger.info("Users vacation columns ensured (saldo_ferias/saldo_ferias_ano)")
    except Exception as e:
        logger.error("Failed ensuring users vacation columns: %s", e)
        raise
    logger.info("DFD engine version: %s", DFD_VER)
    logger.info("FERIAS engine version: %s", FERIAS_VER)
    logger.info("PONTO_SALDO engine version: %s", PONTO_SALDO_VER)
    logger.info("ETP engine version: %s", ETP_VER)
    logger.info("TASKS engine version: %s", TASKS_VER)
    logger.info("AVISOS engine version: %s", AVISOS_VER)
    _validate_catalog_metadata_consistency()
    start_weekly_task_email_scheduler()


def _sync_catalog_block_metadata(block: Dict[str, Any]) -> None:
    kind = block.get("name")
    if not isinstance(kind, str):
        return

    meta = AUTOMATION_META_BY_KIND.get(kind)
    if not meta:
        return

    block["version"] = meta["version"]
    block["title"] = meta["title"]
    if not block.get("displayName"):
        block["displayName"] = meta["title"]

    for key in ("readOnly", "superuserOnly"):
        if key in meta:
            block[key] = meta[key]


def _validate_catalog_metadata_consistency() -> None:
    if not CATALOG_FILE.exists():
        logger.warning("Catalog consistency check skipped: file not found (%s)", CATALOG_FILE)
        return

    try:
        data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Catalog consistency check skipped: failed to read %s", exc)
        return

    blocks = data.get("blocks", [])
    if not isinstance(blocks, list):
        logger.warning("Catalog consistency check skipped: blocks is not a list")
        return

    catalog_by_kind: Dict[str, Dict[str, Any]] = {}
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = block.get("name")
        ui = block.get("ui") or {}
        url = ui.get("url") if isinstance(ui, dict) else None
        if not isinstance(kind, str) or not isinstance(url, str):
            continue
        if not url.startswith("/api/automations/"):
            continue
        catalog_by_kind[kind] = block

    catalog_kinds = set(catalog_by_kind)
    published_kinds = {
        kind
        for kind, meta in AUTOMATION_META_BY_KIND.items()
        if meta.get("catalogPublished", True)
    }

    for kind in sorted(catalog_kinds - published_kinds):
        logger.warning("Catalog block '%s' points to /api/automations but is not published in /api/automations", kind)

    for kind in sorted(published_kinds - catalog_kinds):
        logger.warning("Published automation '%s' is missing from catalog/dev", kind)

    for kind in sorted(catalog_kinds & published_kinds):
        block = catalog_by_kind[kind]
        meta = AUTOMATION_META_BY_KIND[kind]

        if block.get("version") != meta["version"]:
            logger.warning(
                "Catalog version mismatch for '%s': catalog=%s module=%s",
                kind,
                block.get("version"),
                meta["version"],
            )

        display_name = block.get("displayName")
        if isinstance(display_name, str) and display_name != meta["title"]:
            logger.warning(
                "Catalog title mismatch for '%s': displayName=%s module_title=%s",
                kind,
                display_name,
                meta["title"],
            )

        for key in ("readOnly", "superuserOnly"):
            if key in meta and block.get(key) != meta[key]:
                logger.warning(
                    "Catalog flag mismatch for '%s': %s catalog=%s module=%s",
                    kind,
                    key,
                    block.get(key),
                    meta[key],
                )

        navigation = block.get("navigation")
        if isinstance(navigation, list):
            for idx, item in enumerate(navigation):
                if isinstance(item, dict) and "href" in item and "path" not in item:
                    logger.warning(
                        "Catalog navigation mismatch for '%s' item[%s]: uses 'href' instead of 'path'",
                        kind,
                        idx,
                    )

def _get_user_from_session(req: Request) -> Optional[Dict[str, Any]]:
    """
    Recupera o usuário (dict) da sessão HTTP.

    Parâmetros
    ----------
    req : Request
        Requisição atual.

    Retorna
    -------
    dict | None
        Usuário em sessão ou None se não autenticado.
    """
    return req.session.get("user")

def _require_user(req: Request) -> Dict[str, Any]:
    """
    Exige usuário autenticado na sessão.

    Parâmetros
    ----------
    req : Request

    Retorna
    -------
    dict
        Usuário autenticado.

    Exceções
    --------
    HTTPException
        401 se não autenticado.
    """
    u = _get_user_from_session(req)
    if not u:
        raise HTTPException(status_code=401, detail="not authenticated")
    return u

@APP.get("/health")
def health() -> Dict[str, str]:
    """
    Endpoint de saúde do serviço.

    Retorna
    -------
    dict
        {"status": "ok"}
    """
    return {"status": "ok"}

@APP.get("/version")
def version() -> Dict[str, Any]:
    """
    Versões e parâmetros relevantes do runtime.

    Retorna
    -------
    dict
        Metadados de versão, ambiente e configurações principais.
    """
    return {
        "app": APP.version,
        "env": ENV,
        "dfd_version": DFD_VER,
        "ferias_version": FERIAS_VER,
        "etp_version": ETP_VER,
        "tasks_version": TASKS_VER,
        "auth_mode": AUTH_MODE,
        "auth_legacy_mock": AUTH_LEGACY_MOCK,
        "ep_mode": EP_MODE,
        "cors_origins": CORS_ORIGINS,
        "catalog_file": str(CATALOG_FILE),
    }

if AUTH_LEGACY_MOCK:
    @APP.get("/api/auth/login")
    def legacy_mock_login(
        request: Request,
        cpf: Optional[str] = Query(None),
        nome: Optional[str] = Query(None),
        email: Optional[str] = Query(None),
        roles: Optional[str] = Query(None),
        unidades: Optional[str] = Query(None),
        superuser: Optional[bool] = Query(False),
    ) -> Dict[str, Any]:
        """
        [LEGADO/DEV] Cria sessão mock a partir de query params.
        Exposto somente quando AUTH_LEGACY_MOCK=1.

        Regras
        ------
        - Mescla `roles` com `AUTH_DEFAULT_ROLES`.
        - Se `superuser` verdadeiro, inclui 'admin' quando ausente.

        Retorna
        -------
        dict
            Usuário criado e persistido em `request.session["user"]`.
        """
        roles_csv = [r.strip() for r in (roles or "user").split(",") if r.strip()]
        roles_merged = sorted(set(roles_csv + _auth_default_roles()))
        if superuser and "admin" not in roles_merged:
            roles_merged = sorted(set(roles_merged + ["admin"]))

        user = {
            "cpf": cpf or "00000000000",
            "nome": nome or "Usuário de Teste",
            "email": email or "teste@example.com",
            "roles": roles_merged,
            "unidades": [u.strip() for u in (unidades or "AGEPAR").split(",") if u.strip()],
            "auth_mode": "mock",
            "is_superuser": bool(superuser),
            # saldo_ferias será normalizado também em /api/me; aqui já setamos default simples
            "saldo_ferias": 30,
            "saldo_ferias_ano": current_year(),
        }

        # Se CPF/e-mail existirem no BD, vincula a sessão mock ao usuário real
        # e puxa o saldo real (evita sempre cair em 30).
        try:
            if DATABASE_URL:
                with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
                    with conn.cursor() as cur:
                        uid = None
                        em = (user.get("email") or "").strip().lower() or None
                        cp = (user.get("cpf") or "").strip() or None
                        if em:
                            cur.execute("SELECT id FROM users WHERE email = %s", (em,))
                            r = cur.fetchone()
                            uid = r[0] if r else None
                        if (not uid) and cp:
                            cur.execute("SELECT id FROM users WHERE cpf = %s", (cp,))
                            r = cur.fetchone()
                            uid = r[0] if r else None
                        if uid:
                            uid_s = str(uid)
                            user["id"] = uid_s
                            user["saldo_ferias"] = int(ensure_vacation_balance(conn, uid_s))
        except Exception as e:
            logger.warning("[LEGACY_MOCK] failed to bind session to DB user: %s", e)

        request.session["user"] = user
        logger.info("[LEGACY_MOCK] Sessão criada para %s (roles=%s)", user["nome"], ",".join(user["roles"]))
        return user

@APP.get("/api/me")
def get_me(request: Request) -> Dict[str, Any]:
    """
    Retorna o usuário autenticado na sessão.

    Exceções
    --------
    HTTPException
        401 se não autenticado.
    """
    user = _get_user_from_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    # --- Modo MOCK (sem user_id em banco): normaliza em memória ---
    if (user.get("auth_mode") == "mock") and not user.get("id"):
        y = current_year()
        saldo = user.get("saldo_ferias")
        ano = user.get("saldo_ferias_ano")

        if not isinstance(saldo, int):
            saldo = 30
        if not isinstance(ano, int):
            ano = y

        if ano < y:
            saldo = int(saldo) + (30 * (y - int(ano)))
            ano = y

        user["saldo_ferias"] = int(saldo)
        user["saldo_ferias_ano"] = int(ano)
        request.session["user"] = user
        return user

    # --- Modo REAL (local/oidc): garante saldo no banco e espelha na sessão ---
    user_id = user.get("id")

    # Fallback: se o user payload não tiver id, tenta recuperar via auth_sessions
    if not user_id:
        db_sess_id = None
        try:
            db_sess_id = request.session.get("db_session_id")
        except Exception:
            db_sess_id = None

        if db_sess_id and DATABASE_URL:
            try:
                with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT user_id
                            FROM auth_sessions
                            WHERE id = %s::uuid
                              AND revoked_at IS NULL
                              AND expires_at > now()
                            """,
                            (str(db_sess_id),),
                        )
                        row = cur.fetchone()
                        if row and row[0]:
                            user_id = str(row[0])
            except Exception as e:
                logger.error("Failed resolving user_id from auth_sessions: %s", e)
 
    # Fallback extra: tenta resolver pelo CPF/e-mail (útil se db_session_id estiver ausente
    # ou se o payload de sessão não estiver com id ainda).
    if not user_id and DATABASE_URL:
        try:
            cpf = (user.get("cpf") or "").strip() or None
            email = (user.get("email") or "").strip().lower() or None
            if cpf or email:
                with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
                    with conn.cursor() as cur:
                        if email:
                            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
                            row = cur.fetchone()
                            if row and row[0]:
                                user_id = str(row[0])
                        if (not user_id) and cpf:
                            cur.execute("SELECT id FROM users WHERE cpf = %s", (cpf,))
                            row = cur.fetchone()
                            if row and row[0]:
                                user_id = str(row[0])
            if user_id:
                user["id"] = user_id
        except Exception as e:
            logger.error("Failed resolving user_id from users by cpf/email: %s", e)

    # Se ainda não conseguimos user_id, devolve o payload como está (sem quebrar)
    if not user_id:
        return user

    try:
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
            saldo = ensure_vacation_balance(conn, user_id)
        user["saldo_ferias"] = int(saldo)
        # Garante que o id fique gravado na sessão para próximas chamadas
        if not user.get("id"):
            user["id"] = str(user_id)
        request.session["user"] = user
    except Exception as e:
        # Não derruba /api/me por causa de saldo; apenas loga e devolve sessão atual
        logger.error("Failed ensuring vacation balance for user_id=%s: %s", user_id, e)
    return user

@APP.get("/catalog/dev")
def catalog_dev() -> Any:
    """
    Carrega o catálogo JSON de automações utilizado em DEV.

    Retorna
    -------
    Any
        Conteúdo do arquivo JSON definido por `CATALOG_FILE`.

    Exceções
    --------
    HTTPException
        404 se arquivo não existir; 500 em falha de leitura/parse.
    """
    if not CATALOG_FILE.exists():
        raise HTTPException(status_code=404, detail="catalog file not found")
    try:
        data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to read catalog: {e}")

    for block in data.get("blocks", []):
        if not isinstance(block, dict):
            continue
        _sync_catalog_block_metadata(block)

    return JSONResponse(data)

@APP.get("/api/eprotocolo/ping")
def ep_ping(request: Request) -> Dict[str, Any]:
    """
    Ping do eProtocolo (mock/real, conforme EP_MODE).

    Retorna
    -------
    dict
        { actor, ep_mode, ok }
    """
    user = _get_user_from_session(request)
    actor = (user or {}).get("cpf") or "anonymous"
    return {"actor": actor, "ep_mode": EP_MODE, "ok": True}

@APP.get("/demo")
def demo_home() -> HTMLResponse:
    """
    Página HTML de demonstração servida pelo BFF (pode ser embutida via iframe).

    Retorna
    -------
    HTMLResponse
    """
    html = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Plataforma AGEPAR — Demo</title>
    <style>
      html,body { height:100%; margin:0; font-family:system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, 'Helvetica Neue', Arial; }
      .wrap { height:100%; display:flex; align-items:center; justify-content:center; background: #0ea5e9; color:#fff; }
      .card { background: rgba(255,255,255,0.15); padding: 24px 28px; border-radius: 16px; backdrop-filter: blur(6px); }
      h1 { margin:0 0 8px; font-size: 22px }
      p { margin:0; opacity: .9 }
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="card">
        <h1>Bem-vindo à Plataforma AGEPAR</h1>
        <p style="text-align: center;">Este conteúdo está sendo desenvolvido.</p>
      </div>
    </div>
  </body>
</html>
"""
    return HTMLResponse(html)

@APP.get("/api/demo")
def demo_home_api() -> HTMLResponse:
    """
    Alias de /demo sob /api (facilita proxy do Vite).

    Retorna
    -------
    HTMLResponse
    """
    return demo_home()

@APP.get("/api/automations")
def automations_index() -> Dict[str, Any]:
    """
    Índice das automações publicadas pelo BFF.

    Retorna
    -------
    dict
        Lista com {kind, version, title} por automação.
    """
    return {"items": AUTOMATIONS_INDEX_ITEMS}

APP.include_router(fileshare_router,       dependencies=[Depends(require_password_changed)])
APP.include_router(form2json_router,       dependencies=[Depends(require_password_changed)])
APP.include_router(dfd_router,             dependencies=[Depends(require_password_changed)])
APP.include_router(etp_router,             dependencies=[Depends(require_password_changed)])
APP.include_router(ferias_router,          dependencies=[Depends(require_password_changed)])
APP.include_router(controle_router,        dependencies=[Depends(require_password_changed)])
APP.include_router(controle_ferias_router, dependencies=[Depends(require_password_changed)])
APP.include_router(controle_tasks_router,  dependencies=[Depends(require_password_changed)])
APP.include_router(support_router,         dependencies=[Depends(require_password_changed)])
APP.include_router(ponto_saldo_router,     dependencies=[Depends(require_password_changed)])
APP.include_router(accounts_router,        dependencies=[Depends(require_password_changed)])
APP.include_router(avisos_router,          dependencies=[Depends(require_password_changed)])
APP.include_router(whoisonline_router,     dependencies=[Depends(require_password_changed)])
APP.include_router(tasks_router,           dependencies=[Depends(require_password_changed)])
APP.include_router(usuarios_router,        dependencies=[Depends(require_password_changed)])
APP.include_router(profile_router,         dependencies=[Depends(require_password_changed)])
APP.include_router(notifications_router,   dependencies=[Depends(require_password_changed)])

"""
Nota de segurança (produção)
---------------------------
- Ao migrar para OIDC, configurar AUTH_MODE="oidc" e implementar fluxo Authorization Code + PKCE.
- Validar ID Token via JWKS (OIDC_ISSUER / OIDC_JWKS_URL) e emitir sessão segura.
- Em produção sob HTTPS, marcar o cookie de sessão como Secure e SameSite=None.
"""
