---
id: sem-segredos-no-repo
title: "Sem segredos no repo"
sidebar_position: 3
---

O Portal AGEPAR segue uma regra simples:

> **Nenhum segredo real deve viver no repositório.**  
> Senhas, tokens, chaves de sessão/cripto e credenciais de banco **sempre** vêm de
> variáveis de ambiente ou do mecanismo de segredos da infra.

O repo só traz:

- **placeholders e valores de dev** (ex.: `dev-secret`, `portaldev`),
- exemplos de `DATABASE_URL` para laboratório,
- documentação de **quais variáveis** precisam ser configuradas em cada ambiente.

> Referências principais no repositório:  
> `README.md` (bullet “Sem segredos no repositório — use variáveis de ambiente”)  
> `infra/docker-compose.dev.yml`, `infra/docker-compose.pg.yml`  
> `apps/bff/run_dev.sh`  
> `apps/bff/app/main.py`  
> `apps/bff/app/automations/fileshare.py`  
> `apps/docs-site/docs/02-ambiente-dev-setup/03-variáveis-de-ambiente-e-cors-cookies.md`  
> `apps/docs-site/docs/03-build-run-deploy/05-ci-cd-se-aplicável.md`  

---

## 1) O que é considerado “segredo” aqui

Para evitar dúvida, considere **segredo** tudo que:

- permitiria **acesso privilegiado** a algum sistema, se vazasse:
  - senhas de banco (Postgres),  
  - `SESSION_SECRET` (sessão HTTP e HMAC de links),  
  - tokens de registro de imagens (`DOCKERHUB_TOKEN`, `GHCR_TOKEN`),  
  - chaves/segredos de OIDC (`OIDC_CLIENT_SECRET`, mesmo que ainda não exista no código),
  - chaves SSH (`SSH_KEY`) usadas em deploy;
- ou qualquer **token de longa duração** (API keys, refresh tokens, etc.).

Não são considerados segredos:

- nomes de variáveis (`DATABASE_URL`, `SESSION_SECRET`, `PGPASSWORD`),
- **usuário de dev** (por exemplo `portal` ou `agepar` na documentação),
- hosts internos (ex.: `postgres`, `bff` no Docker Compose),
- exemplos obviamente fictícios em docs (`senha-super-secreta`, `CHAVE_AQUI` etc.).

---

## 2) Onde os segredos vivem de verdade

### 2.1. BFF (FastAPI) — `SESSION_SECRET`, `DATABASE_URL`, OIDC

No BFF, as credenciais vêm de **variáveis de ambiente**, nunca hardcoded:

```python title="apps/bff/app/main.py — variáveis sensíveis" showLineNumbers
ENV = os.getenv("ENV", "dev")
AUTH_MODE = os.getenv("AUTH_MODE", "local")
EP_MODE = os.getenv("EP_MODE", "mock")

SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
CATALOG_FILE = Path(os.getenv("CATALOG_FILE", "/catalog/catalog.dev.json"))
OIDC_ISSUER = os.getenv("OIDC_ISSUER", "")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
OIDC_JWKS_URL = os.getenv("OIDC_JWKS_URL", "")
````

E no `run_dev.sh`:

```bash title="apps/bff/run_dev.sh — não define DATABASE_URL por padrão" showLineNumbers
# Sessão HTTP (cookie)
export SESSION_SECRET="${SESSION_SECRET:-dev-secret}"

# CORS p/ o Vite host
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:5173}"

# Catálogo (dev)
export CATALOG_FILE="${CATALOG_FILE:-/catalog/catalog.dev.json}"

# OBS: DATABASE_URL deve vir do docker-compose/.env; não definimos default aqui.
```

Pontos importantes:

* **`SESSION_SECRET`** tem um default **apenas para dev** (`dev-secret`);
  produção **deve** sobrescrever com um valor forte e secreto.
* **`DATABASE_URL`** não tem default em código:

  * isso força a vir **sempre** do ambiente (Compose, Kubernetes Secret, etc.),
  * reduz risco de deixar uma URL “fixa” de banco perdida no código.

O módulo `fileshare` também lê o segredo da sessão **via env**:

```python title="apps/bff/app/automations/fileshare.py — HMAC de links" showLineNumbers
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret").encode("utf-8")
```

Esse mesmo segredo assina os links públicos de download via HMAC; em produção, ele **nunca** deve ser um valor fraco ou compartilhado com outros sistemas.

### 2.2. Banco de dados (Postgres) — Compose + env

No Compose de dev:

```yaml title="infra/docker-compose.pg.yml — credenciais de dev" showLineNumbers
services:
  postgres:
    environment:
      POSTGRES_DB: ${PGDATABASE:-portal}
      POSTGRES_USER: ${PGUSER:-portal}
      POSTGRES_PASSWORD: ${PGPASSWORD:-portaldev}
```

* O valor padrão `portaldev` é **apenas de laboratório**.
* Em ambientes sérios, espera-se que:

  * `PGPASSWORD` venha de um **arquivo `.env` local** (não versionado) ou
    de um **secreto** no orquestrador,
  * `DATABASE_URL` do BFF use esse mesmo usuário/senha sem aparecer no repo.

A própria documentação deixa isso explícito em:

* `02-ambiente-dev-setup/03-variáveis-de-ambiente-e-cors-cookies.md`
  (“Nunca subir segredos reais no repositório; use valores de dev.”)
* `03-build-run-deploy/05-ci-cd-se-aplicável.md`
  (seção **“Segredos e permissões”**).

### 2.3. CI/CD — segredos no GitHub Actions

Na página de CI/CD, os **segredos de pipeline** são referenciados sempre como `secrets.*`:

```yaml title="docs — segredos em workflows de CI" showLineNumbers
# Para deploy via SSH/rsync
with:
  remote_host: ${{ secrets.SSH_HOST }}
  remote_user: ${{ secrets.SSH_USER }}
  remote_key: ${{ secrets.SSH_KEY }}
```

E nas recomendações:

* tokens de registry (`DOCKERHUB_TOKEN`, `GHCR_TOKEN`),
* chaves SSH (`SSH_KEY`),
* credenciais de cloud (S3, CDN, etc.)

**nunca** aparecem com valores concretos — apenas como nomes de segredos que devem ser configurados na UI do provider (GitHub, cloud, etc.).

---

## 3) Como o repo ajuda a evitar vazamento

### 3.1. `.gitignore` protegendo arquivos locais

Na raiz:

```gitignore title=".gitignore — trechos relevantes" showLineNumbers
# Node.js / Frontend
node_modules/
dist/
build/
out/

# Python / Backend
__pycache__/
*.pyc
.venv/
venv/
ENV/
*.db

# Generated files
.docusaurus
.cache-loader

# Misc
.DS_Store
.env.local
.env.development.local
.env.test.local
.env.production.local
```

Consequências:

* Arquivos `.env.*` locais (Host/BFF/infra) **não** são commitados por engano.
* DBs locais (`*.db`) não entram no histórico.
* Pastas de build/cache também ficam fora do repo.

> Se você criar um `.env` “genérico” (sem sufixo), a recomendação é:
>
> * ou adicionar ao `.gitignore`,
> * ou usar sempre `.env.local`, `.env.development.local`, etc.

### 3.2. Defaults claramente “não-prod”

Alguns valores **de propósito** são fracos/óbvios, para deixar claro que são dev-only:

* `SESSION_SECRET=dev-secret` (BFF e fileshare),
* `PGPASSWORD=portaldev` (default no Compose),
* exemplos de docs (`DATABASE_URL=postgresql://agepar:agepar@db:5432/agepar`).

A intenção é:

* mostrar claramente “isso aqui é **dev**”,
* evitar a tentação de reaproveitar credenciais reais em exemplo/documentação,
* permitir subir rapidamente o ambiente local **sem** precisar de segredos externos.

---

## 4) Exceções controladas: valores de dev no repo

Existem **dois tipos** de segredos “visíveis” no código:

1. **Segredos fictícios/de laboratório**, usados apenas em dev:

   * `SESSION_SECRET=dev-secret`
   * `PGPASSWORD=portaldev`
   * usuários/senhas genéricos em exemplos de `DATABASE_URL`.

2. **Nomes de variáveis que receberão segredos reais**:

   * `SESSION_SECRET`, `DATABASE_URL`, `PGPASSWORD`,
   * `SSH_HOST`, `SSH_USER`, `SSH_KEY`,
   * futuros `OIDC_CLIENT_SECRET`, etc.

Política:

* Valores **reais** de produção/homolog **não** devem aparecer em:

  * código (`.py`, `.ts/.tsx`, `.sh`),
  * Compose de produção,
  * documentação (`.md/.mdx`),
  * histórico git (commits antigos).
* Valores “de brinquedo” (como `dev-secret`) são aceitos apenas quando:

  * são marcados como dev/mock,
  * não são reutilizados em nenhum ambiente sério,
  * não dão acesso a dados reais.

---

## 5) Checklist para novas features (para não vazar segredos)

Sempre que você for mexer com algo que **pode envolver segredos**, siga este checklist:

1. **Precisa mesmo de um segredo?**

   * Se for senha, token, chave de HMAC, client secret de OAuth/OIDC → **sim**.
   * Se for apenas um host/porta ou “issuer” público → provavelmente não.

2. **Criar a variável de ambiente adequada**

   * Dê um nome claro, em UPPER_CASE:

     * ex.: `MY_FEATURE_API_TOKEN`, `MY_FEATURE_CLIENT_SECRET`.
   * Lê-la via `os.getenv("NOME", default_dev)` no código:

     * se for critíco, considere **não** ter default (falhar rápido se ausente).

3. **Documentar sem vazar**

   * Na Docs (Docusaurus), mostrar **somente o nome** da variável:

     ```bash
     # exemplo
     MY_FEATURE_API_TOKEN=***  # configure via secret manager
     ```
   * Nunca colocar o valor verdadeiro (nem “mascarado”).

4. **Garantir que não será commitado**

   * Usar `.env.local`, `.env.development.local`, etc. (já ignorados no `.gitignore`).
   * Para arquivos extras (ex.: `secrets/` de dev), adicionar um `secrets/.gitignore`
     interno com `*` e um `README.md` explicando.

5. **Integrar com CI/CD**

   * No GitHub Actions, declarar apenas `secrets.MY_FEATURE_API_TOKEN`.
   * Definir o valor **no ambiente** (GitHub, kube, etc.), nunca no YAML.

6. **Checar o código antes de abrir PR**

   * Rodar uma busca rápida:

     ```bash
     rg -n "PASSWORD|SECRET|TOKEN|API_KEY" .
     ```
   * Verificar se algum valor **real** apareceu por engano (logs, dumps, etc.).

---

## 6) Exemplos práticos

### 6.1. Exemplo de `.env.local` (não versionado) para o BFF

```dotenv title=".env.local (exemplo) — NÃO commitar"
# DB
DATABASE_URL=postgresql://portal:uma-senha-forte@postgres:5432/portal

# Sessão
SESSION_SECRET=uma-string-aleatoria-bem-grande

# CORS (produção)
CORS_ORIGINS=https://portal.agepar.pr.gov.br

# OIDC (quando configurado)
OIDC_ISSUER=https://login.exemplo.gov.br/
OIDC_CLIENT_ID=portal-agepar
OIDC_JWKS_URL=https://login.exemplo.gov.br/.well-known/jwks.json
# OIDC_CLIENT_SECRET deve vir de secrets no orquestrador
```

### 6.2. Exemplo de uso de `SESSION_SECRET` na automação fileshare

```python title="apps/bff/app/automations/fileshare.py — uso do segredo" showLineNumbers
import hmac
import hashlib
import os

SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret").encode("utf-8")

def _sign_token(data: str) -> str:
    """
    Gera assinatura HMAC para links públicos de download.

    Em produção, SESSION_SECRET deve ser forte e vindo de segredo
    gerenciado pela infra (env/secret manager).
    """
    return hmac.new(SESSION_SECRET, data.encode("utf-8"), hashlib.sha256).hexdigest()
```

Esse padrão deixa explícito:

* **o que** precisa de segredo (HMAC),
* **onde** o segredo é lido (env),
* **qual** default é aceitável apenas em dev (`dev-secret`).

---

> _Criado em 2025-12-01_