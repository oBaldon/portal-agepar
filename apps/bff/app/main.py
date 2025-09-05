from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

# ---- Automations infra / routers ----
from app.db import init_db
from app.automations.form2json import router as form2json_router
from app.games.snake import router as snake_router
from app.auth.routes import router as auth_router
from app.auth.middleware import DbSessionMiddleware
from app.auth.sessions import router as auth_sessions_router


# ------------------------------------------------------------------------------
# Configuração (envs)
# ------------------------------------------------------------------------------
ENV = os.getenv("ENV", "dev")

# Agora o padrão é "local" (login real). O mock vira legado e fica desativado.
AUTH_MODE = os.getenv("AUTH_MODE", "local")  # valores: "local" (real), futuramente "oidc"
AUTH_LEGACY_MOCK = os.getenv("AUTH_LEGACY_MOCK", "0").lower() in ("1", "true", "yes")

EP_MODE = os.getenv("EP_MODE", "mock")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
CATALOG_FILE = Path(os.getenv("CATALOG_FILE", "/catalog/catalog.dev.json"))

# Placeholders para OIDC (não usados por enquanto)
OIDC_ISSUER = os.getenv("OIDC_ISSUER", "")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
OIDC_JWKS_URL = os.getenv("OIDC_JWKS_URL", "")

# ------------------------------------------------------------------------------
# App
# ------------------------------------------------------------------------------
APP = FastAPI(title="Portal AGEPAR BFF", version="0.2.0", docs_url="/docs", redoc_url="/redoc")

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

# Routers
APP.include_router(snake_router)
APP.include_router(auth_router)          # /api/auth/login (POST), /api/auth/logout (POST), /api/auth/register...
APP.include_router(auth_sessions_router) # /api/auth/sessions[...]

# ------------------------------------------------------------------------------
# Startup
# ------------------------------------------------------------------------------
@APP.on_event("startup")
def _startup() -> None:
    # Inicializa o banco (SQLite) usado pelas automações (submissions/audits)
    init_db()

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
    ) -> Dict[str, Any]:
        """
        [LEGADO/DEV] Cria sessão mock a partir de query params.
        Só é exposto quando AUTH_LEGACY_MOCK=1.
        """
        user = {
            "cpf": cpf or "00000000000",
            "nome": nome or "Usuário de Teste",
            "email": email or "teste@example.com",
            "roles": [r.strip() for r in (roles or "user").split(",") if r.strip()],
            "unidades": [u.strip() for u in (unidades or "AGEPAR").split(",") if u.strip()],
            "auth_mode": "mock",
        }
        request.session["user"] = user
        # Não cria sessão no banco — uso apenas temporário em DEV.
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
    <title>Portal AGEPAR — Demo</title>
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
        <h1>Bem-vindo ao Portal AGEPAR (demo)</h1>
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
        ]
    }

# ------------------------------------------------------------------------------
# Routers de automações
# ------------------------------------------------------------------------------
APP.include_router(form2json_router)

# ------------------------------------------------------------------------------
# Nota de segurança (prod)
# ------------------------------------------------------------------------------
# Em produção, trocar AUTH_MODE para "oidc" quando implementado e:
#   * /api/auth/login → fluxo Authorization Code + PKCE
#   * callback → validar ID Token via JWKS (OIDC_ISSUER / JWKS_URL) e criar sessão
# Cookie de sessão: marcar como Secure e SameSite=None sob HTTPS.
# ------------------------------------------------------------------------------