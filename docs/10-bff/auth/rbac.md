# RBAC – Role-Based Access Control

O Portal AGEPAR utiliza um modelo de **RBAC simples** para restringir acesso a blocos e endpoints do BFF.

---

## 🎯 Objetivo

- Garantir que **usuários só acessem blocos e automações autorizados**.  
- Permitir que o **frontend filtre blocos** com base nas roles.  
- Reforçar a segurança com **validação no backend**.  

---

## 📌 Conceito

Cada **usuário** possui um conjunto de **roles** atribuídas no login.  
Cada **bloco do catálogo** pode especificar `requiredRoles`.

- **Frontend:** usa o helper `userCanSeeBlock(user, block)` para ocultar blocos.  
- **Backend:** valida roles antes de executar ações restritas.  

---

## 🔑 Exemplo de Catálogo com RBAC

```json
{
  "id": "dfd",
  "label": "DFD",
  "categoryId": "compras",
  "requiredRoles": ["admin", "compras"],
  "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" },
  "routes": ["/dfd"],
  "navigation": [{ "path": "/dfd", "label": "DFD" }]
}
````

Neste exemplo:

* O bloco só é exibido para usuários com role **`admin`** ou **`compras`**.
* Se o usuário não tiver role necessária, o frontend oculta o bloco.
* Mesmo que o usuário tente acessar a rota diretamente, o **BFF bloqueia com `403 Forbidden`**.

---

## ⚙️ Validação no Frontend

Helper `userCanSeeBlock(user, block)`:

* Retorna **true** se o usuário tiver pelo menos uma role em `requiredRoles`.
* Se `requiredRoles` não existir, o bloco é público (ex.: login).

---

## ⚙️ Validação no Backend

Cada rota sensível deve verificar roles:

```python
def user_has_role(user, required_roles: list[str]) -> bool:
    return any(role in user.roles for role in required_roles)
```

* Se falhar, retornar:

```json
{
  "status": "error",
  "code": 403,
  "message": "Você não possui permissão para acessar este recurso"
}
```

---

## 📊 Fluxo RBAC

```mermaid
flowchart LR
    U[Usuário] --> H[Host (frontend)]
    H -->|Catálogo filtrado| U
    U --> BFF
    BFF -->|Valida roles| RBAC
    RBAC -->|Permissão OK| Auto[Automação]
    RBAC -->|403 Forbidden| U
```

---

## 🚀 Próximos Passos

* Definir roles padrão (`admin`, `compras`, `gestao`, etc.).
* Criar política de **herança de roles** (futuro).
* Implementar logs de auditoria para acessos negados.

📖 Próximo: [Sessões](sessoes.md)

````

---

### **`docs/10-bff/auth/sessoes.md`**

```markdown
# Sessões no BFF

A autenticação no Portal AGEPAR é baseada em **sessões persistidas no banco** e gerenciadas via **cookies seguros**.

---

## 🎯 Objetivos

- Manter o estado de autenticação no servidor.  
- Permitir **expiração e invalidação** de sessões.  
- Preparar suporte para **gestão de múltiplas sessões por usuário**.  

---

## 📂 Estrutura da Sessão

Tabela `sessions` (ou equivalente):

| Campo        | Tipo       | Descrição                             |
|--------------|-----------|---------------------------------------|
| `id`         | string    | Identificador único da sessão          |
| `user_id`    | string    | Usuário associado                     |
| `roles`      | json[]    | Roles ativas da sessão                 |
| `ip`         | string    | IP do cliente (opcional)              |
| `user_agent` | string    | Navegador/cliente (opcional)          |
| `created_at` | datetime  | Data/hora de criação                   |
| `expires_at` | datetime  | Data/hora de expiração                 |
| `revoked`    | boolean   | Se a sessão foi revogada               |

---

## 🔑 Cookies

- Nome: `session`  
- Flags:  
  - `HttpOnly` → protege contra XSS.  
  - `Secure` → habilitado em produção (HTTPS).  
  - `SameSite=Lax` (ou `Strict` quando possível).  
- `Max-Age` controlado pela variável `SESSION_EXPIRATION` (default: 3600s).  
- **Rolling session**: cada requisição válida renova a expiração.  

---

## 📊 Ciclo de Vida

1. Usuário faz login → sessão criada no banco.  
2. Cookie de sessão enviado ao cliente.  
3. Cliente usa cookie em requisições subsequentes.  
4. Sessão expira automaticamente após timeout.  
5. Usuário pode encerrar sessão via `POST /api/auth/logout`.  

---

## 🔄 Fluxo de Sessão

```mermaid
flowchart TD
    Login[Login] --> SessaoCriada[Sessão criada no DB]
    SessaoCriada --> Cookie[Cookie de sessão emitido]
    Cookie --> Request[Requisições autenticadas]
    Request --> Renovacao[Renovação de expiração]
    Request --> Expiracao[Expiração ou logout]
````

---

## 🚀 Futuro

* **Múltiplas sessões por usuário**

  * `/api/auth/sessions` → listar todas
  * `DELETE /api/auth/sessions/{id}` → encerrar sessão específica

* **Integração com Redis**

  * Para escalabilidade em múltiplas instâncias do BFF.

* **Notificação de logout remoto**

  * Encerrar sessão em tempo real em todos os dispositivos.

---

📖 Próximo: [Banco de Dados – Schema](../database/schema.md)

```