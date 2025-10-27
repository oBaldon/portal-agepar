---
id: variáveis-de-ambiente-e-cors-cookies
title: "Variáveis de ambiente e CORS/cookies"
sidebar_position: 3
---

_Criado em 2025-10-27 12:47:50_

Esta página reúne **variáveis de ambiente** usadas no Host/BFF e as **configurações de CORS e cookies** típicas para desenvolvimento.

> Regra geral: em dev, **origem** do Host `http://localhost:5173` deve estar liberada no BFF; sessões são mantidas por **cookies**.

## 1) Variáveis do Host (Vite/React)

As variáveis com prefixo `VITE_` ficam disponíveis no código do frontend.

```dotenv
# .env (Host)
VITE_API_BASE=http://localhost:8000
VITE_CATALOG_BASE=http://localhost:8000
VITE_DOCS_BASE=http://localhost:8000
````

Exemplo de uso em TS:

```ts
const API = import.meta.env.VITE_API_BASE ?? "/api";
```

## 2) Variáveis do BFF (FastAPI)

```dotenv
# .env (BFF)
APP_ENV=dev
DB_URL=sqlite:///./data.db
CORS_ORIGINS=http://localhost:5173
SESSION_SECRET=dev-secret-only-local
COOKIE_DOMAIN=localhost
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
```

Leitura (exemplo) no Python:

```py
import os
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS","").split(",") if o.strip()]
SESSION_SECRET = os.getenv("SESSION_SECRET","change-me")
```

## 3) CORS (FastAPI)

Habilite CORS quando o Host roda fora do container do BFF:

```py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI()

origins = [o.strip() for o in os.getenv("CORS_ORIGINS","http://localhost:5173").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,           # necessário para cookies
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 4) Cookies de sessão (dev)

* **Por quê cookies?** o Host (navegador) envia cookies automaticamente, simplificando o mock de sessão.
* **Atenção**: combine `COOKIE_SECURE=false` em dev (HTTP) e `true` em prod (HTTPS).

Criação do cookie após login mock:

```py
from fastapi import APIRouter, Response
from datetime import timedelta
import os

router = APIRouter()

@router.post("/api/auth/login")
def login(payload: dict, response: Response):
    token = "mock-session-token"
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE","false").lower()=="true",
        samesite=os.getenv("COOKIE_SAMESITE","lax"),
        max_age=int(timedelta(hours=8).total_seconds()),
        domain=os.getenv("COOKIE_DOMAIN","localhost"),
        path="/",
    )
    return {"ok": True}
```

Leitura do cookie:

```py
from fastapi import Cookie, HTTPException

@router.get("/api/me")
def me(session: str | None = Cookie(default=None)):
    if not session:
        raise HTTPException(status_code=401, detail="missing session")
    return {"user": "dev", "roles": ["admin"]}
```

## 5) Vite — proxy + credenciais

Garanta que o **proxy** preserve cookies e que as chamadas fetch enviem credenciais:

```ts
// vite.config.ts
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/catalog": "http://localhost:8000",
      "/docs": "http://localhost:8000"
    }
  }
})
```

```ts
// chamada no frontend
fetch("/api/me", { credentials: "include" })
  .then(r => r.json())
  .then(console.log);
```

## 6) cURLs úteis (cookies)

```bash
# login mock (recebe Set-Cookie: session=...)
curl -i -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"dev","password":"dev"}' \
  -c cookies.txt

# chamada autenticada usando cookie salvo
curl -i http://localhost:8000/api/me -b cookies.txt
```

## 7) Boas práticas

* **Nunca** subir segredos reais no repositório; use valores de dev.
* Em **prod**: `COOKIE_SECURE=true`, `SameSite=None` (se necessário) e HTTPS obrigatório.
* Liste explicitamente as **origens** em produção (`CORS_ORIGINS=https://seu.host`).
* Documente as variáveis **por ambiente** (dev/hml/prod).

---

> _Esta página descreve variáveis e segurança de transporte. Consulte também “Proxies do Vite” e “Troubleshooting”._

_Criado em 2025-10-27 12:47:50_
