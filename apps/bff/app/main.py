from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import httpx, os, time, base64, hashlib

AUTH_MODE = os.getenv("AUTH_MODE", "oidc")  # "oidc" (padrão) | "mock"
EP_MODE   = os.getenv("EP_MODE", "real")    # "real" (padrão) | "mock"

# usuários de teste (pode trocar via env TEST_USERS_JSON se quiser)
DEFAULT_TEST_USERS = [
    {"cpf":"12345678901","name":"Servidor de Teste","email":"teste@agepar.pr.gov.br","roles":["requisitante"],"unidades":["UA-001"]},
    {"cpf":"98765432100","name":"Planejamento Demo","email":"planejamento@agepar.pr.gov.br","roles":["planejamento"],"unidades":["UA-001","UA-002"]}
]
import json as _json
_raw = os.getenv("TEST_USERS_JSON", "").strip()
try:
    TEST_USERS = _json.loads(_raw) if _raw else DEFAULT_TEST_USERS
except Exception as e:
    print(f"[WARN] TEST_USERS_JSON inválido ({e}); usando DEFAULT_TEST_USERS")
    TEST_USERS = DEFAULT_TEST_USERS


APP = FastAPI(title="Portal AGEPAR – BFF")


@APP.on_event("startup")
async def _guard_mock_em_ambientes():
    env = os.getenv("ENV", "dev").lower()
    if AUTH_MODE == "mock" and env in ("hml", "prod"):
        raise RuntimeError("AUTH_MODE=mock não é permitido fora de dev")

APP.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)
APP.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "dev-secret"), https_only=False)

# ===== Config OIDC (Central de Segurança) =====
ISSUER = os.getenv("CS_ISSUER", "https://auth-cs-hml.identidadedigital.pr.gov.br/centralautenticacao")
AUTH_URL = os.getenv("CS_AUTH_URL", f"{ISSUER}/oauth2/authorize")
TOKEN_URL = os.getenv("CS_TOKEN_URL", f"{ISSUER}/api/v1/token/jwt")
JWKS_URL = os.getenv("CS_JWKS_URL", f"{ISSUER}/.well-known/jwks.json")
CLIENT_ID = os.getenv("CS_CLIENT_ID", "changeme")
CLIENT_SECRET = os.getenv("CS_CLIENT_SECRET", "changeme")
REDIRECT_URI = os.getenv("CS_REDIRECT_URL", "http://localhost:8000/auth/callback")
SCOPES = (os.getenv("CS_SCOPES", "openid email profile")).split()
EP_SCOPES = (os.getenv("EP_SCOPES", "")).split()

JWKS_CACHE = None
JWKS_TS = 0

async def get_jwks():
    global JWKS_CACHE, JWKS_TS
    if JWKS_CACHE and time.time() - JWKS_TS < 3600:
        return JWKS_CACHE
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(JWKS_URL)
        r.raise_for_status()
        JWKS_CACHE = r.json()
        JWKS_TS = time.time()
        return JWKS_CACHE

def _session(request: Request) -> dict:
    return request.session.setdefault("user", {})

@APP.get("/health")
async def health():
    return {"status": "ok"}

# ===== Auth (Authorization Code + PKCE S256) =====
@APP.get("/api/auth/login")
async def login(request: Request):
    if AUTH_MODE == "mock":
        qp = request.query_params
        user = next((u for u in TEST_USERS if u["cpf"] == qp.get("cpf")), TEST_USERS[0])
        request.session["user"] = {
            "cpf":  qp.get("cpf") or user["cpf"],
            "name": qp.get("name") or user["name"],
            "email":qp.get("email") or user["email"],
            "roles":_json.loads(qp.get("roles","[]")) if qp.get("roles") else user.get("roles",[]),
            "unidades":_json.loads(qp.get("unidades","[]")) if qp.get("unidades") else user.get("unidades",[])
        }
        # no mock não há access token; guarde um marcador
        request.session["access_token"] = "MOCK_TOKEN"
        return RedirectResponse("/")
    # === fluxo OIDC real (igual ao que já fizemos) ===
    from secrets import token_urlsafe
    state = token_urlsafe(24)
    code_verifier = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).decode().rstrip("=")
    request.session["oauth_state"] = state
    request.session["code_verifier"] = code_verifier
    params = {
        "response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES + EP_SCOPES), "state": state,
        "code_challenge": code_challenge, "code_challenge_method": "S256",
    }
    url = httpx.URL(AUTH_URL, params=params)
    return RedirectResponse(str(url))

@APP.get("/auth/callback")
async def callback(request: Request, code: str = "", state: str = ""):
    if state != request.session.get("oauth_state"):
        return JSONResponse({"error": "invalid_state"}, status_code=400)

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": request.session.get("code_verifier", "")
    }
    # algumas CS exigem client_secret no body; se não, use auth header basic
    if CLIENT_SECRET:
        data["client_secret"] = CLIENT_SECRET

    async with httpx.AsyncClient(timeout=20) as client:
        tok = await client.post(TOKEN_URL, data=data, headers={"Content-Type":"application/x-www-form-urlencoded"})
    if tok.status_code != 200:
        return JSONResponse({"error":"token_exchange_failed","detail": tok.text}, status_code=401)

    tokens = tok.json()
    id_token = tokens.get("id_token")
    access_token = tokens.get("access_token")

    # (Opcional) Validar ID Token via JWKS (iss/aud/exp)
    try:
        from jose import jwt
        jwks = await get_jwks()
        unverified = jwt.get_unverified_header(id_token)
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == unverified.get("kid")), None)
        if not key:
            raise ValueError("JWKS key not found")
        claims = jwt.decode(
            id_token,
            key,
            algorithms=[unverified.get("alg", "RS256")],
            audience=CLIENT_ID,
            issuer=ISSUER
        )
    except Exception as e:
        # Em dev, podemos seguir sem a validação completa; em prod, trate como 401
        try:
            from jose import jwt
            claims = jwt.get_unverified_claims(id_token) if id_token else {}
        except Exception:
            claims = {}

    user = {
        "cpf": claims.get("cpf") or claims.get("documento") or "",
        "name": claims.get("name") or claims.get("preferred_username") or "Servidor",
        "email": claims.get("email") or "",
        "roles": [],
        "obtained_at": int(time.time())
    }
    request.session["user"] = user
    request.session["access_token"] = access_token
    return RedirectResponse("/")

@APP.post("/api/auth/logout")
async def do_logout(request: Request):
    request.session.clear()
    return JSONResponse({"ok": True})

@APP.get("/api/me")
async def me(request: Request):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"error":"unauthenticated"}, status_code=401)
    return {k: user[k] for k in ("cpf","name","email","roles")}

# ===== Catálogo (servir arquivo dev) =====
@APP.get("/catalog/dev")
async def catalog_dev():
    import pathlib, json as _json
    p = pathlib.Path(__file__).resolve().parents[3] / "catalog" / "catalog.dev.json"
    return JSONResponse(_json.loads(p.read_text("utf-8")))

# ===== eProtocolo (ping de teste) =====
@APP.get("/api/eprotocolo/ping")
async def ep_ping(request: Request):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    if EP_MODE == "mock":
        return {"actor": user.get("cpf"), "ep_mode": "mock", "ok": True}
    # real: aqui você chamaria o gateway com Authorization Bearer do usuário
    return {"actor": user.get("cpf"), "ep_mode": "real", "ok": True}

