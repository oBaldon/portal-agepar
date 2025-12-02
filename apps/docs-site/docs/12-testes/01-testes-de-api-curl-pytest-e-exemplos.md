---
id: testes-de-api-curl-pytest-e-exemplos
title: "Testes de API (cURL/pytest) e exemplos"
sidebar_position: 1
---

O Portal AGEPAR hoje é testado principalmente com:

- **cURLs de fumaça** (descritos no `README.md`) para validar login, sessão e automations,
- **testes unitários sugeridos com pytest** para modelos Pydantic (já exemplificados em outras páginas de docs),
- e tem espaço aberto para **testes de API automatizados** usando `pytest + TestClient` (ainda não criados no repositório, mas já com padrão recomendado).

> Referências no repo:
>
> - `README.md` → seção **“🧪 Testes rápidos (cURL)”**
> - `apps/bff/app/automations/*.py` → endpoints de API das automations
> - `apps/bff/app/auth/routes.py` → login, logout, sessões
> - `apps/docs-site/docs/06-bff-fastapi/04-pydantic-v2-configdict-populate_by_name-extraignore.md` → exemplos de **pytest** para modelos
> - `apps/docs-site/docs/06-bff-fastapi/05-normalização-validação-evitar-422.md` → mais exemplos de testes de normalização/validação

---

## 1) Mapa mental: cURL vs pytest

```mermaid
flowchart LR
  Dev[(Dev)]
  subgraph CLI
    CURL["cURL scripts (manual/smoke)"]
    PYTEST["pytest (testes automatizados)"]
  end
  subgraph Stack
    BFF["FastAPI BFF :8000"]
    DB[(Postgres)]
  end

  Dev --> CURL
  Dev --> PYTEST
  CURL --> BFF
  PYTEST --> BFF
  BFF --> DB
````

* **cURL**: ótimo para smoke test rápido, diagnóstico e documentação viva.
* **pytest**: ideal para cobrir casos de sucesso/erro de forma automatizada (incluindo o mesmo fluxo que os cURLs).

---

## 2) Testes rápidos de API com cURL (do README)

A forma mais simples de validar se a stack está de pé:

### 2.1. Login (mock) e sessão

Trechos retirados de `README.md`.

```bash title="Login (mock, ambiente dev)" showLineNumbers
curl -i -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"dev@example.com","password":"dev"}'
```

* Esperado: `HTTP/1.1 200 OK` + JSON com dados do usuário.
* O cookie `portal_agepar_session` deve ser setado no header `Set-Cookie`.

```bash title="Sessão atual (/api/me)" showLineNumbers
curl -i http://localhost:8000/api/me
```

* Sem cookie → `401 not authenticated`.
* Com cookie válido → JSON com dados do usuário logado.

### 2.2. Teste rápido de uma automação simples (form2json)

Um exemplo de **teste de API completo** (do README e docs de BFF) é a automação `form2json`:

```bash title="Submit em /api/automations/form2json/submit" showLineNumbers
curl -i -X POST http://localhost:8000/api/automations/form2json/submit \
  -H 'Content-Type: application/json' \
  -d '{
    "fullName": "  Maria da Silva  ",
    "email": "  maria@example.com ",
    "phone": "(41) 9 9999-0000",
    "acceptTerms": "sim",
    "amount": "1.234,56",
    "dateStart": "18/11/2025"
  }'
```

O teste verifica que:

* a API responde com `200 OK`,
* o payload retornado já está **normalizado** (vide docs de Pydantic/normalização),
* nenhum `422 validation_error` é disparado para casos triviais (espaços, formatação).

---

## 3) Pacote sugerido de cURLs de fumaça

Mesmo que apenas dois comandos estejam explícitos no README, a **rotina sugerida** de smoke test é:

1. **Healthcheck do BFF**

   ```bash title="Health do BFF" showLineNumbers
   curl -i http://localhost:8000/health
   ```

   * Esperado: `200 OK` + `{"status":"ok"}`.

2. **Versão e configuração**

   ```bash title="/version" showLineNumbers
   curl -s http://localhost:8000/version | jq .
   ```

   * Confere `env`, `auth_mode`, `ep_mode`, `dfd_version`, `ferias_version`, `cors_origins` etc.

3. **Login + sessão**

   ```bash title="Login de dev e uso de sessão" showLineNumbers
   # login
   curl -i -c /tmp/cookies.txt \
     -X POST http://localhost:8000/api/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"identifier":"dev@example.com","password":"dev"}'

   # /api/me usando cookie
   curl -i -b /tmp/cookies.txt http://localhost:8000/api/me
   ```

4. **Listagem de submissões DFD (quando configurado)**

   ```bash title="Listar DFD do usuário" showLineNumbers
   curl -s -b /tmp/cookies.txt \
     "http://localhost:8000/api/automations/dfd/submissions?limit=5&offset=0" | jq .
   ```

5. **Submit DFD com payload mínimo**

   (exemplo simplificado; valores dependem da automação)

   ```bash title="Submit DFD" showLineNumbers
   curl -i -b /tmp/cookies.txt \
     -X POST http://localhost:8000/api/automations/dfd/submit \
     -H 'Content-Type: application/json' \
     -d '{
       "modeloSlug": "padrao",
       "numero": "2025-001",
       "protocolo": "12345/2025",
       "assunto": "Teste de fumaça",
       "pcaAno": "2025"
     }'
   ```

6. **Exercitar um erro 4xx previsível**

   ```bash title="DFD — forçar validation_error" showLineNumbers
   curl -i -b /tmp/cookies.txt \
     -X POST http://localhost:8000/api/automations/dfd/submit \
     -H 'Content-Type: application/json' \
     -d '{
       "modeloSlug": "padrao",
       "numero": "",
       "protocolo": "",
       "assunto": "",
       "pcaAno": "20"
     }'
   ```

   * Esperado: `422` com `{code: "validation_error", message: "...", details: ...}`
     (padrão descrito em **Padrões de Erro & DX**).

> Esses cURLs podem ser agrupados em um script bash (ex.: `infra/scripts/smoke.sh`)
> para testes de fumaça pós-deploy.

---

## 4) pytest: onde entra e o que já está documentado

### 4.1. Situação atual no repositório

No zip atual:

* **não há** pastas de teste (`tests/`) nem arquivos `pytest.ini` / `conftest.py`,
* mas já existem **exemplos de uso de pytest nos docs**, especialmente:

  * `06-bff-fastapi/04-pydantic-v2-configdict-populate_by_name-extraignore.md`
  * `06-bff-fastapi/05-normalização-validação-evitar-422.md`

Nesses docs, aparecem testes como:

```python title="Exemplo de teste (docs de Pydantic)" showLineNumbers
# tests/test_submit_payload.py
from pydantic import ValidationError
from app.automations.form2json import Body

def test_normalize_and_validate():
    b = Body(fullName="  Alice  ", email="  A@Example.com ")
    assert b.full_name == "Alice"
    assert b.email == "a@example.com"

def test_empty_name_fails():
    try:
        Body(fullName="  ")
    except ValidationError:
        ...
```

e:

```python title="Exemplo de testes de normalização" showLineNumbers
def test_trim_and_case():
    p = SubmitPayload(fullName="  maria da silva  ")
    assert p.full_name == "Maria Da Silva"

def test_phone_digits():
    assert SubmitPayload(fullName="a", phone="(41) 9 9999-0000").phone == "41999990000"
```

Ou seja:

* a **filosofia de testes** já está definida:

  * focar em normalização e validação,
  * garantir que “o modelo faz o que promete”,
* falta apenas **materializar isso em uma árvore de testes pytest** no repo.

---

## 5) Estrutura recomendada para testes de API com pytest

Mesmo que ainda não exista, o padrão recomendando para organizar testes é:

```text
apps/
  bff/
    app/
      ...
    tests/
      __init__.py
      test_auth.py
      test_form2json.py
      test_dfd_api.py
      test_ferias_api.py
      conftest.py
```

### 5.1. `conftest.py` com TestClient

```python title="apps/bff/tests/conftest.py (sugestão)" showLineNumbers
import os
import pytest
from fastapi.testclient import TestClient

from app.main import APP  # FastAPI principal

@pytest.fixture(scope="session")
def client() -> TestClient:
    # Garantir que estamos em ambiente de teste
    os.environ.setdefault("ENV", "test")
    os.environ.setdefault("AUTH_MODE", "mock")
    return TestClient(APP)
```

### 5.2. Testes básicos de API (equivalentes aos cURLs)

#### Login + /api/me

```python title="apps/bff/tests/test_auth.py (sugestão)" showLineNumbers
def test_login_and_me(client: "TestClient"):
    # login mock
    res = client.post(
        "/api/auth/login",
        json={"identifier": "dev@example.com", "password": "dev"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "cpf" in data
    assert "nome" in data

    # reaproveita cookies da sessão
    res_me = client.get("/api/me")
    assert res_me.status_code == 200
    me = res_me.json()
    assert me["cpf"] == data["cpf"]
```

#### validation_error em automação

```python title="apps/bff/tests/test_dfd_api.py (sugestão)" showLineNumbers
def test_dfd_validation_error(client: "TestClient"):
    # login primeiro
    client.post(
        "/api/auth/login",
        json={"identifier": "dev@example.com", "password": "dev"},
    )

    res = client.post(
        "/api/automations/dfd/submit",
        json={
            "modeloSlug": "padrao",
            "numero": "",
            "protocolo": "",
            "assunto": "",
            "pcaAno": "20",
        },
    )
    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "validation_error"
    assert "message" in body
    assert "details" in body
```

#### fluxo feliz de submit

```python title="Submit DFD ok" showLineNumbers
def test_dfd_submit_ok(client: "TestClient"):
    client.post(
        "/api/auth/login",
        json={"identifier": "dev@example.com", "password": "dev"},
    )

    res = client.post(
        "/api/automations/dfd/submit",
        json={
            "modeloSlug": "padrao",
            "numero": "2025-001",
            "protocolo": "12345/2025",
            "assunto": "Teste pytest",
            "pcaAno": "2025",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "sid" in data
    assert data["status"] in ("queued", "done")
```

---

## 6) Como rodar pytest (quando testes forem criados)

Quando a pasta `apps/bff/tests/` existir, o fluxo sugerido é:

```bash title="Execução de pytest (sugestão)" showLineNumbers
# dentro do container ou no seu Python local
cd apps/bff

# instalar dependências (se ainda não fez)
pip install -r requirements.txt
pip install pytest

# rodar testes
pytest -q
```

E, para facilitar, pode ser criado um alvo de Make / script:

```bash title="Makefile (exemplo)" showLineNumbers
test-bff:
\tcd apps/bff && pytest -q
```

---

## 7) Cobrindo os contratos de erro (4xx/5xx) em pytest

A partir da seção de **Padrões de Erro & DX**, os testes de API podem verificar:

* códigos HTTP certos,
* `code` correto no JSON,
* estrutura de `details`.

Exemplos:

```python title="Testando 403 forbidden" showLineNumbers
def test_dfd_forbidden_on_other_user_submission(client: "TestClient"):
    # login como usuário A, criar submissão...
    client.post("/api/auth/login", json={"identifier": "userA", "password": "dev"})
    res = client.post("/api/automations/dfd/submit", json={...})
    sid = res.json()["sid"]

    # login como usuário B
    client.post("/api/auth/login", json={"identifier": "userB", "password": "dev"})

    # tentar acessar submissão de A
    res = client.get(f"/api/automations/dfd/submissions/{sid}")
    assert res.status_code == 403
    body = res.json()
    assert body["code"] == "forbidden"
```

```python title="Testando storage_error em cenário de falha de DB (mock)" showLineNumbers
def test_dfd_storage_error(monkeypatch, client: "TestClient"):
    from app import db

    def fake_list_submissions(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "list_submissions", fake_list_submissions)

    client.post("/api/auth/login", json={"identifier": "dev@example.com", "password": "dev"})

    res = client.get("/api/automations/dfd/submissions")
    assert res.status_code == 500
    body = res.json()
    assert body["code"] == "storage_error"
    assert "Falha ao consultar submissões." in body["message"]
```

---

## 8) Checklist de testes de API (para cada automação)

Para cada nova automação (ou endpoint) criada, o ideal é ter pelo menos:

1. **Smoke cURL** (documentado no README ou na própria página da automação):

   * [ ] Login + submit.
   * [ ] Listagem de submissões.
   * [ ] Download (quando aplicável).
   * [ ] Erro de validação (422) com payload claramente inválido.

2. **pytest de API** (quando a suíte existir):

   * [ ] `test_submit_ok` (trilha feliz).
   * [ ] `test_validation_error` (422).
   * [ ] `test_forbidden` (403, com usuário sem permissão).
   * [ ] `test_not_found` (404 com SID inexistente).
   * [ ] `test_not_ready` / `submission_in_progress` (409, se aplicável).
   * [ ] `test_file_not_found` (410, se houver geração de arquivos).

3. **pytest de modelos** (como já exibido nas docs de Pydantic):

   * [ ] Normalização (trim, lower, CPF, telefone, etc.).
   * [ ] Regras de negócio simples (período de datas, formatos válidos).

---

> _Criado em 2025-12-02_