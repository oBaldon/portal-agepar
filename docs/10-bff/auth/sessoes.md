# Sessões de Autenticação no BFF

O **BFF (FastAPI)** do Portal AGEPAR utiliza **sessões baseadas em cookies** para autenticação de usuários.  
As sessões são persistidas no banco de dados e validadas a cada requisição.

---

## 🎯 Objetivos

- Manter o estado de login do usuário de forma **segura e simples**.  
- Controlar expiração automática de sessões.  
- Permitir futura gestão de **múltiplas sessões por usuário**.  
- Garantir rastreabilidade via **auditoria**.  

---

## 📂 Estrutura da Sessão

Tabela `sessions` (exemplo de colunas):

| Campo        | Tipo       | Descrição                             |
|--------------|-----------|---------------------------------------|
| `id`         | string    | Identificador único da sessão          |
| `user_id`    | string    | ID do usuário associado                |
| `roles`      | json[]    | Lista de roles da sessão               |
| `ip`         | string    | IP do cliente (opcional)              |
| `user_agent` | string    | Navegador/cliente (opcional)          |
| `created_at` | datetime  | Data/hora de criação                   |
| `expires_at` | datetime  | Data/hora de expiração                 |
| `revoked`    | boolean   | Se a sessão foi revogada               |

---

## 🔑 Cookies

- Nome do cookie: **`session`**  
- Configuração:
  - `HttpOnly` → impede acesso via JavaScript (protege contra XSS).  
  - `Secure` → ativado em produção (requer HTTPS).  
  - `SameSite=Lax` → default; pode ser `Strict` em cenários de maior restrição.  
  - `Path=/` → válido para toda a aplicação.  
  - `Max-Age` → configurado por `SESSION_EXPIRATION` (ex.: `3600s`).  
- **Rolling session:** expiração é renovada a cada requisição válida.  

---

## 📊 Ciclo de Vida da Sessão

1. Usuário envia credenciais em `/api/auth/login`.  
2. BFF valida e cria registro em `sessions`.  
3. Cookie de sessão (`session`) é enviado ao cliente.  
4. Cliente envia cookie em cada requisição autenticada.  
5. BFF valida sessão contra DB:  
   - Se válida → prossegue.  
   - Se expirada ou revogada → `401 Unauthorized`.  
6. Sessão pode ser encerrada via `/api/auth/logout`.  

---

## 🔄 Diagrama de Fluxo

```mermaid
sequenceDiagram
    participant U as Usuário
    participant B as BFF
    participant DB as Banco (sessions)

    U->>B: POST /api/auth/login {credenciais}
    B->>DB: Criar sessão
    DB-->>B: Sessão criada
    B-->>U: Set-Cookie: session=...

    U->>B: GET /api/me (Cookie)
    B->>DB: Valida sessão
    DB-->>B: Sessão válida
    B-->>U: Perfil usuário

    U->>B: POST /api/auth/logout
    B->>DB: Revoga sessão
    DB-->>B: Sessão encerrada
    B-->>U: 204 No Content
````

---

## 🚀 Futuro

* **Múltiplas sessões por usuário**

  * `GET /api/auth/sessions` → listar sessões ativas
  * `DELETE /api/auth/sessions/{id}` → encerrar sessão específica

* **Escalabilidade**

  * Suporte a Redis ou outro store distribuído para sessões em múltiplas instâncias.

* **Segurança Avançada**

  * Notificação em tempo real de logout remoto.
  * Sessões vinculadas a fingerprint de dispositivo.

---

📖 Próximo: [Banco de Dados – Schema](../database/schema.md)
