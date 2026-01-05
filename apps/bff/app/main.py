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

from fastapi import FastAPI, Request, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

from app.automations.dfd import DFD_VERSION as DFD_VER
from app.automations.ferias import router as ferias_router, FERIAS_VERSION as FERIAS_VER
from app.db import init_db
from app.automations.form2json import router as form2json_router
from app.automations.dfd import router as dfd_router
from app.automations.controle import router as controle_router
from app.automations.controle_ferias import router as controle_ferias_router
from app.automations.accounts import router as accounts_router
from app.automations.fileshare import router as fileshare_router
from app.automations.whoisonline import router as whoisonline_router
from app.automations.support import router as support_router
from app.automations.usuarios import router as usuarios_router
from app.games.snake import router as snake_router
from app.auth.routes import router as auth_router
from app.auth.middleware import DbSessionMiddleware
from app.auth.sessions import router as auth_sessions_router
from app.auth.rbac import require_password_changed

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
    logger.info("DFD engine version: %s", DFD_VER)
    logger.info("FERIAS engine version: %s", FERIAS_VER)

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
        }
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
    return {
        "items": [
            {"kind": "form2json", "version": "1.0.0", "title": "Formulário para JSON"},
            {"kind": "dfd", "version": DFD_VER, "title": "DFD — Documento de Formalização da Demanda"},
            {"kind": "ferias", "version": FERIAS_VER, "title": "Férias — Requerimento + Substituição"},
            {"kind": "controle", "version": "1.0.0", "title": "Painel de Controle (Auditoria)", "readOnly": True},
            {"kind": "fileshare", "version": "0.1.0", "title": "Área Comunitária — Arquivos Temporários"},
            {"kind": "support", "version": "1.0.0", "title": "Suporte & Feedback"},
            {"kind": "accounts", "version": "1.0.0", "title": "Admin — Contas & Roles"},
            {"kind": "whoisonline", "version": "0.1.0", "title": "Quem está online (Superuser)"},
            {"kind": "usuarios", "version": "1.0.0", "title": "Admin — Gestão de Usuários"},
        ]
    }

APP.include_router(fileshare_router,       dependencies=[Depends(require_password_changed)])
APP.include_router(form2json_router,       dependencies=[Depends(require_password_changed)])
APP.include_router(dfd_router,             dependencies=[Depends(require_password_changed)])
APP.include_router(ferias_router,          dependencies=[Depends(require_password_changed)])
APP.include_router(controle_router,        dependencies=[Depends(require_password_changed)])
APP.include_router(controle_ferias_router, dependencies=[Depends(require_password_changed)])
APP.include_router(support_router,         dependencies=[Depends(require_password_changed)])
APP.include_router(accounts_router,        dependencies=[Depends(require_password_changed)])
APP.include_router(whoisonline_router,     dependencies=[Depends(require_password_changed)])
APP.include_router(usuarios_router,        dependencies=[Depends(require_password_changed)])

"""
Nota de segurança (produção)
---------------------------
- Ao migrar para OIDC, configurar AUTH_MODE="oidc" e implementar fluxo Authorization Code + PKCE.
- Validar ID Token via JWKS (OIDC_ISSUER / OIDC_JWKS_URL) e emitir sessão segura.
- Em produção sob HTTPS, marcar o cookie de sessão como Secure e SameSite=None.
"""
