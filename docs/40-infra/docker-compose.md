# Infra – Docker Compose

O **Docker Compose** é utilizado para orquestrar os serviços principais do Portal AGEPAR em **desenvolvimento** e **homologação**.  
Este documento descreve sua configuração, boas práticas e comandos úteis.

---

## 🎯 Objetivos

- Definir os serviços do monorepo (BFF, Host, Docs, Banco).  
- Garantir rede compartilhada entre containers.  
- Simplificar setup local (`docker compose up`).  
- Servir de base para homologação/staging.  

---

## 📦 Serviços Principais

### Exemplo `docker-compose.yml`

```yaml
version: "3.9"

services:
  bff:
    build: ./apps/bff
    container_name: portal_bff
    ports:
      - "8000:8000"
    env_file: .env.dev
    volumes:
      - ./apps/bff:/app
    depends_on:
      - db

  host:
    build: ./apps/host
    container_name: portal_host
    ports:
      - "5173:5173"
    env_file: .env.dev
    volumes:
      - ./apps/host:/app
    depends_on:
      - bff
      - docs

  docs:
    build: ./docs
    container_name: portal_docs
    expose:
      - "8000"
    volumes:
      - ./docs:/docs

  db:
    image: postgres:15
    container_name: portal_db
    restart: always
    environment:
      POSTGRES_USER: agepar_user
      POSTGRES_PASSWORD: ${DB_PASSWORD:-devpass}
      POSTGRES_DB: agepar
    volumes:
      - db_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

volumes:
  db_data:
````

---

## 🕸️ Rede

* Todos os serviços compartilham rede padrão do Compose.
* Host resolve `bff:8000` e `docs:8000` via proxy configurado no Vite.
* Banco acessível como `db:5432` para o BFF.

---

## 🔧 Arquivos `.env`

* **`.env.dev`** → variáveis locais (SQLite/Postgres dev, secrets mock).
* **`.env.stage`** → variáveis para homologação (Postgres real).
* **`.env.prod`** → usado em deploys (não versionado, injetado via CI/CD).

---

## 🛠️ Comandos Úteis

Subir ambiente de desenvolvimento:

```bash
docker compose up --build
```

Recriar apenas o BFF:

```bash
docker compose up -d --build bff
```

Executar migrations dentro do BFF:

```bash
docker compose exec bff alembic upgrade head
```

Acessar banco Postgres:

```bash
docker compose exec db psql -U agepar_user -d agepar
```

Parar todos os serviços:

```bash
docker compose down
```

---

## 🔐 Boas Práticas

* Usar **volumes nomeados** para banco (`db_data`) → persistência local.
* Não expor `db:5432` em produção (apenas em dev/homolog quando necessário).
* Definir sempre `env_file` ou `environment` com valores claros.
* Manter containers leves, builds rápidos (usar `.dockerignore`).

---

## 🧪 Testes

* Após `docker compose up`, validar:

  * `http://localhost:5173` → Host online.
  * `http://localhost:5173/api/health` → BFF responde OK.
  * `http://localhost:5173/catalog/dev` → catálogo carregado.
  * `http://localhost:5173/docs/` → documentação disponível.

---

## 📦 Extensões Futuras

* **docker-compose.override.yml** para dev local (hot-reload).
* Separar rede de **frontend/backend** para maior isolamento.
* Adicionar serviços auxiliares (pgadmin, adminer) em dev.
* Migrar para **Compose v2 + Profiles** para ativar/desativar serviços (`--profile docs`).