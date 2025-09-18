# Autenticação no BFF – Visão Geral

O **BFF (FastAPI)** do Portal AGEPAR implementa autenticação baseada em **sessões HTTP**, com suporte a **cookies seguros** e **RBAC simples** (Role-Based Access Control).

---

## 🎯 Objetivos

- Garantir **segurança e simplicidade** no login/logout.  
- Usar **cookies de sessão** em vez de tokens JWT.  
- Manter o estado do usuário no servidor (facilitando RBAC).  
- Permitir futura integração com **provedores de identidade externos**.  

---

## 📌 Como funciona

1. O usuário envia **credenciais** via `POST /api/auth/login`.  
2. O servidor valida e cria uma **sessão** no banco.  
3. Um **cookie de sessão** é retornado ao cliente (`HttpOnly`, `Secure`).  
4. O cliente usa o cookie em chamadas subsequentes (`/api/me`, automations, catálogo protegido).  
5. O usuário pode encerrar a sessão com `POST /api/auth/logout`.  

---

## 🔑 Sessões

- Cada sessão é persistida em tabela de banco (`sessions` ou equivalente).  
- Contém:
  - `id` da sessão  
  - `user_id`  
  - `roles`  
  - `expiração` (default: 3600s)  
- Cookies são renovados em **cada requisição válida** (rolling session).  

---

## 🧩 RBAC

- Implementação **simples**:  
  - Blocos no catálogo definem `requiredRoles`.  
  - O frontend filtra blocos via helper `userCanSeeBlock(user, block)`.  
  - O backend valida novamente roles ao processar requisições sensíveis.  

---

## 📊 Fluxo de Autenticação

```mermaid
sequenceDiagram
    participant U as Usuário
    participant H as Host (Frontend)
    participant B as BFF (FastAPI)
    participant DB as Banco de Dados

    U->>H: Acessa login
    H->>B: POST /api/auth/login
    B->>DB: Valida credenciais
    DB-->>B: Ok
    B-->>H: Cookie de sessão (HttpOnly)

    U->>H: Navega
    H->>B: GET /api/me (com cookie)
    B->>DB: Valida sessão
    DB-->>B: Sessão válida
    B-->>H: Dados do usuário
````

---

## ⚠️ Considerações de Segurança

* Cookies `HttpOnly` → não acessíveis via JavaScript.
* Cookies `Secure` em produção → apenas transmitidos via HTTPS.
* **Senhas nunca são logadas**.
* Mensagens de erro de login são **genéricas** (evitar exposição de existência de usuário).

---

📖 **Próximo passo:** [Rotas de Autenticação](rotas.md)
