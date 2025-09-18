# Rotas de Autenticação (BFF)

Documenta as rotas de **login**, **logout**, **identidade do usuário** e a rota futura de **gestão de sessões**.  
Autenticação é **stateful**, baseada em **cookies de sessão** emitidos pelo BFF.

> Base path: `/api/auth/*` (exceto `/api/me`)

---

## Sumário Rápido

| Rota                       | Método | Auth | Descrição                               | Códigos |
|---------------------------|--------|------|-----------------------------------------|---------|
| `/api/auth/login`         | POST   | ❌   | Autentica e cria cookie de sessão       | 200, 400, 401, 429 |
| `/api/auth/logout`        | POST   | ✅   | Encerra a sessão atual                  | 204, 401 |
| `/api/me`                 | GET    | ✅   | Retorna dados do usuário autenticado    | 200, 401 |
| `/api/auth/sessions`      | GET    | ✅   | **(Futuro)** Lista sessões ativas       | 200, 401 |
| `/api/auth/sessions/{id}` | DELETE | ✅   | **(Futuro)** Encerra sessão específica  | 204, 401, 404 |

---

## Modelo de Erro (padrão)

```json
{
  "status": "error",
  "code": 401,
  "message": "Sessão inválida ou expirada",
  "details": null
}
````

---

## `POST /api/auth/login`

Autentica o usuário e emite **cookie de sessão** (`Set-Cookie`).

### Request

* Headers: `Content-Type: application/json`
* Body (schema):

```json
{
  "username": "joao",
  "password": "senha123"
}
```

> Validação: ambos obrigatórios (strings não vazias).

### Responses

* `200 OK`

  * Headers:

    * `Set-Cookie: session=<opaque>; HttpOnly; SameSite=Lax; Path=/; Max-Age=3600; Secure*`
    * `Cache-Control: no-store`
  * Body:

    ```json
    {
      "status": "success",
      "user": {
        "id": "u123",
        "username": "joao",
        "roles": ["admin", "compras"]
      }
    }
    ```
* `400 Bad Request` – payload inválido (ex.: tipos errados, campos ausentes).
* `401 Unauthorized` – credenciais inválidas (mensagem genérica).
* `429 Too Many Requests` – se rate limit estiver habilitado.

### Observações de Segurança

* Mensagens de erro de login **não** indicam se usuário existe.
* Senhas **nunca** são logadas.
* Em produção, o cookie tem `Secure` e, se possível, `SameSite=Strict`.

### Exemplos

**curl**

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"joao","password":"senha123"}' \
  -c cookies.txt -i
```

**HTTPie**

```bash
http -v POST :8000/api/auth/login username=joao password=senha123 --download --session=me
```

---

## `POST /api/auth/logout`

Encerra a **sessão atual**, invalidando o cookie.

### Request

* Headers: incluir cookie de sessão (`Cookie: session=...`)

### Responses

* `204 No Content`

  * Headers:

    * `Set-Cookie: session=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax; Secure*`
    * `Cache-Control: no-store`
* `401 Unauthorized` – sessão ausente ou inválida.

### Exemplo

```bash
curl -X POST http://localhost:8000/api/auth/logout -b cookies.txt -i
```

---

## `GET /api/me`

Retorna o **perfil** do usuário autenticado.

### Request

* Headers: `Cookie: session=...`

### Responses

* `200 OK`

  ```json
  {
    "id": "u123",
    "username": "joao",
    "roles": ["admin", "compras"]
  }
  ```
* `401 Unauthorized`

  ```json
  {
    "status": "error",
    "code": 401,
    "message": "Sessão inválida ou expirada"
  }
  ```

### Exemplo

```bash
curl http://localhost:8000/api/me -b cookies.txt -i
```

---

## (Futuro) Gestão de Sessões

### `GET /api/auth/sessions`

Lista sessões ativas do usuário.

* `200 OK`

  ```json
  [
    {
      "session_id": "s_abc",
      "created_at": "2025-09-16T12:00:00Z",
      "expires_at": "2025-09-16T13:00:00Z",
      "ip": "203.0.113.10",
      "user_agent": "Mozilla/5.0 ..."
    }
  ]
  ```
* `401 Unauthorized`

### `DELETE /api/auth/sessions/{id}`

Encerra uma sessão específica do próprio usuário.

* `204 No Content`
* `401 Unauthorized`
* `404 Not Found` – sessão não existe ou não pertence ao usuário.

---

## Política de Cookies

* `HttpOnly`: **sempre** (mitiga XSS).
* `Secure`: **produção** (requer HTTPS).
* `SameSite`: `Lax` (sugestão) ou `Strict` quando viável.
* `Path`: `/`
* `Max-Age`: controlado por `SESSION_EXPIRATION` (ex.: `3600` segundos).
* **Rolling session**: renovação do `Max-Age` a cada requisição válida (configurável).

---

## Considerações de Segurança

* **CSRF**: como a API é consumida pelo mesmo domínio (proxy do Host), `SameSite` + `HttpOnly` reduzem superfície; para cenários cross-site, usar **CSRF token** (header `X-CSRF-Token`) e **preflight**.
* **Rate limiting**: recomendado em `/api/auth/login` (ex.: 5 req/min/IP + cooldown).
* **Lockout progressivo**: opcional; evitar lockout global por usuário (risco de DoS).
* **Auditoria**: registrar `login_success`, `login_failure`, `logout`, `session_invalidated`.
* **Headers de segurança**: `Cache-Control: no-store`, `Pragma: no-cache` em rotas sensíveis.

---

## Diagrama de Fluxo

```mermaid
sequenceDiagram
    participant C as Cliente (Host)
    participant A as BFF Auth
    participant DB as Sessões/Usuários

    C->>A: POST /api/auth/login {username, password}
    A->>DB: valida credenciais
    DB-->>A: ok
    A-->>C: 200 + Set-Cookie: session=...
    Note over C,A: Cliente usa cookie em chamadas subsequentes

    C->>A: GET /api/me (Cookie: session=...)
    A->>DB: valida sessão
    DB-->>A: sessão válida
    A-->>C: 200 {id, username, roles}

    C->>A: POST /api/auth/logout (Cookie)
    A->>DB: invalida sessão
    A-->>C: 204 + Set-Cookie: session=; Max-Age=0
```

---

## Testes Rápidos (cURL)

```bash
# Login
curl -X POST :8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"joao","password":"senha123"}' -c cookies.txt -i

# Me
curl :8000/api/me -b cookies.txt -i

# Logout
curl -X POST :8000/api/auth/logout -b cookies.txt -i
```

---

## Referências Internas

* [API – Autenticação (geral)](../api/auth.md)
* [RBAC](rbac.md)
* [Sessões](sessoes.md)

