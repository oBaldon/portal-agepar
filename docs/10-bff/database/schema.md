# Banco de Dados – Schema

O **BFF (FastAPI)** utiliza um banco de dados relacional para persistir **submissões, auditorias e sessões**.  
Em desenvolvimento é usado **SQLite**, enquanto em produção o banco é **Postgres**.

---

## 🎯 Objetivos

- Garantir **persistência confiável** das informações.  
- Suportar **auditoria e rastreabilidade** de eventos.  
- Facilitar consultas para relatórios e integrações futuras.  
- Manter **compatibilidade entre SQLite e Postgres**.  

---

## 📂 Tabelas Principais

### 🔹 `submissions`
Armazena as submissões de automações.

| Campo          | Tipo       | Descrição |
|----------------|-----------|-----------|
| `id`           | integer PK | Identificador único da submissão |
| `automation_slug` | string  | Identificador da automação (`dfd`, `form2json`, etc.) |
| `payload`      | json      | Dados enviados pelo usuário |
| `status`       | string    | Estado da submissão (`pending`, `processing`, `success`, `error`) |
| `result`       | json      | Resultado da automação (ex.: caminho do arquivo) |
| `error`        | string    | Mensagem de erro, se falha |
| `created_at`   | datetime  | Data/hora da criação |
| `updated_at`   | datetime  | Última atualização |

---

### 🔹 `audits`
Armazena eventos importantes para rastreabilidade.

| Campo        | Tipo       | Descrição |
|--------------|-----------|-----------|
| `id`         | integer PK | Identificador único |
| `timestamp`  | datetime   | Momento do evento |
| `user_id`    | string     | Usuário associado (ou `anonymous`) |
| `action`     | string     | Tipo de ação (`login_success`, `automation_submit`, etc.) |
| `status`     | string     | `success` ou `failure` |
| `details`    | json       | Dados adicionais sobre o evento |

---

### 🔹 `sessions`
Gerencia sessões autenticadas do usuário.

| Campo        | Tipo       | Descrição |
|--------------|-----------|-----------|
| `id`         | string PK | Identificador único da sessão |
| `user_id`    | string    | Usuário autenticado |
| `roles`      | json[]    | Roles da sessão |
| `ip`         | string    | IP do cliente (opcional) |
| `user_agent` | string    | Agente do usuário (opcional) |
| `created_at` | datetime  | Criação da sessão |
| `expires_at` | datetime  | Expiração configurada |
| `revoked`    | boolean   | Se a sessão foi revogada |

---

## 🔄 Relacionamentos

```mermaid
erDiagram
    submissions {
        int id PK
        string automation_slug
        json payload
        string status
        json result
        string error
        datetime created_at
        datetime updated_at
    }

    audits {
        int id PK
        datetime timestamp
        string user_id
        string action
        string status
        json details
    }

    sessions {
        string id PK
        string user_id
        json roles
        string ip
        string user_agent
        datetime created_at
        datetime expires_at
        boolean revoked
    }

    submissions ||--o{ audits : "auditado por"
    sessions ||--o{ audits : "eventos relacionados"
````

---

## 📌 Migrações

* Usar **Alembic** para controle de versão do schema.
* Migrações devem ser compatíveis com **SQLite (dev)** e **Postgres (prod)**.
* Scripts de inicialização (`init_db`) devem garantir:

  * Criação das tabelas mínimas (`submissions`, `audits`, `sessions`).
  * Inserção de registros iniciais, se aplicável.

---

## 🚀 Futuro

* Indexar campos de pesquisa frequente (`automation_slug`, `status`, `created_at`).
* Criar **tabela de usuários** (quando houver autenticação real).
* Implementar **sharding ou particionamento** em submissões, se volume crescer.

---

📖 Próximo: [Conexão e Pool](conexao-e-pool.md)
