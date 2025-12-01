---
id: cookies-de-sessão
title: "Cookies de sessão"
sidebar_position: 2
---

No Portal AGEPAR, a autenticação gira em torno de **três peças que trabalham juntas**:

1. Um **cookie de sessão HTTP** (`portal_agepar_session`) gerenciado pelo Starlette.
2. Uma **sessão persistida em banco** (`auth_sessions` no PostgreSQL).
3. Um **snapshot do usuário** em `request.session["user"]`, usado pelo BFF e pelo Host.

A ideia é:

- o **cookie** identifica a sessão de aplicação;
- a **tabela `auth_sessions`** decide se ela continua válida (TTL, revogação, IP, etc.);
- o **payload `user`** viabiliza RBAC e exibição rápida de dados no frontend.

> Referências principais no repositório:  
> `apps/bff/app/main.py` (SessionMiddleware + `/api/me`)  
> `apps/bff/app/auth/routes.py` (login/logout, criação de sessão)  
> `apps/bff/app/auth/middleware.py` (DbSessionMiddleware, sliding expiration)  
> `infra/sql/init_db.sql` (tabela `auth_sessions`)  
> `apps/host/src/lib/api.ts` (fetch com `credentials: "include"`)

---

## 1) Visão geral: como a sessão funciona

Fluxo resumido:

1. Usuário faz **login** em `/api/auth/login`.
2. BFF:
   - valida credenciais;
   - cria uma linha em `auth_sessions`;
   - monta um dicionário `user` com CPF, nome, email, roles etc.;
   - grava tudo em `request.session[...]`.
3. O **SessionMiddleware** serializa `request.session` em um cookie assinado,
   chamado `portal_agepar_session`.
4. Em cada requisição:
   - o browser manda o cookie (por ser `same_site="lax"` + `credentials: "include"`),
   - o Starlette reconstrói `request.session`,
   - o `DbSessionMiddleware` confere se `db_session_id` ainda corresponde a uma
     sessão de banco válida; se não, limpa a sessão (logout efetivo),
   - as rotas e o RBAC usam `request.session["user"]`.

Diagrama (simplificado):

```mermaid
sequenceDiagram
    participant Browser
    participant BFF as BFF (FastAPI)
    participant DB as Postgres (auth_sessions)

    Browser->>BFF: POST /api/auth/login (identifier, password)
    BFF->>DB: INSERT INTO auth_sessions(...)
    BFF->>BFF: request.session["user"] = {...}
    BFF->>BFF: request.session["db_session_id"] = uuid()

    BFF-->>Browser: 200 + Set-Cookie: portal_agepar_session=...

    loop cada requisição autenticada
      Browser->>BFF: GET /api/me (Cookie: portal_agepar_session=...)
      BFF->>BFF: SessionMiddleware → restaurar request.session
      BFF->>DB: DbSessionMiddleware → validar db_session_id
      alt sessão válida
        DB-->>BFF: ok (atualiza last_seen_at / expires_at)
        BFF-->>Browser: 200 {user: {...}}
      else sessão inválida/expirada
        DB-->>BFF: nenhuma linha
        BFF->>BFF: request.session.clear()
        BFF-->>Browser: 401 not authenticated
      end
    end
````

---

## 2) Cookie de sessão HTTP (`portal_agepar_session`)

O cookie é configurado em `apps/bff/app/main.py`:

```python title="apps/bff/app/main.py — SessionMiddleware" showLineNumbers
APP.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=False,
    session_cookie="portal_agepar_session",
)
```

### 2.1. Atributos importantes

* `session_cookie="portal_agepar_session"`

  * Nome do cookie (único ponto de verdade para a sessão web).
* `secret_key=SESSION_SECRET`

  * Chave usada para **assinar** o conteúdo.
  * Vem de variável de ambiente `SESSION_SECRET`.
    Em dev (`docker-compose.dev.yml`), é `dev-secret`; em produção deve ser uma
    string longa, aleatória e mantida fora do repositório.
* `same_site="lax"`

  * Protege contra parte significativa de ataques CSRF:

    * cookie é enviado em navegações top-level e GET “normais”,
    * não é enviado em POSTs cross-site embutidos (ex.: formulário malicioso).
* `https_only=False`

  * No Starlette controla o flag `Secure` do cookie:

    * `False` → cookie pode trafegar em HTTP (apenas dev).
    * Em produção, é recomendável mudar para `True` (só HTTPS).
* `httponly=True` (padrão do SessionMiddleware)

  * JavaScript do frontend **não consegue ler ou escrever o cookie**:

    * reduz risco de exfiltração em XSS,
    * todo acesso é indireto via chamadas ao BFF (`/api/me`, etc).

Outros detalhes (defaults do middleware):

* `path="/"` → cookie é enviado para qualquer rota do domínio.
* `max_age` padrão é um intervalo longo; na prática, quem manda é o TTL da
  sessão em banco (`auth_sessions.expires_at`).

### 2.2. O que vai dentro do cookie?

O Starlette guarda um **dicionário serializado e assinado**. No nosso caso:

* sempre tem (quando autenticado):

  * `request.session["user"]` → snapshot do usuário,
  * `request.session["db_session_id"]` → ID da sessão em Postgres.
* pode ter outros campos pontuais (ex.: mocks de dev, CSRF token no futuro).

Exemplo aproximado da estrutura em memória:

```python
{
  "user": {
    "cpf": "00000000000",
    "nome": "Fulano Exemplo",
    "email": "fulano@example.org",
    "roles": ["user", "compras"],
    "unidades": ["AGEPAR"],
    "auth_mode": "local",
    "is_superuser": False,
    "must_change_password": False,
  },
  "db_session_id": "46f2420c-3af8-4c5e-b3dd-0f8e4d2b4c9f",
}
```

Importante:

* o browser **não é confiável**; por isso:

  * o cookie é **assinado** (`SESSION_SECRET`),
  * o `DbSessionMiddleware` ainda confere a existência da sessão em banco.

---

## 3) Sessão persistida em banco (`auth_sessions`)

O cookie não é a única fonte de verdade. A “sessão real” mora em:

```sql title="infra/sql/init_db.sql — tabela auth_sessions" showLineNumbers
CREATE TABLE IF NOT EXISTS auth_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  ip INET,
  user_agent TEXT,
  csrf_token UUID NOT NULL DEFAULT gen_random_uuid()
);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_user ON auth_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_exp ON auth_sessions (expires_at);
```

### 3.1. Criação no login

Na rota `/api/auth/login` (`apps/bff/app/auth/routes.py`):

```python title="routes.py — criação de sessão" showLineNumbers
sess_id = uuid.uuid4()
ttl = timedelta(days=REMEMBER_ME_TTL_DAYS) if payload.remember_me else timedelta(hours=SESSION_TTL_HOURS)
expires = _now() + ttl
cur.execute(
    """
    INSERT INTO auth_sessions (id, user_id, created_at, last_seen_at, expires_at, ip, user_agent)
    VALUES (%s, %s, now(), now(), %s, %s, %s)
    """,
    (str(sess_id), user_id, expires, ip, ua),
)

# payload "user" para o frontend
user_payload = { ... }

request.session.clear()
request.session["user"] = user_payload
request.session["db_session_id"] = str(sess_id)
```

Variáveis de ambiente relevantes:

* `SESSION_TTL_HOURS` (default: 8 horas)
* `REMEMBER_ME_TTL_DAYS` (default: 30 dias)
* `AUTH_REVOKE_ALL_ON_PASSWORD_CHANGE` (revogar todas as sessões na troca de senha)

### 3.2. Validação a cada requisição (DbSessionMiddleware)

O middleware `DbSessionMiddleware` (`apps/bff/app/auth/middleware.py`):

* roda **antes** das rotas,
* lê `request.session["db_session_id"]`,
* faz uma única query:

```sql
UPDATE auth_sessions
   SET last_seen_at = now(),
       expires_at   = CASE WHEN ... THEN ... ELSE expires_at END
 WHERE id = :db_session_id
   AND revoked_at IS NULL
   AND expires_at > now()
RETURNING user_id;
```

* se não voltar linha:

  * faz `request.session.clear()` (logout),
  * requisição segue, mas as rotas que dependem de `require_auth` vão devolver 401.
* se der erro de banco:

  * o erro é **suprimido** (design intencional para não “derrubar” o app),
  * a requisição segue com a sessão como estava (degradar graciosamente).

---

## 4) Login, `/api/me` e logout

### 4.1. Login (`POST /api/auth/login`)

Passos principais:

1. Valida credenciais e estado do usuário.
2. Cria linha em `auth_sessions` com TTL adequado.
3. Monta payload `LoginOut` com dados do usuário.
4. Preenche `request.session` (user + db_session_id).
5. Retorna 200 com JSON do usuário.

O Host usa isso em `apps/host/src/lib/api.ts`:

```ts title="apps/host/src/lib/api.ts — login" showLineNumbers
export async function loginWithPassword(params: {
  identifier: string;
  password: string;
  remember_me?: boolean;
}): Promise<User> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return jsonOrThrow<User>(res);
}
```

Repare em `credentials: "include"` → necessário para o browser enviar o cookie
`portal_agepar_session` em chamadas subsequentes.

### 4.2. `/api/me` — quem sou eu?

Rota em `main.py`:

```python title="apps/bff/app/main.py — /api/me" showLineNumbers
def _get_user_from_session(req: Request) -> Optional[Dict[str, Any]]:
    return req.session.get("user")

@APP.get("/api/me")
def get_me(request: Request) -> Dict[str, Any]:
    """
    Retorna o usuário autenticado na sessão.
    """
    user = _get_user_from_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user
```

O Host consome assim:

```ts title="apps/host/src/lib/api.ts — getMe" showLineNumbers
export async function getMe(): Promise<User> {
  const res = await fetch(`${API_BASE}/me`, {
    method: "GET",
    credentials: "include",
  });
  return jsonOrThrow<User>(res);
}
```

Se o cookie estiver ausente ou apontar para uma sessão inválida:

* `DbSessionMiddleware` provavelmente terá limpado `request.session`,
* `_get_user_from_session` volta `None`,
* `/api/me` responde `401 not authenticated`,
* o Host trata 401 redirecionando para a tela de login.

### 4.3. Logout (`POST /api/auth/logout`)

Também em `routes.py`:

* Lê `db_session_id` da sessão.
* Marca `revoked_at = now()` em `auth_sessions`.
* Limpa `request.session.clear()`.
* Retorna `204 No Content`.

No Host:

```ts title="apps/host/src/lib/api.ts — logout" showLineNumbers
export async function logout(): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  await ensureOkOrThrow(res);
}
```

---

## 5) Segurança: por que cookies de sessão (e não JWT solto)?

Resumo das escolhas de design:

* **Cookie HTTP-only assinado**:

  * não expõe token legível ou manipulável por JS,
  * protege contra muitas classes de vazamento.
* **Sessão em banco (`auth_sessions`)**:

  * permite revogação server-side (logout em todos dispositivos),
  * facilita políticas como “revogar tudo na troca de senha”,
  * guarda IP, user-agent e CSRF token (para usos futuros).
* **Middleware de sessão**:

  * aplica sliding expiration (se configurado),
  * limpa sessão em caso de expiração/revogação,
  * não injeta 401/403 por conta própria → responsabilidade continua nas rotas.

Consequências:

* Se alguém tentar **forjar** um cookie:

  * precisa conhecer `SESSION_SECRET` para passar pela assinatura;
  * ainda precisaria de uma `auth_sessions.id` válida e não revogada.
* Se `SESSION_SECRET` vazar:

  * há risco de elevação de privilégio forjando o `user.roles` no cookie;
  * por isso:

    * o secret **não deve** ficar no repositório,
    * em produção deve ser longo e rotacionável.

---

## 6) Boas práticas e recomendações

Para evoluções futuras:

1. **Produção sempre com HTTPS + `https_only=True`**

   * Idealmente ajustar no `main.py`:

     ```python
     https_only=True  # em clusters atrás de HTTPS
     ```
   * E garantir TLS em todos os acessos externos.

2. **Segredo forte em `SESSION_SECRET`**

   * Pelo menos 32 caracteres aleatórios.
   * Configurado via segredo de ambiente (Kubernetes Secret, Vault, etc.).
   * Nunca commitar o valor real no repositório.

3. **Não guardar dados sensíveis na sessão**

   * Nada de senhas, tokens externos, documentos inteiros.
   * Apenas:

     * identificadores (`user_id`, `db_session_id`),
     * snapshot mínimo do usuário,
     * flags de controle (ex.: `must_change_password`).

4. **Tratar `/api/me` como fonte de verdade para o Host**

   * O Host sempre deveria revalidar sessão no carregamento da aplicação.
   * Em mudanças de roles sensíveis (ex.: admin removido), basta revogar
     sessões e o novo login refletirá o estado atualizado.

---

## 7) Exemplos práticos de teste

### 7.1. Ver cookie no navegador (dev)

1. Rodar stack dev (`./infra/scripts/dev_up.sh`).
2. Acessar `http://localhost:5173`.
3. Fazer login com usuário dev.
4. DevTools → `Application` → `Cookies` → `http://localhost:5173`:

   * nome: `portal_agepar_session`
   * `HttpOnly`: `true`
   * `SameSite`: `Lax`
   * `Secure`: `false` (dev)

### 7.2. Testar `/api/me` via cURL (reutilizando cookie)

```bash title="Login + uso da sessão em cURL" showLineNumbers
# Login (captura o cookie de sessão)
curl -i -c /tmp/cookies.txt \
  -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"dev@example.com","password":"dev"}'

# Chamada autenticada reaproveitando o cookie
curl -i -b /tmp/cookies.txt http://localhost:8000/api/me
```

Se tudo deu certo, o segundo comando deve retornar um JSON com os dados do usuário.

---

> _Criado em 2025-12-01_