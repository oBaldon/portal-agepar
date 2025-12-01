---
id: superfícies-públicas-api-catalog-docs-e-mitigação
title: "Superfícies públicas (/api, /catalog, /docs) e mitigação"
sidebar_position: 6
---

Quando o Portal AGEPAR está de pé, existem basicamente **três “frentes” acessíveis via HTTP**:

- **BFF** em `/api` (mais `/health`, `/version` e `/catalog/dev`);
- **Host** (SPA React) em `/` (e o que ele proxia para o BFF);
- **Docs de dev** em `/devdocs` (Docusaurus, via proxy do Host).

Esta página mapeia essas superfícies e resume **o que já existe de proteção** e **o que é recomendado endurecer** em ambientes reais.

> Referências principais no repositório:  
> `apps/bff/app/main.py`  
> `apps/bff/app/auth/*`  
> `apps/bff/app/automations/*`  
> `apps/bff/app/games/snake.py`  
> `apps/host/vite.config.ts`  
> `apps/docs-site/docusaurus.config.ts`  
> `infra/docker-compose.dev.yml`  

---

## 1) Visão geral das superfícies

```mermaid
flowchart LR
  subgraph Public
    Browser[(Browser do usuário)]
  end

  subgraph Edge["Reverse proxy / Ingress"]
    RP["https://portal... (Host + /devdocs)"]
    API["https://api.portal... (/api, /health, /version, /catalog)"]
  end

  subgraph Cluster["Cluster / Docker"]
    HOST["Host (Vite/React) :5173"]
    BFF["BFF (FastAPI) :8000"]
    DOCS["Docs (Docusaurus) :8000"]
    PG["Postgres"]
  end

  Browser --> RP
  RP --> HOST
  RP --> API
  HOST -->|proxy /api,/catalog| BFF
  HOST -->|proxy /devdocs| DOCS
  BFF --> PG
````

Na prática:

* Em **dev** (Compose):

  * BFF → `http://localhost:8000`
  * Host → `http://localhost:5173`
  * Docs → `http://localhost:5173/devdocs` (e opcionalmente `http://localhost:9000/`)
* Em **prod**, a ideia é:

  * um domínio para o Host (portal),
  * um domínio ou path para o BFF (`/api`),
  * docs de dev ou internas atrás de rede restrita.

---

## 2) BFF — `/api`, `/health`, `/version`, `/catalog/dev`, `/api/docs`

### 2.1. Rotas expostas pelo BFF

No `main.py`:

```python title="apps/bff/app/main.py — FastAPI principal" showLineNumbers
APP = FastAPI(
    title="Portal AGEPAR BFF",
    version="0.3.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

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

@APP.get("/api/me")
def get_me(request: Request) -> Dict[str, Any]:
    user = _get_user_from_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user

@APP.get("/catalog/dev")
def catalog_dev() -> Any:
    ...
```

Além disso, o BFF inclui:

* `auth_router` (`/api/auth/*` — login/logout/sessões),
* `auth_sessions_router` (`/api/auth/sessions` etc.),
* routers de automação sob `/api/automations/{slug}`,
* `snake_router` em `/api/games/snake`.

Trecho de inclusão de routers com dependências de segurança:

```python title="apps/bff/app/main.py — routers de automações" showLineNumbers
from app.auth.rbac import require_password_changed

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

APP.include_router(snake_router)           # jogo/POC, sem auth
APP.include_router(auth_router)            # login/logout
APP.include_router(auth_sessions_router)   # gestão de sessões
```

### 2.2. Classificando “superfície pública” no BFF

Hoje, no código, temos:

* **Sem autenticação (by design):**

  * `GET /health` → para probes de liveness/monitoramento.
  * `GET /version` → metadados de versão/ambiente (útil para suporte).
  * `GET /api/docs`, `GET /api/redoc` → documentação gerada OpenAPI.
  * `GET /api/games/snake/ui` → jogo de exemplo (HTML estático).
  * `POST /api/auth/login` → entrada de credenciais.
* **Protegidas apenas por sessão (não por role específico):**

  * `GET /api/me` (só precisa estar logado).
  * `/api/auth/logout`, `/api/auth/sessions/*`.
  * Alguns endpoints mais “infra” dentro de automations (ex.: `schema`).
* **Protegidas por sessão **e** RBAC (ANY-of)**:

  * a maioria dos endpoints de automação (`dfd`, `ferias`, `controle`, `fileshare`, `usuarios`, etc.),
  * normalmente com `require_roles_any(...)` e/ou `require_roles_all(...)`.

Além disso, o BFF protege:

* **UI das automations** (HTML/iframe) com RBAC na própria rota:

```python title="apps/bff/app/automations/dfd.py — proteção de /ui" showLineNumbers
@router.get("/ui")
@router.get("/ui/")
async def dfd_ui(request: Request):
    checker = require_roles_any(*REQUIRED_ROLES)
    try:
        checker(request)
    except HTTPException as he:
        status = he.status_code
        msg = "Faça login..." if status == 401 else "Você não tem permissão..."
        return HTMLResponse(html_err, status_code=status)

    html = _read_html("ui.html")
    return HTMLResponse(html)
```

> ✅ **Mitigação**: mesmo as páginas HTML em iframe (`/ui`) só rendem conteúdo se
> o usuário estiver autenticado e com o papel correto.

### 2.3. `/catalog/dev` — catálogo de blocos

O catálogo de automações é exposto como JSON em:

```python title="apps/bff/app/main.py — /catalog/dev" showLineNumbers
CATALOG_FILE = Path(os.getenv("CATALOG_FILE", "/catalog/catalog.dev.json"))

@APP.get("/catalog/dev")
def catalog_dev() -> Any:
    if not CATALOG_FILE.exists():
        raise HTTPException(status_code=404, detail="catalog file not found")
    try:
        data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail="catalog parse error")
    return data
```

Características:

* Não exige autenticação (qualquer cliente HTTP consegue obter o catálogo).
* CORS continua valendo (browsers só consomem se a origem estiver em `CORS_ORIGINS`).
* Conteúdo é puramente **metadados de UI** (categorias, blocos, URLs, descrição), sem dados de usuário.

Mitigação recomendada:

* **Nunca** colocar dados sensíveis ou PII no catálogo.
* Tratar o catálogo como “arquivo de configuração público”:

  * apenas slugs de automations, labels, descrições e ícones.

### 2.4. `/api/docs` e `/api/redoc`

São gerados pelo FastAPI com base nos routers:

```python
APP = FastAPI(..., docs_url="/api/docs", redoc_url="/api/redoc")
```

Em dev, isso é excelente para debug. Em produção:

* não expõe dados, apenas a **forma** da API;
* pode ser útil para times internos;
* também vira uma fonte fácil de recon para atacantes.

Mitigação recomendada em ambientes sensíveis:

* ou desabilitar (`docs_url=None`, `redoc_url=None`),
* ou proteger via:

  * autenticação (ex.: basic auth no reverse proxy),
  * IP allow-list (somente rede interna/VPN).

### 2.5. Fileshare — endpoint com link público

A automação `fileshare` tem um endpoint **concebido** para consumo público (download por token HMAC):

```python title="apps/bff/app/automations/fileshare.py — /share/{token}" showLineNumbers
@router.get("/share/{token}")
def share_download(token: str):
    """
    Endpoint público para baixar via token assinado.
    """
    # valida token, TTL, assinatura HMAC
    # carrega metadados + arquivo
    db.fileshare_inc_downloads(item_id)
    db.audit_log(
        actor={"cpf": "anonymous"},
        action="downloaded_shared_link",
        kind="fileshare",
        target_id=item_id,
        meta={"via": "token"},
    )
    return StreamingResponse(..., media_type=mime_type)
```

Mitigações intrínsecas:

* Tokens incluem:

  * ID do item,
  * expiração (`expires_at`),
  * assinatura HMAC com `SESSION_SECRET`.
* Mesmo que o token vaze:

  * o acesso é limitado ao **arquivo específico** e até a data de expiração.
* Download é auditado (`automation_audits`) com `actor={"cpf":"anonymous"}`.

Mitigação de infra:

* Tratar `/api/automations/fileshare/share/{token}` como **única rota pensada para acesso anônimo externo**.
* Aplicar:

  * throttling/rate limit de IP,
  * monitoramento de volume de downloads,
  * proteção contra brute force de token (tokens devem ser suficientemente grandes).

---

## 3) Host — SPA em `/` + proxy para `/api`, `/catalog`, `/devdocs`

### 3.1. Proxies de desenvolvimento (Vite)

`apps/host/vite.config.ts`:

```ts title="apps/host/vite.config.ts — proxies" showLineNumbers
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api":     { target: "http://bff:8000", changeOrigin: true },
      "/catalog": { target: "http://bff:8000", changeOrigin: true },
      "/devdocs": { target: "http://docs:8000", changeOrigin: true },
    },
  },
});
```

Ou seja:

* Para o browser, tudo parece vir de `http://localhost:5173`:

  * `/api/...` → proxia para o BFF,
  * `/catalog/...` → proxia para o BFF,
  * `/devdocs/...` → proxia para o container de docs.
* Isso reduz exposição de CORS em dev (tudo mesmo origin).

Em produção, a ideia é semelhante:

* Host servindo a SPA (HTML+JS+CSS),
* reverse proxy repassando `/api` para o BFF,
* `/docs` ou `/devdocs` para o site de documentação.

### 3.2. Mitigações do Host

* O Host **não guarda segredos**:

  * todo acesso protegido passa pelo BFF (sessão, RBAC).
* Usa `fetch(..., credentials: "include")`:

  * cookies de sessão HTTP-only,
  * CORS restrito às origens oficiais.
* Aplica **RBAC de vitrine** (ANY-of) no catálogo:

  * só renderiza blocos/categorias compatíveis com `user.roles`,
  * evita que o usuário veja cards que, de qualquer forma, dariam 403 no BFF.

> Importante: o Host não substitui o RBAC do BFF; ele só evita
> exposições desnecessárias na UI.

---

## 4) Docs de dev — `/devdocs` (Docusaurus)

### 4.1. Base URL e proxy

No Docusaurus:

```ts title="apps/docs-site/docusaurus.config.ts" showLineNumbers
const config: Config = {
  title: 'Plataforma AGEPAR — Dev Docs',
  // ...
  url: 'http://localhost',
  // Caminho base onde o site será servido (via proxy do Host em /devdocs)
  baseUrl: '/devdocs/',
  // ...
};
```

No Compose:

```yaml title="infra/docker-compose.dev.yml — serviço docs" showLineNumbers
  docs:
    image: node:20-alpine
    container_name: portal-agepar-docs
    working_dir: /work/apps/docs-site
    environment:
      NODE_ENV: development
      CI: "true"
    volumes:
      - ../:/work
    ports:
      - "9000:8000"  # opcional (acesso direto além do proxy)
    command: >
      sh -lc "
        (test -f package-lock.json && npm ci --quiet) || npm install --quiet &&
        npm run start -- --host 0.0.0.0 --port 8000
      "
```

Superfícies resultantes em dev:

* `http://localhost:5173/devdocs` — caminho “oficial” via Host,
* `http://localhost:9000/` — acesso direto ao servidor do Docusaurus (opcional).

### 4.2. Riscos e mitigação

Conteúdo de `/devdocs`:

* é **documentação para desenvolvedores**,
* normalmente contém:

  * detalhes de arquitetura,
  * nomes de tabelas e rotas,
  * exemplos de payloads.

Mitigação recomendada:

* Em ambientes públicos:

  * restringir `/devdocs` (ou `/docs`) a:

    * rede interna / VPN,
    * ou autenticação (ex.: SSO da casa),
  * evitar expor `/devdocs` diretamente na internet sem controle.
* Em produção voltada para público externo:

  * ter um **site de docs “reduzido”** (sem detalhes sensíveis) se necessário,
  * manter as dev docs completas apenas em ambientes internos.

---

## 5) Resumo de mitigação por superfície

| Superfície                 | Quem deve acessar                             | Controles atuais (código)                                                                | Recomendações adicionais (infra)                                   |
| -------------------------- | --------------------------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `/health`                  | Probes, observabilidade                       | Sem auth; responde `{"status":"ok"}`                                                     | Expor só internamente (kube/monitoring), não via internet direta   |
| `/version`                 | Dev/ops, suporte                              | Sem auth; mostra env, versões, origens CORS, nome de arquivo de catálogo                 | Restringir via IP ou auth em prod (ou desabilitar se não precisar) |
| `/api` (auth, automations) | Host + clientes oficiais                      | Sessão via cookie HTTP-only; `require_password_changed`, RBAC ANY-of nas rotas sensíveis | TLS obrigatório, WAF/rate limit, logs estruturados                 |
| `/catalog/dev`             | Host + ferramentas internas                   | Sem auth; apenas metadados; CORS restrito a origens confiáveis                           | Garantir que catálogo não contenha PII/segredos                    |
| `/api/docs`, `/api/redoc`  | Dev/ops interno                               | Sem auth, OpenAPI gerado automaticamente                                                 | Proteger ou desligar em prod pública                               |
| `/api/.../fileshare/share` | Destinatários de links de arquivos (externos) | Token HMAC + TTL; auditoria de downloads                                                 | Rate limit por IP; monitorar abuso; limitar tamanho/tempo          |
| `/devdocs`                 | Devs internos                                 | Sem auth na app; proxy via Host em `/devdocs`                                            | Expor só em intranet/VPN ou com SSO                                |

---

## 6) Exemplos práticos (cURL)

### 6.1. Checar exposição de `/version` em dev

```bash title="Checando /version" showLineNumbers
curl -s http://localhost:8000/version | jq .
```

Saída típica:

```json
{
  "app": "0.3.0",
  "env": "dev",
  "dfd_version": "2.4.0",
  "ferias_version": "x.y.z",
  "auth_mode": "mock",
  "auth_legacy_mock": false,
  "ep_mode": "mock",
  "cors_origins": ["http://localhost:5173", "http://127.0.0.1:5173"],
  "catalog_file": "/catalog/catalog.dev.json"
}
```

Em prod, avaliar se esse nível de exposição é aceitável.

### 6.2. Ver catálogo dev

```bash title="GET /catalog/dev" showLineNumbers
curl -s http://localhost:8000/catalog/dev | jq '.categories[0], .blocks[0]'
```

Conferir se:

* não há dados de usuários,
* não há URLs internas “secretas”,
* apenas config de UI.

---

> _Criado em 2025-12-01_