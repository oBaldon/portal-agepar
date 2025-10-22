# apps/bff/app/main.py
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

from app.automations.dfd import DFD_VERSION as DFD_VER
from app.automations.ferias import router as ferias_router, FERIAS_VERSION as FERIAS_VER
# ---- Automations infra / routers ----
from app.db import init_db
from app.automations.form2json import router as form2json_router
from app.automations.dfd import router as dfd_router
from app.automations.controle import router as controle_router
from app.automations.controle_ferias import router as controle_ferias_router  # calendário de férias (aba do controle)
from app.automations.accounts import router as accounts_router
from app.automations.fileshare import router as fileshare_router
from app.automations.whoisonline import router as whoisonline_router
from app.automations.support import router as support_router
from app.games.snake import router as snake_router
from app.auth.routes import router as auth_router
from app.auth.middleware import DbSessionMiddleware
from app.auth.sessions import router as auth_sessions_router

# ------------------------------------------------------------------------------
# Configuração (envs)
# ------------------------------------------------------------------------------
ENV = os.getenv("ENV", "dev")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Agora o padrão é "local" (login real). O mock vira legado e fica desativado.
AUTH_MODE = os.getenv("AUTH_MODE", "local")  # valores: "local" (real), futuramente "oidc"
AUTH_LEGACY_MOCK = os.getenv("AUTH_LEGACY_MOCK", "0").lower() in ("1", "true", "yes")

EP_MODE = os.getenv("EP_MODE", "mock")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
CATALOG_FILE = Path(os.getenv("CATALOG_FILE", "/catalog/catalog.dev.json"))

# Placeholders para OIDC (não usados por enquanto)
OIDC_ISSUER = os.getenv("OIDC_ISSUER", "")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
OIDC_JWKS_URL = os.getenv("OIDC_JWKS_URL", "")

# Roles padrão para sessão mock (mantém consistência com rotas reais)
def _auth_default_roles() -> list[str]:
    return [r.strip() for r in os.getenv("AUTH_DEFAULT_ROLES", "").split(",") if r.strip()]

# ------------------------------------------------------------------------------
# Logging básico (respeita LOG_LEVEL)
# ------------------------------------------------------------------------------
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)
logger.info(
    "Starting BFF (ENV=%s, AUTH_MODE=%s, LEGACY_MOCK=%s, LOG_LEVEL=%s, EP_MODE=%s)",
    ENV, AUTH_MODE, AUTH_LEGACY_MOCK, LOG_LEVEL, EP_MODE
)
logger.info("CORS_ORIGINS=%s | CATALOG_FILE=%s", ",".join(CORS_ORIGINS), str(CATALOG_FILE))

# ------------------------------------------------------------------------------
# App
# ------------------------------------------------------------------------------
# Importante: expurgamos o MkDocs do host. Para evitar colisão com /docs do host,
# movemos a UI do FastAPI para o prefixo /api, que já é proxied pelo Vite.
APP = FastAPI(title="Portal AGEPAR BFF", version="0.3.0", docs_url="/api/docs", redoc_url="/api/redoc")

# CORS primeiro (fica mais interno após os próximos add_middleware)
APP.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# IMPORTANTE (ordem dos middlewares):
# Em Starlette, o ÚLTIMO add_middleware é o mais externo (executa primeiro).
# Para que DbSessionMiddleware tenha acesso a request.session, o SessionMiddleware
# precisa executar ANTES (ser o mais externo). Portanto: adicionamos DbSessionMiddleware
# ANTES e SessionMiddleware DEPOIS.
APP.add_middleware(DbSessionMiddleware)
APP.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",           # dev
    https_only=False,          # dev
    session_cookie="portal_agepar_session",
)

# Routers básicos de infra/autenticação
APP.include_router(snake_router)
APP.include_router(auth_router)          # /api/auth/login (POST), /api/auth/logout (POST), /api/auth/register...
APP.include_router(auth_sessions_router) # /api/auth/sessions[...]
APP.include_router(fileshare_router)     # /api/automations/fileshare/...

# ------------------------------------------------------------------------------
# Startup
# ------------------------------------------------------------------------------
@APP.on_event("startup")
def _startup() -> None:
    # Inicializa o banco (Postgres) usado pelas automações (submissions/audits/fileshare)
    init_db()
    logger.info("DB initialized (Postgres)")
    logger.info("DFD engine version: %s", DFD_VER)
    logger.info("FERIAS engine version: %s", FERIAS_VER)

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _get_user_from_session(req: Request) -> Optional[Dict[str, Any]]:
    return req.session.get("user")

def _require_user(req: Request) -> Dict[str, Any]:
    u = _get_user_from_session(req)
    if not u:
        raise HTTPException(status_code=401, detail="not authenticated")
    return u

# ------------------------------------------------------------------------------
# Rotas base
# ------------------------------------------------------------------------------
@APP.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}

@APP.get("/version")
def version() -> Dict[str, Any]:
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

# ------------------------------------------------------------------------------
# MOCK legado (opcional): habilite somente em DEV e quando realmente precisar
# Sete AUTH_LEGACY_MOCK=1 para expor o GET /api/auth/login com params.
# ------------------------------------------------------------------------------
if AUTH_LEGACY_MOCK:
    @APP.get("/api/auth/login")
    def legacy_mock_login(
        request: Request,
        cpf: Optional[str] = Query(None),
        nome: Optional[str] = Query(None),
        email: Optional[str] = Query(None),
        roles: Optional[str] = Query(None),      # csv
        unidades: Optional[str] = Query(None),   # csv
        superuser: Optional[bool] = Query(False),
    ) -> Dict[str, Any]:
        """
        [LEGADO/DEV] Cria sessão mock a partir de query params.
        Só é exposto quando AUTH_LEGACY_MOCK=1.
        Mescla roles com AUTH_DEFAULT_ROLES para ficar consistente com o login real.
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
    user = _get_user_from_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user

@APP.get("/catalog/dev")
def catalog_dev() -> Any:
    if not CATALOG_FILE.exists():
        raise HTTPException(status_code=404, detail="catalog file not found")
    try:
        data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to read catalog: {e}")
    return JSONResponse(data)

@APP.get("/api/eprotocolo/ping")
def ep_ping(request: Request) -> Dict[str, Any]:
    user = _get_user_from_session(request)
    actor = (user or {}).get("cpf") or "anonymous"
    return {"actor": actor, "ep_mode": EP_MODE, "ok": True}

# Página demo que pode ser embutida num iframe
@APP.get("/demo")
def demo_home() -> HTMLResponse:
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
        <h1>Bem-vindo à Plataforma AGEPAR (demo)</h1>
        <p>Este conteúdo está servido pelo BFF e embutido via &lt;iframe&gt;.</p>
      </div>
    </div>
  </body>
</html>
"""
    return HTMLResponse(html)

# ADD: alias sob /api (passa pelo proxy do Vite)
@APP.get("/api/demo")
def demo_home_api() -> HTMLResponse:
    return demo_home()

# ------------------------------------------------------------------------------
# Catálogo de automações (índice)
# ------------------------------------------------------------------------------
@APP.get("/api/automations")
def automations_index() -> Dict[str, Any]:
    """
    Lista de automações disponibilizadas pelo BFF.
    Cada automação expõe seu próprio router sob /api/automations/{kind}/...
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
        ]
    }

# ------------------------------------------------------------------------------
# Routers de automações
# ------------------------------------------------------------------------------
APP.include_router(form2json_router)
APP.include_router(dfd_router)
APP.include_router(ferias_router)
APP.include_router(controle_router)
APP.include_router(controle_ferias_router)  # calendário de férias (aba dentro do controle)
APP.include_router(support_router)
APP.include_router(accounts_router)
APP.include_router(whoisonline_router)
# (removido) APP.include_router(snake_router)  # já incluído acima

# ------------------------------------------------------------------------------
# Nota de segurança (prod)
# ------------------------------------------------------------------------------
# Em produção, trocar AUTH_MODE para "oidc" quando implementado e:
#   * /api/auth/login → fluxo Authorization Code + PKCE
#   * callback → validar ID Token via JWKS (OIDC_ISSUER / JWKS_URL) e criar sessão
# Cookie de sessão: marcar como Secure e SameSite=None sob HTTPS.
# ------------------------------------------------------------------------------
