# Testes – Unitários no Backend (FastAPI + Pytest)

Este documento descreve como escrever e estruturar **testes unitários** para o BFF do Portal AGEPAR (FastAPI), cobrindo **validações Pydantic**, **routers**, **dependências**, **DB** e **background tasks**.

---

## 🎯 Objetivos

- Validar **regras de negócio** e **schemas** sem rodar todo o stack.
- Isolar componentes com **fixtures** e **mocks**.
- Garantir mensagens de erro **claras** e **status codes** padronizados.
- Medir cobertura e integrar na **CI**.

---

## 🧱 Estrutura Recomendada

```

apps/bff/
├── app/
│   ├── automations/
│   ├── db/
│   ├── deps.py
│   ├── main.py
│   └── ...
└── tests/
├── conftest.py
├── test\_health.py
├── test\_auth.py
├── test\_catalog.py
├── automations/
│   ├── test\_dfd.py
│   └── test\_form2json.py
└── utils/
└── test\_validators.py

```

---

## ⚙️ Dependências

No `apps/bff/requirements-dev.txt`:

```

pytest
pytest-asyncio
httpx
pytest-cov
faker

````

> Se os endpoints são **sync** com `TestClient` do FastAPI, `httpx` é opcional. Para async, use `pytest-asyncio` + `httpx.AsyncClient`.

---

## 🧩 `conftest.py` (fixtures principais)

```python
# apps/bff/tests/conftest.py
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.base import Base
from app.db.session import get_db  # sua dependência de sessão

TEST_DB_URL = "sqlite:///./test.db"

@pytest.fixture(scope="session", autouse=True)
def _env():
    os.environ["ENV"] = "test"
    os.environ["LOG_LEVEL"] = "error"
    yield

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture()
def db(engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.fixture()
def client(db, monkeypatch):
    # override de dependência do FastAPI p/ usar a sessão de teste
    def _get_db_override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
````

> **Dica:** para **tests paralelos** use bancos `sqlite:///:memory:` por processo/worker ou namespace por arquivo.

---

## 🩺 Health & Version

```python
# apps/bff/tests/test_health.py
def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"

def test_version_has_semver(client):
    r = client.get("/api/version")
    assert r.status_code == 200
    v = r.json()["version"]
    assert isinstance(v, str) and v.count(".") >= 2
```

---

## 🔐 Auth & Sessões (mock)

```python
# apps/bff/tests/test_auth.py
def test_login_ok_sets_cookie(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200
    assert "set-cookie" in r.headers

def test_me_requires_session(client):
    r = client.get("/api/me")
    assert r.status_code in (401, 403)

def test_logout_ok_without_error(client):
    r = client.post("/api/auth/logout")
    assert r.status_code in (200, 204)
```

> Ajuste os **status** conforme sua implementação (401/403/204).

---

## 📚 Catálogo

```python
# apps/bff/tests/test_catalog.py
def test_catalog_dev_shape(client):
    r = client.get("/catalog/dev")
    assert r.status_code == 200
    data = r.json()
    assert "categories" in data and "blocks" in data
    assert isinstance(data["categories"], list)
    assert isinstance(data["blocks"], list)
```

---

## 🧪 Validações Pydantic

```python
# apps/bff/tests/utils/test_validators.py
import pytest
from pydantic import ValidationError
from app.schemas.common import NonEmptyStr  # exemplo

def test_non_empty_str_rejects_blank():
    with pytest.raises(ValidationError):
        NonEmptyStr.model_validate("  ")

def test_non_empty_str_ok():
    assert NonEmptyStr.model_validate("ok") == "ok"
```

---

## 🤖 Automações – Fluxo Padrão

### Exemplo DFD

```python
# apps/bff/tests/automations/test_dfd.py
import time

def test_schema(client):
    r = client.get("/api/automations/dfd/schema")
    assert r.status_code in (200, 204)

def test_ui(client):
    r = client.get("/api/automations/dfd/ui")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]

def test_submit_and_persist(client, db):
    payload = {"ano": 2025, "orgao": "AGEPAR", "justificativa": "Teste"}
    r = client.post("/api/automations/dfd/submit", json=payload)
    assert r.status_code in (200, 202)
    body = r.json()
    sid = body.get("submission_id")
    assert sid is not None

    # listar
    r = client.get("/api/automations/dfd/submissions")
    assert r.status_code == 200
    items = r.json()
    assert any(i["id"] == sid for i in items)

    # consultar
    r = client.get(f"/api/automations/dfd/submissions/{sid}")
    assert r.status_code == 200
    sub = r.json()
    assert sub["payload"]["orgao"] == "AGEPAR"

def test_download_404_when_not_ready(client):
    r = client.post("/api/automations/dfd/submissions/999999/download")
    assert r.status_code == 404
```

---

## 🧰 Mock de BackgroundTasks

Se o processamento é assíncrono, **troque** a função real por um **mock** para não depender de workers:

```python
# apps/bff/tests/automations/test_form2json.py
from app.automations import form2json

def test_submit_mock_background(client, monkeypatch):
    def _fake_process(submission_id: int):
        # simula sucesso rápido
        pass
    monkeypatch.setattr(form2json, "process_submission", _fake_process)

    r = client.post("/api/automations/form2json/submit", json={"html": "<form></form>"})
    assert r.status_code in (200, 202)
```

---

## 🧩 Tabela de Submissões (ORM)

```python
# apps/bff/tests/test_db_submissions.py
from sqlalchemy import select
from app.db.models import Submission

def test_submission_persisted(db, client):
    r = client.post("/api/automations/form2json/submit", json={"html": "<form></form>"})
    assert r.ok
    sid = r.json()["submission_id"]

    row = db.execute(select(Submission).where(Submission.id == sid)).scalar_one()
    assert row.automation_slug == "form2json"
    assert row.status in ("pending", "processing", "success", "error")
```

---

## 🧱 Parametrização de Erros (422/400)

```python
# apps/bff/tests/automations/test_validation.py
import pytest

@pytest.mark.parametrize("payload", [
    {},  # faltando campos
    {"ano": "xxxx"},  # tipo inválido
    {"orgao": ""},  # vazio
])
def test_submit_validation_errors(client, payload):
    r = client.post("/api/automations/dfd/submit", json=payload)
    assert r.status_code in (400, 422)
```

---

## 🔒 RBAC nos Endpoints

```python
# apps/bff/tests/test_rbac.py
def test_automation_requires_role(client):
    # sem cookie/role → deve falhar
    r = client.post("/api/automations/dfd/submit", json={"ano": 2025, "orgao": "X"})
    assert r.status_code in (401, 403)
```

> Em ambiente de teste, crie helper para **login** e reutilize cookies:

```python
def login_admin(client):
    return client.post("/api/auth/login", json={"username": "admin", "password": "admin"})

def test_allowed_after_login(client):
    login_admin(client)
    r = client.get("/api/me")
    assert r.status_code == 200
```

---

## 📈 Cobertura

Adicionar ao `pyproject.toml` (ou `pytest.ini`):

```toml
[tool.pytest.ini_options]
addopts = "-q --cov=app --cov-report=term-missing:skip-covered"
testpaths = ["apps/bff/tests"]
```

Rodar:

```bash
pytest -q --cov=app --cov-report=term-missing:skip-covered
```

**Metas sugeridas**:

* Cobertura **linhas** ≥ 70%
* Cobertura **branches** ≥ 50%

---

## 🧪 Dicas Práticas

* Use **fixtures** para dados repetidos (ex.: `payload_dfd`).
* Prefira **mocks** a dependências externas (e-mails, fila, storage).
* Valide sempre **status code** + **mensagem de erro** (clareza para o usuário).
* Testes devem ser **idempotentes** e **independentes** (não dependem de ordem).

---

## 🔮 Futuro

* Testes async com `httpx.AsyncClient` e `lifespan="on"` para eventos de startup/shutdown.
* Fixtures de **catálogo** por cenário (dev, prod, RBAC).
* **Property-based testing** (hypothesis) para validações complexas.
* Testes de **contrato** (schemathesis) a partir do **OpenAPI**.