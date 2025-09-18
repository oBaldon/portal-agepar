# Migrações de Banco (Alembic)

Este documento padroniza a estratégia de **migrações de schema e dados** do BFF usando **Alembic**.  
Ambientes: **SQLite (dev)** e **Postgres (prod)**.

---

## 🎯 Objetivos

- Versionar alterações de schema de forma **auditável**.
- Suportar **evolução incremental** sem perda de dados.
- Minimizar downtime em produção (estratégias compatíveis com zero-downtime).
- Testar migrações em CI para evitar regressões.

---

## 📦 Estrutura Recomendada

```

apps/bff/
├── app/
│   └── db/
│       ├── base.py           # modelos SQLAlchemy
│       ├── session.py        # engine / SessionLocal
│       └── **init**.py
└── alembic/
├── env.py
├── script.py.mako
├── alembic.ini           # opcional aqui; pode ficar na raiz do projeto
└── versions/
├── 20250916\_0001\_init.py
└── 20250916\_0002\_add\_audits\_index.py

````

> **Observação**: manter `alembic.ini` na raiz do repositório facilita comandos na CI.

---

## ⚙️ Instalação

### Dependências
```bash
pip install alembic sqlalchemy psycopg2-binary  # prod
# Para dev (SQLite) não é necessário o driver do Postgres
````

### Init do Alembic

```bash
cd apps/bff
alembic init alembic
```

---

## 🔧 Configuração (`alembic/env.py`)

Pontos-chave:

* Ler `DATABASE_URL` de env.
* Importar **metadados** dos modelos (`Base.metadata`) para autogenerate.
* Suportar **offline** (gera SQL) e **online** (aplica direto).

Exemplo (trecho):

```python
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os

# Carrega config.ini
config = context.config
fileConfig(config.config_file_name)

# URL do banco
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./db.sqlite")
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Importa metadados
from app.db.base import Base  # Base = declarative_base()
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

---

## 🧬 Modelos Base (exemplo mínimo)

```python
# app/db/base.py
from sqlalchemy.orm import declarative_base
Base = declarative_base()
```

> Seus modelos (Submissions, Audits, Sessions) devem herdar de `Base` e estar importados por este módulo para o **autogenerate** funcionar.

---

## 🧪 Comandos Essenciais

### Criar revisão (vazia)

```bash
alembic revision -m "cria tabela submissions"
```

### Criar revisão por **autogenerate**

```bash
alembic revision --autogenerate -m "ajusta indices em audits"
```

> **Revise o diff** gerado antes de aplicar. Autogenerate não é infalível.

### Aplicar migrações

```bash
alembic upgrade head
```

### Voltar uma versão (downgrade)

```bash
alembic downgrade -1
```

### Gerar SQL (offline)

```bash
alembic upgrade head --sql > migrate.sql
```

---

## 🗂️ Revisão de Exemplo

```python
# alembic/versions/20250916_0001_init.py
from alembic import op
import sqlalchemy as sa

revision = "20250916_0001_init"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("automation_slug", sa.String(64), nullable=False, index=True),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "audits",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("timestamp", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("details", sa.JSON, nullable=True),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("roles", sa.JSON, nullable=False),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default=sa.text("0")),
    )

def downgrade():
    op.drop_table("sessions")
    op.drop_table("audits")
    op.drop_table("submissions")
```

> **Compatibilidade**: `JSON` em SQLite pode requerer fallback para `Text` + validação; ajuste conforme necessidade.

---

## 🧷 Dicas para Zero-Downtime

* **Add-first, remove-later**:

  * Adicione colunas/tabelas novas **sem** remover as antigas.
  * Faça o aplicativo aceitar **ambas** até completar a implantação.
  * Remova colunas antigas em **revisão posterior**.

* **Defaults & NULL**:

  * Prefira `NULLABLE + DEFAULT` ao introduzir colunas para evitar falhas em inserts existentes.

* **Índices e constraints**:

  * Crie índices **concomitantes** (em Postgres: `CREATE INDEX CONCURRENTLY`) em migrações separadas quando volume alto.

* **Long running**:

  * Evite `ALTER TABLE ... TYPE` ou `ALTER COLUMN NOT NULL` em tabelas grandes sem planejamento.

---

## 🧪 Estratégia de Testes de Migração

1. **Dev (SQLite):**

   * Rodar `alembic upgrade head` localmente.
2. **CI (SQLite e Postgres):**

   * Subir containers (`postgres:15`), aplicar migrações e executar testes.
3. **Smoke Test:**

   * Após upgrade, rodar um teste de inicialização do app.
4. **Rollback controlado:**

   * Validar `alembic downgrade -1` em ambientes não-prod.

Exemplo de job (pseudo):

```bash
export DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/portal
alembic upgrade head
pytest -q
```

---

## 🔁 Branching & Merge de Migrações

* Evite criar **revisões concorrentes** na mesma branch.
* Em conflitos de `down_revision`, una as revisões ajustando o cabeçalho:

  * Escolha a revisão “base” e defina `down_revision` corretamente.
* **Nunca** reescreva (`amend`) migrações já aplicadas em ambientes compartilhados.

---

## 🧹 Migrações de Dados (DML)

* Use revisões com **passos idempotentes** (ex.: `UPDATE` com `WHERE`).
* Em Postgres, prefira **transações explícitas** e **bateladas**.
* Em alto volume, migre dados em **jobs** do app, não dentro da migração (reduz lock).

Exemplo:

```python
def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE submissions SET status='processing' WHERE status IS NULL"))
```

---

## 🛠️ Troubleshooting

* **`No such revision`**: checar `alembic.ini` e `script_location`.
* **`Target database is not up to date`**: rodar `alembic upgrade head`.
* **Autogenerate não detecta mudanças**: garantir que modelos estão importados em `Base`.
* **Tipos JSON no SQLite**: usar `sa.Text` + validação na aplicação, ou `sqlite+aiosqlite` com checagem.
* **Lock em Postgres**: revisar índices/alterações pesadas; usar janelas de manutenção.

---

## 📌 Políticas

* **Downgrade em produção**: somente para incidentes críticos; preferir **forward-fix**.
* **Revisões pequenas e frequentes**: facilitam revisão e rollback.
* **Nomear revisões** com **data + propósito** (ex.: `20250916_0003_add_index_submissions_created_at`).

---

## ✅ Checklist PR de Migração

* [ ] `revision --autogenerate` revisada manualmente
* [ ] Compatível com **SQLite** e **Postgres**
* [ ] Testes passaram em CI (ambos os bancos)
* [ ] Inclui **upgrade** e **downgrade** seguros
* [ ] Documentação atualizada (esta página / changelog)

