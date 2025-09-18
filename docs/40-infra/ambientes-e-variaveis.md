# Infra – Ambientes e Variáveis

Este documento descreve os **ambientes do Portal AGEPAR** e as **variáveis de configuração** utilizadas no BFF, Host e Docs.

---

## 🎯 Objetivos

- Padronizar nomes e valores de ambientes.  
- Separar configuração de **infra** e **aplicação**.  
- Garantir que todos os serviços funcionem em **dev**, **homolog** e **prod** sem alterações manuais.  

---

## 🌍 Ambientes

### 1. Desenvolvimento (`dev`)
- Executado via **Docker Compose** local.  
- Banco: SQLite (persistência simples).  
- Catálogo: `/catalog/dev` (pode incluir blocos experimentais).  
- Auth: mock simples (`/api/auth/login`).  
- Observabilidade mínima (logs console).

### 2. Homologação (`stage`)
- Implantado em cluster de homologação.  
- Banco: PostgreSQL compartilhado.  
- Catálogo: `/catalog/prod` com RBAC aplicado.  
- Integrações externas apontam para **sandboxes**.  
- Logs coletados em stack observabilidade (ELK/Prometheus).  

### 3. Produção (`prod`)
- Implantado em cluster de produção.  
- Banco: PostgreSQL dedicado.  
- Catálogo: `/catalog/prod` somente blocos liberados.  
- Autenticação e RBAC obrigatórios.  
- Observabilidade completa (tracing, métricas, alertas).  

---

## 📦 Variáveis Comuns

| Variável                | Serviço | Descrição |
|--------------------------|---------|-----------|
| `ENV`                   | BFF, Host | Define ambiente (`dev`, `stage`, `prod`) |
| `PORT`                  | Todos   | Porta de exposição do serviço |
| `CORS_ALLOWED_ORIGINS`  | BFF     | Lista de origens permitidas em CORS (ex.: `http://localhost:5173`) |
| `SESSION_SECRET`        | BFF     | Chave para assinar cookies de sessão |
| `SESSION_COOKIE_NAME`   | BFF     | Nome do cookie de sessão (ex.: `agepar_session`) |
| `DB_URL`                | BFF     | String de conexão ao banco (Postgres ou SQLite) |
| `LOG_LEVEL`             | Todos   | Nível de logs (`info`, `debug`, `error`) |

---

## 🖥️ Variáveis do Host

| Variável             | Descrição |
|-----------------------|-----------|
| `VITE_API_BASE`       | Path base da API (default: `/api`) |
| `VITE_CATALOG_BASE`   | Path base do catálogo (default: `/catalog`) |
| `VITE_DOCS_BASE`      | Path base da documentação (default: `/docs`) |

> O Host **sempre usa paths relativos** (proxies resolvem em dev; reverse proxy em prod).  

---

## 📑 Variáveis do Docs (MkDocs)

| Variável        | Descrição |
|------------------|-----------|
| `MKDOCS_PORT`    | Porta do servidor interno (default: 8000) |
| `SITE_NAME`      | Nome do portal de documentação |
| `THEME`          | Tema Material configurado em `mkdocs.yml` |

---

## 🐳 Exemplo `.env.dev`

```env
# BFF
ENV=dev
PORT=8000
CORS_ALLOWED_ORIGINS=http://localhost:5173
SESSION_SECRET=dev-secret
SESSION_COOKIE_NAME=agepar_session
DB_URL=sqlite:///./dev.db
LOG_LEVEL=debug

# Host
VITE_API_BASE=/api
VITE_CATALOG_BASE=/catalog
VITE_DOCS_BASE=/docs

# Docs
MKDOCS_PORT=8000
SITE_NAME="Portal AGEPAR Docs (Dev)"
THEME=material
````

---

## 🐳 Exemplo `.env.prod`

```env
# BFF
ENV=prod
PORT=8000
CORS_ALLOWED_ORIGINS=https://portal.agepar.gov.br
SESSION_SECRET=${SESSION_SECRET_FROM_VAULT}
SESSION_COOKIE_NAME=agepar_session
DB_URL=postgresql+psycopg2://user:pass@db-prod/agepar
LOG_LEVEL=info

# Host
VITE_API_BASE=/api
VITE_CATALOG_BASE=/catalog
VITE_DOCS_BASE=/docs

# Docs
MKDOCS_PORT=8000
SITE_NAME="Portal AGEPAR"
THEME=material
```

---

## 🛡️ Segurança

* **Segredos não versionados**: nunca commitar valores de `SESSION_SECRET`, credenciais de banco ou chaves externas.
* **Vault**: usar serviço de cofre (HashiCorp Vault, AWS Secrets Manager, etc.).
* **CORS restrito**: em `prod`, apenas o domínio oficial.
* **Cookies**: usar `Secure` e `SameSite=Strict` em produção.

---

## 🧪 Validação

* **Startup do BFF** deve falhar se `SESSION_SECRET` ausente.
* **Pipeline CI/CD** deve validar variáveis obrigatórias em cada ambiente.
* Rodar `curl $HOST/api/health` após deploy para validar.

---

## 🔮 Futuro

* Automatizar provisionamento de `.env` via Terraform + Vault.
* Incluir suporte a **multi-tenant** (variáveis específicas por cliente).
* Configuração dinâmica via `/api/config` servido pelo BFF.

