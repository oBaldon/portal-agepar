---
id: métricas-healthchecks-se-houver
title: "Métricas/healthchecks"
sidebar_position: 3
---

Hoje o Portal AGEPAR não expõe **métricas formais** (ex.: Prometheus), mas já
tem uma base de **healthchecks HTTP** e **checks de container** que cobrem:

- disponibilidade básica do BFF (`/health`),
- versão/configuração em runtime (`/version`),
- conectividade do Postgres (healthcheck no Docker Compose),
- um ping lógico para o eProtocolo (`/api/eprotocolo/ping`),
- além de logs estruturados e auditoria em banco (vistos nas seções anteriores).

> Referências principais no repositório:  
> `apps/bff/app/main.py`  
> `infra/docker-compose.pg.yml`  
> `README.md`

---

## 1) Healthchecks HTTP no BFF

### 1.1. `/health` — liveness do processo

No `apps/bff/app/main.py`:

```python title="apps/bff/app/main.py — /health" showLineNumbers
@APP.get("/health")
def health() -> Dict[str, str]:
    """
    Endpoint de saúde do serviço.

    Retorna
    -------
    dict
        {"status": "ok"}
    """
    return {"status": "ok"}
````

Características:

* **Sem autenticação** — qualquer cliente HTTP pode chamar.
* **Não toca no banco** (nem em serviços externos):

  * é um **liveness check** puro do processo FastAPI/Uvicorn.
* Retorno estável:

  * HTTP 200 + `{"status": "ok"}` quando o app respondeu.

Uso típico:

* probes de liveness em Kubernetes / orquestrador,
* checagem rápida em monitoramento de uptime.

### 1.2. `/version` — metadados de runtime

Ainda em `main.py`:

```python title="apps/bff/app/main.py — /version" showLineNumbers
@APP.get("/version")
def version() -> Dict[str, Any]:
    """
    Versões e parâmetros relevantes do runtime.
    """
    return {
        "app": APP.version,
        "env": ENV,
        "dfd_version": DFD_VER,
        "ferias_version": FERIAS_VER,
        "auth_mode": AUTH_MODE,
        "auth_legacy_mock": AUTH_LEGACY_MOCK,
        "ep_mode": EP_MODE,
        "cors_origins": CORS_ORIGINS,
        "catalog_file": str(CATALOG_FILE),
    }
```

Esse endpoint também:

* **não exige autenticação**,
* não consulta o banco,
* expõe informações úteis para **observabilidade e suporte**:

  * versão da app (`APP.version`),
  * ambiente (`ENV`),
  * versões dos motores de DFD/Férias,
  * modo de autenticação (`AUTH_MODE`, `AUTH_LEGACY_MOCK`),
  * origens CORS efetivas,
  * caminho do arquivo de catálogo.

Recomendações de uso:

* **Monitoramento**:

  * validar se o cluster está rodando o build/versão esperados;
  * usar labels derivadas (env, version) em dashboards.
* **Segurança**:

  * em produção pública, considerar restringir `/version` (IP interno ou auth) se
    o nível de detalhe for considerado sensível.

### 1.3. `/api/eprotocolo/ping` — ping lógico do eProtocolo

No final do `main.py`:

```python title="apps/bff/app/main.py — ping do eProtocolo" showLineNumbers
@APP.get("/api/eprotocolo/ping")
def ep_ping(request: Request) -> Dict[str, Any]:
    """
    Ping do eProtocolo (mock/real, conforme EP_MODE).

    Retorna
    -------
    dict
        { actor, ep_mode, ok }
    """
    user = _get_user_from_session(request)
    actor = (user or {}).get("cpf") or "anonymous"
    return {"actor": actor, "ep_mode": EP_MODE, "ok": True}
```

Hoje ele:

* **depende de sessão** (usa `_get_user_from_session`):

  * sem login → `actor="anonymous"`,
  * com login → `actor=cpf`.
* **Não faz chamada real ao eProtocolo** na versão mock:

  * responde sempre `{"ok": true}` com o `EP_MODE` atual.

Como “métrica”:

* serve mais como **ping lógico** da integração (e para testar sessão),
* pode evoluir no futuro para um healthcheck real (HTTP/Soap/etc. do eProtocolo),
  incluindo latência e resultado no payload.

---

## 2) Healthcheck de banco (Postgres) no Docker Compose

Embora o BFF não verifique o banco em `/health`, o **Postgres em dev** já tem
um healthcheck nativo no Compose:

```yaml title="infra/docker-compose.pg.yml — healthcheck do Postgres" showLineNumbers
services:
  postgres:
    image: postgres:16-alpine
    # ...
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${PGUSER:-portal} -d ${PGDATABASE:-portal} -h localhost"]
      interval: 5s
      timeout: 3s
      retries: 30
```

E o BFF depende disso:

```yaml title="infra/docker-compose.pg.yml — depends_on no BFF" showLineNumbers
  bff:
    # ...
    depends_on:
      postgres:
        condition: service_healthy
```

Consequências:

* O container do BFF **só sobe** depois que o Postgres é considerado saudável
  (`pg_isready` OK).
* Em dev/local, isso já evita várias condições de corrida “BFF subiu antes do DB”.

Para ambientes futuros (Kubernetes, etc.):

* é natural traduzir isso em:

  * **readiness probe** que verifica uma query simples (`SELECT 1`) no banco,
  * combinada com o `/health` do BFF para liveness.

---

## 3) Métricas de alto nível (a partir do que já existe)

Não há, por enquanto, endpoint `/metrics` ou integração explícita com Prometheus /
OpenTelemetry no repositório.

Mesmo assim, com o que já existe, dá para extrair algumas “quase-métricas”:

1. **Contagem de submissões por status**

   * via tabela `submissions`:

     * `status IN ('queued','running','done','error')`,
     * índices por `kind`, `created_at`.
   * pode ser agregada por scripts/relatórios (ex.: jobs externos ou automação `controle`).

2. **Eventos em `automation_audits`**

   * permitem contar:

     * `submitted`, `completed`, `failed`, `download`, `deleted` etc.,
     * por automação (`kind`), usuário, período.

3. **Logs estruturados**

   * `logger.info/exception` com padrões consistentes:

     * `[FERIAS][SUBMIT] ...`,
     * `DFD process done | sid=...`,
     * `fileshare.upload.failed | ...`.

Esses dados podem alimentar:

* dashboards ad hoc (Kibana, Loki, etc.),
* alertas baseados em aumento de `failed` vs `completed`,
* contadores de uso das automations.

> Resumindo: **não há métricas numéricas prontas na API**,
> mas o modelo de dados (submissions/audits) e a padronização de logs permitem
> derivá-las.

---

## 4) Como usar healthchecks na prática

### 4.1. Probes HTTP

Em um orquestrador (Kubernetes, Nomad, etc.), os probes recomendados seriam:

* **Liveness probe**: `GET /health`

  * falhou → restart do pod/container.
* **Readiness probe**: ou

  * `GET /health` + checagem de DB fora do app, **ou**
  * um futuro endpoint `/healthz` que faça `SELECT 1` no Postgres.

Em dev (sem orquestrador), dá para simular:

```bash title="Checando health e version em dev" showLineNumbers
curl -s http://localhost:8000/health
curl -s http://localhost:8000/version | jq .
```

### 4.2. Checagem de banco via `pg_isready`

Mesmo em dev, é possível verificar o DB manualmente:

```bash title="Verificando Postgres" showLineNumbers
docker exec -it portal-agepar-postgres \
  pg_isready -U portal -d portal -h localhost
```

Para monitoramento:

* o mesmo comando usado no `healthcheck` do Compose pode ser usado por scripts
  externos ou agentes de observabilidade.

---

## 5) Próximos passos sugeridos (para métricas “de verdade”)

Quando for o momento de evoluir a observabilidade, o projeto está bem posicionado
para receber:

1. **Endpoint `/metrics` (Prometheus)**

   * exportar:

     * contagens de requisições por rota/resultado,
     * durações de chamadas de automations,
     * número de submissions por status/kind.
   * pode ser implementado com libs como `prometheus_client` e montado em `/metrics`
     protegidos (IP interno ou auth).

2. **Healthcheck “profundo”**

   * novo endpoint (ex.: `/healthz`) que verifica:

     * conexão DB (`SELECT 1`),
     * disco do `UPLOAD_ROOT` (fileshare),
     * eventualmente serviços externos (eProtocolo, etc.).

3. **Alertas baseados em dados existentes**

   * jobs periódicos lendo:

     * `submissions` (picos de `error`),
     * `automation_audits` (`failed` por automação),
   * envio de alerta para o canal de suporte.

---

## 6) Exemplos práticos (cURL)

### 6.1. Health e versão

```bash title="Ping básico do BFF" showLineNumbers
curl -s http://localhost:8000/health
# -> {"status":"ok"}

curl -s http://localhost:8000/version | jq .
# -> { "app": "0.3.0", "env": "dev", "dfd_version": "...", ... }
```

### 6.2. Ping lógico do eProtocolo

```bash title="Ping do eProtocolo (mock)" showLineNumbers
# Sem autenticação
curl -s http://localhost:8000/api/eprotocolo/ping | jq .
# -> { "actor": "anonymous", "ep_mode": "mock", "ok": true }

# Com sessão (após login)
curl -i -c /tmp/cookies.txt \
  -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"identifier":"dev@example.com","password":"dev"}'

curl -s -b /tmp/cookies.txt \
  http://localhost:8000/api/eprotocolo/ping | jq .
# -> { "actor": "<cpf-dev>", "ep_mode": "mock", "ok": true }
```

---

> _Criado em 2025-12-01_