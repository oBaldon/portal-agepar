# Infra – Banco de Dados PostgreSQL

Este documento descreve como o Portal AGEPAR utiliza o **PostgreSQL** como banco de dados principal em **homologação** e **produção**.

---

## 🎯 Objetivos

- Substituir SQLite usado em **dev** por PostgreSQL em ambientes reais.  
- Fornecer persistência robusta para **submissões**, **auditoria** e dados de autenticação.  
- Garantir escalabilidade (pool de conexões) e segurança (roles, TLS, backups).  

---

## 🗄️ Estrutura Básica

O BFF usa **SQLAlchemy + Alembic** (ou equivalente) para gerenciar o schema.  

Tabelas iniciais:
- **`submissions`**: armazena entradas de automações.  
- **`audits`**: registra eventos (quem fez, quando, resultado).  
- Futuro: **`users`**, **`sessions`**, **`roles`**.  

---

## 🔧 Conexão

### URL de conexão

```text
postgresql+psycopg2://<user>:<password>@<host>:5432/<dbname>
````

### Exemplo `.env.prod`

```env
DB_URL=postgresql+psycopg2://agepar_user:${DB_PASSWORD}@db-prod:5432/agepar
```

> A senha (`DB_PASSWORD`) deve ser obtida de **Vault** e nunca commitada.

---

## 🐳 Docker Compose (Homolog)

```yaml
services:
  db:
    image: postgres:15
    restart: always
    environment:
      POSTGRES_USER: agepar_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: agepar
    volumes:
      - db_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
volumes:
  db_data:
```

---

## 🔐 Segurança

* Criar **usuário dedicado** por ambiente (não usar `postgres` default).
* Aplicar **principle of least privilege**:

  * `agepar_user` → apenas `CONNECT`, `SELECT`, `INSERT`, `UPDATE`, `DELETE`.
  * `agepar_admin` → para migrações (DDL).
* Habilitar **TLS** em produção (`sslmode=require`).
* Senhas gerenciadas em **Vault** ou Secret Manager.

---

## 🏗️ Pool de Conexões

O BFF inicializa `asyncpg`/SQLAlchemy com **pool configurado**:

* `pool_size`: 5–10 (ajustar conforme carga).
* `max_overflow`: +5.
* Timeout: 30s.

Isso evita exaustão de conexões e melhora performance.

---

## 🔄 Migrações

* Feitas via **Alembic**.
* Scripts devem ser versionados em `apps/bff/migrations/`.
* Pipelines de CI/CD aplicam migrações automaticamente em homologação.
* Em produção, aplicar migrações **sob controle de change management**.

---

## 🧪 Health Checks

* Endpoint `/api/health` deve verificar conectividade com o banco.
* Monitorar latência média (<100ms).
* Alertar quando conexão falhar ou acumular retries.

---

## ♻️ Backup e Restauração

* **Backups diários** completos.
* **Retenção mínima**: 30 dias (configurado em S3/Blob storage).
* Testes de restauração devem ser feitos mensalmente.

Exemplo de comando manual:

```bash
pg_dump -h db-prod -U agepar_user agepar > backup.sql
psql -h db-prod -U agepar_user -d agepar < backup.sql
```

---

## 📊 Observabilidade

* Habilitar **pg\_stat\_statements** para analisar queries lentas.
* Monitorar:

  * conexões ativas
  * locks
  * tamanho de tabelas/indexes
* Dashboards no Grafana/Prometheus integrados ao Postgres Exporter.

---

## 🔮 Futuro

* Implementar **particionamento** para tabelas grandes (ex.: auditorias).
* Usar **read replicas** para consultas analíticas.
* Habilitar **pgBouncer** como connection pooler externo.
* Criptografar colunas sensíveis com **pgcrypto**.