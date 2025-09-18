# Configuração do BFF (FastAPI)

Este documento detalha a configuração do **Backend for Frontend (BFF)** do Portal AGEPAR, incluindo variáveis de ambiente, middlewares, inicialização do banco de dados e padrões de segurança.

---

## ⚙️ Variáveis de Ambiente

O BFF utiliza variáveis de ambiente para controlar sua configuração.  

### 🔹 Principais variáveis

| Variável               | Descrição                                    | Default             |
|------------------------|----------------------------------------------|---------------------|
| `BFF_HOST`             | Host de escuta do FastAPI                   | `0.0.0.0`           |
| `BFF_PORT`             | Porta do serviço FastAPI                    | `8000`              |
| `DATABASE_URL`         | URL do banco (Postgres ou SQLite)           | `sqlite:///./db.sqlite` |
| `SESSION_SECRET_KEY`   | Chave secreta para assinar cookies           | `changeme`          |
| `SESSION_EXPIRATION`   | Tempo de expiração de sessão (segundos)      | `3600`              |
| `CORS_ALLOWED_ORIGINS` | Lista de origens permitidas para CORS        | `http://localhost:5173` |

---

## 🧩 Middlewares

O BFF aplica os seguintes middlewares padrão:

- **CORS Middleware**
  - Permite apenas origens configuradas em `CORS_ALLOWED_ORIGINS`.  
  - Métodos e cabeçalhos controlados.  

- **Session Middleware**
  - Gera e valida cookies de sessão.  
  - Baseado em `SESSION_SECRET_KEY`.  

- **Logging Middleware**
  - Registra requisições (INFO) e erros (ERROR).  
  - Inclui contexto (rota, usuário, payload resumido).  

---

## 🗄️ Banco de Dados

### Inicialização
- Executada em `startup` via `init_db()`.  
- Cria tabelas padrão se não existirem:  
  - `submissions` → submissões de automações.  
  - `audits` → auditoria de eventos.  

### Conexão
- **SQLite** em desenvolvimento (arquivo local).  
- **Postgres** em produção (via `DATABASE_URL`).  
- Pool de conexões configurado para performance.  

---

## 🔐 Segurança

- **Sessões baseadas em cookies** (não JWT).  
- **RBAC simples** → cada bloco pode definir `requiredRoles`.  
- **Validações Pydantic v2** → `extra="ignore"` para evitar erros triviais.  
- **Erros claros e consistentes** →  
  - `400` → entrada inválida  
  - `401` → não autenticado  
  - `403` → sem permissão  
  - `404` → recurso não encontrado  
  - `409` → conflito  
  - `422` → erro de validação  

---

## 🔄 Fluxo de Startup

```mermaid
flowchart TD
    A[FastAPI app] --> B[Load Config]
    B --> C[Middlewares]
    C --> D[Init DB]
    D --> E[Load Routes]
    E --> F[Ready]
````

---

## 🧪 Comando para rodar localmente

```bash
uvicorn apps.bff.app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

📖 **Próximo passo:** [Logging e Observabilidade](logging-observabilidade.md)
