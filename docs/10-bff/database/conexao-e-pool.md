# Conexão e Pool de Banco de Dados

O **BFF (FastAPI)** do Portal AGEPAR utiliza **SQLAlchemy** para conectar-se ao banco de dados.  
O objetivo é garantir conexões **seguras, eficientes e escaláveis** tanto em desenvolvimento (SQLite) quanto em produção (Postgres).

---

## 🎯 Objetivos

- Estabelecer conexão robusta com **SQLite** (dev) e **Postgres** (prod).  
- Gerenciar conexões via **pool de conexões** para evitar overhead.  
- Garantir **rollback automático** em caso de erro.  
- Preparar suporte a **múltiplas instâncias do BFF** em produção.  

---

## 📌 URL de Conexão

A conexão é configurada pela variável de ambiente:

```bash
DATABASE_URL=postgresql+psycopg2://user:pass@db:5432/portal
````

* **Desenvolvimento (SQLite):**

  ```bash
  DATABASE_URL=sqlite:///./db.sqlite
  ```
* **Produção (Postgres):**

  ```bash
  DATABASE_URL=postgresql+psycopg2://user:pass@db:5432/portal
  ```

---

## ⚙️ Pool de Conexões

* Usado em produção para **Postgres**.
* Configuração típica (SQLAlchemy):

  * `pool_size=5` → conexões simultâneas mínimas.
  * `max_overflow=10` → conexões extras em pico.
  * `pool_timeout=30` → tempo de espera antes de erro.
  * `pool_recycle=1800` → reciclagem para evitar desconexões inativas.

Exemplo em código:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    echo=False,  # ativar True para debug
    future=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

---

## 🔄 Ciclo de Sessão

Cada requisição FastAPI deve usar uma sessão independente:

```python
from fastapi import Depends

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

* Sessão aberta no início da requisição.
* Encerrada automaticamente no fim, evitando vazamentos.
* Em caso de erro, **rollback automático**.

---

## 🧪 Teste de Conexão

### SQLite

```bash
sqlite3 db.sqlite ".tables"
```

### Postgres

```bash
psql -h localhost -U user -d portal -c "\dt"
```

---

## 🚀 Futuro

* Integrar **pgbouncer** ou **ProxySQL** para gerenciamento avançado.
* Adicionar suporte a **monitoramento de pool** (Prometheus exporter).
* Migrar para **async SQLAlchemy** em cenários de alta concorrência.

---

📖 Próximo: [Migrações](migracoes.md)
