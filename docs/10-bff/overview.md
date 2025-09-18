# Backend (BFF) – Visão Geral

O **BFF (Backend for Frontend)** do Portal AGEPAR é construído em **FastAPI** e funciona como camada intermediária entre o **Host (frontend)**, o **catálogo de automações**, o **banco de dados** e os **módulos de automação**.

---

## 🎯 Objetivos do BFF

- **Unificar a comunicação** do frontend com o backend.  
- **Gerenciar autenticação e RBAC** (Role-Based Access Control).  
- **Fornecer endpoints modulares** para automações.  
- **Persistir e auditar** submissões e eventos do sistema.  
- **Servir o catálogo** para guiar a navegação no frontend.  

---

## ⚙️ Principais Responsabilidades

- **Autenticação & Sessões**
  - Endpoints em `/api/auth/*`  
  - Cookies de sessão (mock em dev, real em produção)  
  - RBAC simples, baseado em roles  

- **Catálogo**
  - Servido em `/catalog/*`  
  - Estrutura em JSON com categorias, blocos e permissões  

- **Automations**
  - Cada automação é um **módulo independente**  
  - Endpoints padrão:  
    - `GET /schema`  
    - `GET /ui`  
    - `POST /submit`  
    - `GET /submissions`  
    - `GET /submissions/{id}`  
    - `POST /submissions/{id}/download`  
  - Persistência de submissões em tabela `submissions`  
  - Auditoria em tabela `audits`  

- **Banco de Dados**
  - SQLite (desenvolvimento)  
  - Postgres (produção)  
  - Inicialização automática (`init_db`)  

---

## 🔄 Fluxo de Requisições

```mermaid
sequenceDiagram
    participant U as Usuário (Host)
    participant B as BFF (FastAPI)
    participant DB as Banco de Dados

    U->>B: Login (POST /api/auth/login)
    B->>DB: Valida credenciais e cria sessão
    DB-->>B: Sessão registrada
    B-->>U: Cookie de sessão

    U->>B: Requisição Catálogo (/catalog/dev)
    B->>DB: Lê categorias e blocos
    B-->>U: Retorna JSON catálogo

    U->>B: Submissão Automação (/api/automations/{slug}/submit)
    B->>DB: Persiste submissão
    B-->>U: Confirmação + ID
    B->>DB: Audita evento
````

---

## 📂 Estrutura do Código

```plaintext
apps/bff/app/
├── api/             # Rotas globais (auth, catalog, health)
├── automations/     # Automations isoladas (form2json, dfd, etc.)
├── core/            # Configuração, middlewares, logging
├── db/              # Modelos e inicialização do banco
├── utils/           # Funções auxiliares
└── main.py          # Ponto de entrada FastAPI
```

---

## 📊 Observabilidade

* **Logs estruturados** (`INFO`, `ERROR`)
* **Mensagens de erro claras** → 400, 401, 403, 404, 422, 500
* **Auditoria completa** em `audits`

---

## 🚀 Próximos Passos

* Detalhar [Configuração](configuracao.md)
* Definir [Logging e Observabilidade](logging-observabilidade.md)
* Documentar [Erros e Status](erros-e-status.md)
* Explorar [API](api/health-version.md) e [Automations](automations/index.md)

