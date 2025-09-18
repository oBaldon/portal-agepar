# API – Autenticação e Sessões

O **BFF (FastAPI)** do Portal AGEPAR implementa autenticação baseada em **sessões via cookies**, com suporte a **RBAC simples** (Role-Based Access Control).

---

## 📌 Endpoints

### 🔹 `POST /api/auth/login`
- **Descrição:** Realiza login do usuário.  
- **Request Exemplo:**
```json
{
  "username": "joao",
  "password": "senha123"
}
````

* **Resposta Exemplo:**

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

* **Efeito:** Cria cookie de sessão (`HttpOnly`, `Secure` em produção).

---

### 🔹 `POST /api/auth/logout`

* **Descrição:** Finaliza sessão do usuário.
* **Resposta Exemplo:**

```json
{
  "status": "success",
  "message": "Sessão encerrada"
}
```

* **Efeito:** Invalida cookie de sessão.

---

### 🔹 `GET /api/me`

* **Descrição:** Retorna dados do usuário autenticado.
* **Resposta Exemplo:**

```json
{
  "id": "u123",
  "username": "joao",
  "roles": ["admin", "compras"]
}
```

* **Erro:** Se sessão inválida/expirada → `401 Unauthorized`.

---

### 🔹 `GET /api/auth/sessions`

* **Descrição:** Lista sessões ativas do usuário (futuro).
* **Uso:** Permitirá encerrar sessões específicas.

---

## 🔑 RBAC (Role-Based Access Control)

O RBAC é **simples e baseado em roles** atribuídas ao usuário.

* Cada **bloco do catálogo** pode ter um campo `requiredRoles`.
* O frontend usa o helper `userCanSeeBlock(user, block)`.
* O backend reforça validação nos endpoints protegidos.

### Exemplo de Bloco no Catálogo

```json
{
  "id": "dfd",
  "label": "DFD",
  "requiredRoles": ["admin", "compras"],
  "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" }
}
```

---

## 🧪 Testes de Exemplo

### Login

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"joao","password":"senha123"}' \
  -c cookies.txt
```

### Consultar usuário logado

```bash
curl http://localhost:8000/api/me -b cookies.txt
```

### Logout

```bash
curl -X POST http://localhost:8000/api/auth/logout -b cookies.txt
```

---

## 🚀 Próximos Passos

* Detalhar [Autenticação](../auth/overview.md)
* Documentar [RBAC](../auth/rbac.md)
* Explicar [Sessões](../auth/sessoes.md)
