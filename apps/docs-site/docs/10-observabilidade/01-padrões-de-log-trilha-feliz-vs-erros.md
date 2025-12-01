---
id: padrões-de-log-trilha-feliz-vs-erros
title: "Padrões de log (trilha feliz vs erros)"
sidebar_position: 1
---

A observabilidade do Portal AGEPAR começa simples: **logs bem feitos** no BFF, com:

- trilha feliz consistente em `INFO`,
- erros em `ERROR` (com contexto suficiente),
- mensagens padronizadas em pontos-chave (startup, autenticação, automations).

> Referências principais no repositório:  
> `apps/bff/app/main.py`  
> `apps/bff/app/db.py`  
> `apps/bff/app/auth/routes.py`  
> `apps/bff/app/automations/*.py` (especialmente `dfd.py`, `ferias.py`, `fileshare.py`)  

---

## 1) Visão geral: filosofia de logging

Em linha com o plano, o BFF adota estas ideias:

- **Trilha feliz:**
  - usar `logger.info` para:
    - startup da aplicação (ENV, AUTH_MODE, CORS, etc.),
    - operações de alto nível bem-sucedidas (login OK, submissão criada, tarefa concluída),
    - checkpoints de background tasks.
- **Erros:**
  - usar `logger.error` (`logger.exception` quando dentro de um `except`) para:
    - falhas em automations (geração de DOCX/PDF, IO, banco),
    - erros de infraestrutura (conexão com DB, disco, etc.),
  - sempre com _algum_ contexto de negócio (kind, submission id, usuário) — sem vazar dados sensíveis.
- **Separação de responsabilidades:**
  - logs de **execução** vão para o logger Python,
  - eventos de **negócio/auditoria** vão para a tabela `automation_audits`
    (ver seção de banco de dados / auditoria).

O objetivo não é “logar tudo”, e sim:

> Ter linhas de log que respondam “o que aconteceu?”  
> sem precisar ligar o debugger em produção.

---

## 2) Startup do BFF: logs mínimos obrigatórios

Logo no `main.py`, o BFF registra o estado inicial:

```python title="apps/bff/app/main.py — logs de startup" showLineNumbers
logger = logging.getLogger("portal-agepar.bff")

ENV = os.getenv("ENV", "dev")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
AUTH_MODE = os.getenv("AUTH_MODE", "local")
AUTH_LEGACY_MOCK = os.getenv("AUTH_LEGACY_MOCK", "0").lower() in ("1", "true", "yes")
EP_MODE = os.getenv("EP_MODE", "mock")

CORS_ORIGINS = [...]
CATALOG_FILE = Path(os.getenv("CATALOG_FILE", "/catalog/catalog.dev.json"))

logger.info(
    "ENV=%s | AUTH_MODE=%s | AUTH_LEGACY_MOCK=%s | LOG_LEVEL=%s | EP_MODE=%s",
    ENV, AUTH_MODE, AUTH_LEGACY_MOCK, LOG_LEVEL, EP_MODE,
)
logger.info("CORS_ORIGINS=%s | CATALOG_FILE=%s", ",".join(CORS_ORIGINS), str(CATALOG_FILE))
````

E no evento de startup:

```python title="apps/bff/app/main.py — init_db no startup" showLineNumbers
@APP.on_event("startup")
def _startup() -> None:
    init_db()
    logger.info("DB initialized (Postgres)")
    logger.info("DFD engine version: %s", DFD_VER)
    logger.info("FERIAS engine version: %s", FERIAS_VER)
```

Padrões aqui:

* **Nível**: `INFO`.
* **Formato**: mensagens curtas + valores relevantes em parâmetros (para facilitar parse).
* **Contexto**: ENV, modo de autenticação, endpoints, versões de automations.

Se algo crítico quebrar no startup (ex.: `init_db()` falhar), a exceção sobe até o
servidor (Uvicorn/docker), tornando o problema bem visível na subida dos containers.

---

## 3) Trilha feliz nas automations (INFO)

### 3.1. Submissão criada e processada

Nas automations (ex.: `dfd.py`, `ferias.py`, `form2json.py`), o fluxo típico é:

1. **Receber request** → validar payload.
2. **Criar submission** → logar em `INFO` com `kind` e `sid`.
3. **Processar em background** → logs em pontos-chave (`queued`, `running`, `done`).

Exemplo ilustrativo:

```python title="Padrão sugerido de logs na automação" showLineNumbers
logger = logging.getLogger("portal-agepar.automations.dfd")

def _enqueue_submission(user: dict, body: DfdIn) -> str:
    sid = str(uuid4())
    payload = body.model_dump(mode="json")

    logger.info(
        "DFD submit queued | sid=%s | cpf=%s | numero=%s | protocolo=%s",
        sid,
        user.get("cpf"),
        body.numero,
        body.protocolo,
    )

    insert_submission(
        {
            "id": sid,
            "kind": KIND,
            "version": DFD_VERSION,
            "actor_cpf": user.get("cpf"),
            "actor_nome": user.get("nome"),
            "actor_email": user.get("email"),
            "payload": payload,
            "status": "queued",
            "result": None,
            "error": None,
        }
    )
    add_audit(KIND, "submitted", user, {"sid": sid, "protocolo": body.protocolo})
    return sid
```

Na task de processamento:

```python title="Background task — trilha feliz" showLineNumbers
def _process_submission(sid: str, actor: dict) -> None:
    logger.info("DFD process start | sid=%s | actor=%s", sid, actor.get("cpf"))

    try:
        update_submission(sid, status="running")
        add_audit(KIND, "running", actor, {"sid": sid})

        # ... gerar documentos, etc.

        update_submission(sid, status="done", result=manifest, error=None)
        add_audit(KIND, "completed", actor, {"sid": sid})
        logger.info("DFD process done | sid=%s", sid)

    except Exception as exc:
        # erro tratado na seção seguinte (ERROR/exception)
        ...
```

Características da trilha feliz:

* logs curtos, com **chaves estáveis**:

  * `sid`, `cpf`, `kind`, `numero`, `protocolo` etc.
* nível `INFO` para cada marco importante:

  * submissão enfileirada,
  * processamento iniciado,
  * conclusão com sucesso.

### 3.2. Operações “administrativas”

Automations como `controle`, `usuarios`, `whoisonline` e `accounts` também podem logar:

* **consultas administrativas** (por exemplo, lista de auditoria com filtros),
* **ações de gestão** (criação/edição de usuários, revogação de sessão).

Exemplo sintético:

```python title="Exemplo em usuarios.py (trilha feliz)" showLineNumbers
logger = logging.getLogger("portal-agepar.automations.usuarios")

def create_user(actor: dict, payload: UsuarioIn) -> dict:
    logger.info(
        "usuarios.create | actor=%s | email=%s",
        actor.get("cpf"),
        payload.email,
    )
    # ... cria usuário, audita, etc.
```

---

## 4) Logs de erro (ERROR / exception) com contexto

### 4.1. Exceções em automations

Quando algo quebra no processamento (IO, DB, template, etc.), o padrão esperado é:

1. **Registrar o erro em `submissions`** (`status="error"`, campo `error`).
2. **Adicionar evento em `automation_audits`** (`action="failed"`).
3. **Logar em `ERROR` com contexto mínimo**, de preferência com stack trace.

Exemplo:

```python title="Erro em background task" showLineNumbers
def _process_submission(sid: str, actor: dict) -> None:
    try:
        # ... processamento
    except Exception as exc:
        logger.exception(
            "DFD process failed | sid=%s | cpf=%s | msg=%s",
            sid,
            actor.get("cpf"),
            str(exc),
        )
        update_submission(sid, status="error", error=str(exc))
        add_audit(KIND, "failed", actor, {"sid": sid, "error": str(exc)})
```

Observações:

* `logger.exception(...)` registra **stack trace completo** automaticamente.

* O contexto (sid, cpf) facilita correlacionar:

  * log ⇄ `submissions` ⇄ `automation_audits` ⇄ UI.

* `error=str(exc)` guarda uma mensagem amigável em banco, evitando expor stack trace na UI.

### 4.2. Erros em infra/DB (`app/db.py`)

Nas funções que interagem com o banco, o padrão é:

* logar em `ERROR` ao capturar exceções de Postgres,
* incluir informações de operação (tipo de query, parâmetros-chave),
* retornar erro coerente para a automação (que então decide se responde 500/400/etc.).

Exemplo ilustrativo:

```python title="db.py — padrão de log em erro de DB" showLineNumbers
logger = logging.getLogger("portal-agepar.db")

def insert_submission(sub: dict) -> None:
    try:
        with _pg() as conn, conn.cursor() as cur:
            # ... executar INSERT
    except Exception:
        logger.exception(
            "DB error on insert_submission | kind=%s | actor_cpf=%s",
            sub.get("kind"),
            sub.get("actor_cpf"),
        )
        raise
```

> Regra de ouro: **não** logar o payload completo em caso de erro,
> para não vazar dados sensíveis ou documentos grandes nos logs.

### 4.3. Erros de autenticação e login

Em `auth/routes.py`, falhas de login podem gerar logs em `INFO` ou `WARNING`/`ERROR`:

* logar tentativas de login inválido (sem password, usuário bloqueado),
* incluir IP e user-agent de forma moderada (sem exagerar em volume).

Padrão sugerido:

```python title="auth/routes.py — log de falha de login" showLineNumbers
logger = logging.getLogger("portal-agepar.auth")

def login(payload: LoginIn, request: Request):
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "-")

    # ... validação
    if not user or not check_password(user, payload.password):
        logger.warning(
            "login.failed | identifier=%s | ip=%s | ua=%s",
            payload.identifier,
            ip,
            ua,
        )
        raise HTTPException(status_code=401, detail="invalid credentials")
```

---

## 5) Logs vs Auditoria: papéis complementares

É importante diferenciar:

* **Logs de aplicação** (logger Python):

  * foco em **debug e operação**,
  * podem ser descartados após certa retenção (ex.: 7–30 dias),
  * são mais volumosos (incluem stack trace, etc.).
* **Auditoria de automations** (`automation_audits`):

  * foco em **rastreabilidade de negócio** (“quem fez o quê, quando e onde”),
  * tem retenção mais longa (meses/anos, conforme política),
  * alimenta telas de Controle e relatórios.

Fluxo típico de um erro:

* log em `ERROR` + `logger.exception(...)` no BFF,
* registro em `automation_audits` com `action="failed"`, `meta={"sid": ..., "error": ...}`,
* registro em `submissions.error` para que a UI mostre um resumo amigável ao usuário.

---

## 6) Boas práticas para novos logs

Quando criar nova automação ou endpoint, use este checklist:

1. **Defina um logger por módulo**

   ```python
   logger = logging.getLogger("portal-agepar.automations.meu_modulo")
   ```
2. **Trilha feliz em INFO**

   * logar apenas marcos relevantes:

     * início/fim de operações caras,
     * submissões criadas,
     * tarefas concluídas.
3. **Erros em ERROR/exception**

   * usar `logger.exception` dentro de `except` para capturar stack trace.
   * incluir contexto mínimo (ids, usuário, kind).
4. **Cuidado com dados sensíveis**

   * não logar payload completo,
   * mascarar valores críticos (documentos, tokens, PII em excesso).
5. **Evitar `print`**

   * sempre usar o logger configurado (encaixa melhor com stacks de log centralizado).
6. **Padronizar prefixos/mensagens**

   * usar padrões como:

     * `"DFD submit queued | sid=%s | ..."`
     * `"FERIAS process done | sid=%s"`
     * `"fileshare.upload.failed | msg=%s"`

---

## 7) Exemplos (cURL) para ver logs em ação

Em dev (via `docker-compose.dev.yml`), é comum acompanhar logs com:

```bash title="Tail dos logs em dev" showLineNumbers
cd infra
./scripts/dev_logs.sh
```

Depois, exercitar:

```bash title="Exemplo de submissão DFD" showLineNumbers
curl -i -c /tmp/cookies.txt \
  -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"identifier":"dev@example.com","password":"dev"}'

curl -i -b /tmp/cookies.txt \
  -X POST "http://localhost:8000/api/automations/dfd/submit" \
  -H "Content-Type: application/json" \
  -d '{"numero":"2025-001","protocolo":"12345/2025","assunto":"Teste","pcaAno":"2025","modeloSlug":"padrao"}'
```

Nos logs do BFF, você deverá enxergar:

* linhas `INFO` de login / criação de sessão,
* linhas `INFO` de submissão DFD (`submit queued`, `process start`, `process done`),
* em caso de erro, uma linha `ERROR` com stack trace.

---

> _Criado em 2025-12-01_