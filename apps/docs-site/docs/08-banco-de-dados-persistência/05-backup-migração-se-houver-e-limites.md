---
id: backup-migração-se-houver-e-limites
title: "Backup/migração (se houver) e limites"
sidebar_position: 5
---

Esta página amarra três assuntos relacionados à **persistência** no Portal AGEPAR:

- Onde os dados vivem (PostgreSQL + diretório de uploads).
- Como pensar em **backup/restore** e **migração de schema**.
- Quais são os **limites** já implementados (tamanho, TTL, paginação, limpeza).

> Referências principais no repositório:  
> `infra/docker-compose.dev.yml`  
> `infra/docker-compose.pg.yml`  
> `infra/scripts/dev_down.sh`  
> `infra/scripts/dev_fresh.sh`  
> `infra/sql/init_db.sql`  
> `apps/bff/app/db.py`  
> `apps/bff/app/automations/fileshare.py`  

---

## 1) Onde os dados vivem

### 1.1. Banco de dados (PostgreSQL)

O banco padrão em dev é um **Postgres 16** definido em:

- `infra/docker-compose.pg.yml`

Trechos relevantes:

```yaml title="infra/docker-compose.pg.yml (trecho simplificado)"
services:
  postgres:
    image: postgres:16-alpine
    container_name: portal-agepar-postgres
    environment:
      POSTGRES_DB: ${PGDATABASE:-portal}
      POSTGRES_USER: ${PGUSER:-portal}
      POSTGRES_PASSWORD: ${PGPASSWORD:-portaldev}
      TZ: UTC
      PGTZ: UTC
    ports:
      - "${PGPORT_MAP:-5432}:5432"
    # ... volumes, healthcheck, etc.

volumes:
  pg_data:
    labels:
      org.agepar.project: portal-agepar
      org.agepar.volume: pg_data
````

Pontos importantes:

* Há um **volume nomeado** `pg_data` associado ao Postgres.
* Enquanto o volume existir, os dados do banco são preservados, mesmo que o container
  seja destruído/recriado.
* O BFF se conecta via `DATABASE_URL` (construída a partir de `PG*`), e no startup
  roda `init_db()` (ver páginas anteriores) para garantir `submissions`,
  `automation_audits` e `fileshare_items`.

### 1.2. Arquivos de uploads (fileshare)

A automação `fileshare` grava arquivos em disco (metadados vão para o Postgres):

* Caminho base configurado via `UPLOAD_ROOT` (default `/data/uploads`):

```python title="apps/bff/app/automations/fileshare.py (trecho)" showLineNumbers
UPLOAD_ROOT = Path(os.getenv("UPLOAD_ROOT", "/data/uploads")).resolve()
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
```

Para que **backup/restore** faça sentido, é preciso pensar sempre em **duas peças**:

1. O banco (`pg_data` / Postgres).
2. O diretório de uploads (`UPLOAD_ROOT`, montado como volume ou bind no BFF).

---

## 2) Backups (dev e além)

Não há, hoje, um job automatizado de backup dentro do repositório.
A responsabilidade é da **infra** (cron, job de Kubernetes, ferramenta corporativa, etc.).

Mesmo assim, o repo já facilita alguns fluxos.

### 2.1. Dev local (uso de laboratório)

Em dev, a abordagem típica é:

* **Sem SLA de backup**: o banco é considerado “descartável”.
* Scripts que **apagam tudo** (inclusive DB) são parte do fluxo:

`infra/scripts/dev_down.sh`:

```bash title="infra/scripts/dev_down.sh" showLineNumbers
docker compose \
  -f "${INFRA_DIR}/docker-compose.dev.yml" \
  -f "${INFRA_DIR}/docker-compose.pg.yml" \
  down -v

echo "🛑 Stack dev+pg derrubado e volumes removidos."
```

> `down -v` remove containers **e volumes** → inclusive o `pg_data`.

`infra/scripts/dev_fresh.sh`:

```bash title="dev_fresh.sh (cabeçalho)" showLineNumbers
# Uso:
#   ./infra/scripts/dev_fresh.sh           # zera tudo, inclusive DB (pg_data)
#   ./infra/scripts/dev_fresh.sh --keep-db # preserva DB, zera containers e imagens
```

Ou seja:

* Se rodar `dev_down.sh` ou `dev_fresh.sh` sem `--keep-db`, o banco dev vai embora.
* Se quiser preservar dados de dev, use:

  * `dev_fresh.sh --keep-db` **ou**
  * `docker compose ... down` **sem** `-v`.

Mesmo em dev, se quiser “tirar um snapshot” antes de quebrar tudo:

```bash title="Dump rápido do banco dev" showLineNumbers
# Dump lógico do banco 'portal' para um arquivo .sql
docker exec -i portal-agepar-postgres \
  pg_dump -U "${PGUSER:-portal}" "${PGDATABASE:-portal}" \
  > backup-portal-dev-$(date +%F).sql
```

### 2.2. Homolog / Produção (recomendação)

Para ambientes “de verdade”, o recomendável é:

1. **Backup lógico diário** com `pg_dump`:

   * Full dump (`pg_dump`) ou schema + dados críticos.
   * Solo ou via ferramentas (pgBackRest, Barman, etc.).
2. **Retenção definida** (ex.: 30 dias de diários + 6 meses de semanais).
3. **Inclusão do diretório de uploads** (`UPLOAD_ROOT`):

   * backup de filesystem (tar, snapshot de volume, etc.),
   * com retenção alinhada ao banco.

Exemplo de comando lógico (ajuste para sua infra):

```bash title="Exemplo conceitual para cron" showLineNumbers
PGURL="postgresql://portal:***@postgres:5432/portal"
pg_dump "$PGURL" | gzip > /backup/portal-agepar-$(date +%F).sql.gz

# Em paralelo, backup do diretório de uploads
tar czf /backup/uploads-$(date +%F).tar.gz /data/uploads
```

> **Decisão de produto:** o Portal AGEPAR **não** tenta fazer backup por conta própria.
> A suposição é que o banco (e volumes) estão sob uma política corporativa de backup.

---

## 3) Migração de schema

### 3.1. Arquivo principal de schema: `infra/sql/init_db.sql`

O schema “global” (usuários, papéis, org, views, etc.) fica em:

* `infra/sql/init_db.sql`

Logo no topo:

```sql title="init_db.sql (cabeçalho)" showLineNumbers
-- ============================================================================
-- Portal AGEPAR — Schema consolidado (PostgreSQL)
-- Idempotente, sem duplicações e sem código de teste.
-- ============================================================================

SET search_path = public;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
```

E mais adiante:

* `CREATE TABLE IF NOT EXISTS ...`
* `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...`
* `CREATE INDEX IF NOT EXISTS ...`
* Blocos `BEGIN; ... COMMIT;` para seeds idempotentes (org_units, etc).

A ideia:

* Você pode aplicar o arquivo **múltiplas vezes** sem quebrar nada.
* Quando novos campos são adicionados, eles aparecem como `ADD COLUMN IF NOT EXISTS`.
* O arquivo funciona tanto para **cluster vazio** quanto para **cluster já existente**.

### 3.2. Schema das automações: `app/db.py`

As tabelas específicas das automações são criadas por `init_db()` no BFF:

* `apps/bff/app/db.py` → função `init_db()`:

  * `CREATE TABLE IF NOT EXISTS submissions (...)`
  * `CREATE TABLE IF NOT EXISTS automation_audits (...)`
  * `CREATE TABLE IF NOT EXISTS fileshare_items (...)`
  * `CREATE INDEX IF NOT EXISTS ...`
  * `CREATE OR REPLACE FUNCTION touch_updated_at() ...`
  * `DROP TRIGGER IF EXISTS ...; CREATE TRIGGER ...`

Essa função roda no **startup do FastAPI** (`APP.on_event("startup")` em `main.py`) e é
responsável por:

* Garantir que as tabelas “mínimas” de automations existam.
* Aplicar ajustes idempotentes em índices/constraints/triggers.

### 3.3. Fluxo recomendado para alteração de schema

Quando for necessário evoluir o schema (ex.: novo índice, nova coluna):

1. Atualizar **`infra/sql/init_db.sql`**:

   * adicionar `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`,
   * ajustar constraints, índices, views, etc.

2. Se for algo relacionado a automations (`submissions`, `automation_audits`, `fileshare_items`):

   * atualizar também `app/db.py` (para que `init_db()` reflita a mudança).

3. Aplicar em ambientes existentes:

   * dev: `psql -f infra/sql/init_db.sql` apontando para o banco dev
     (ou recriar o cluster, se cómodo).
   * homolog/prod: via pipeline ou job com `psql -f` em janela controlada.

4. Só usar **scripts destrutivos** (DROP COLUMN, renomear coluna, migração pesada de
   dados) em arquivos separados, conscientemente versionados.

> Não existe hoje integração com Alembic ou outra ferramenta de migração.
> O “contrato” é: **DDL idempotente em SQL + init_db() no BFF**.

---

## 4) Limites e políticas de retenção

### 4.1. Fileshare — TTL, tamanho de upload e limpeza

A automação `fileshare` é o ponto onde os limites estão mais explícitos.

**TTL (tempo de vida) dos links**:

```python title="fileshare.py — TTLs" showLineNumbers
TTL_MAP = {
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
```

* Forms aceitam `ttl` como `"1d" | "7d" | "30d"`.
* Default no endpoint de upload:

  ```python
  ttl: str = Form("7d")
  ```
* A expiração real é calculada como `_utcnow() + TTL_MAP[ttl]`.

**Limite de tamanho de upload**:

```python title="fileshare.py — limites de upload" showLineNumbers
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", "0"))
UPLOAD_CHUNK_SIZE = int(os.getenv("UPLOAD_CHUNK_SIZE", str(1024 * 1024)))
```

* `MAX_UPLOAD_SIZE`:

  * `0` → **sem limite** na aplicação (vale o limite do servidor/reverso).
  * `>0` → limite em bytes.
* `_save_stream(...)` corta no servidor:

  ```python title="_save_stream" showLineNumbers
  size = 0
  chunk_size = UPLOAD_CHUNK_SIZE if UPLOAD_CHUNK_SIZE > 0 else 1024 * 1024
  with dest.open("wb") as f:
      while True:
          chunk = up.file.read(chunk_size)
          if not chunk:
              break
          f.write(chunk)
          size += len(chunk)
          if MAX_UPLOAD_SIZE and size > MAX_UPLOAD_SIZE:
              ...
              dest.unlink(missing_ok=True)
              raise HTTPException(
                  status_code=413,
                  detail="tamanho do arquivo excede o limite configurado",
              )
  ```

**Limpeza de arquivos expirados**:

```python title="app/db.py — limpeza de expirados" showLineNumbers
def fileshare_cleanup_expired(limit: int = 200) -> int:
    """
    Marca como deletados e remove fisicamente arquivos expirados (best-effort).
    """
    now = _utcnow()
    with _pg() as conn, conn.cursor() as cur:
        # SELECT itens expirados e não deletados (LIMIT :limit)
        # marca deleted_at e remove o arquivo do disco
        ...
        return count
```

E o endpoint administrativo:

```python title="fileshare.py — endpoint de limpeza" showLineNumbers
@router.post("/tasks/cleanup")
def cleanup_now(request: Request, limit: int = 200):
    """
    Executa limpeza imediata de itens expirados.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    if not (_is_super(user) or "admin" in (user.get("roles") or [])):
        raise HTTPException(status_code=403, detail="admin required")

    deleted = db.fileshare_cleanup_expired(limit=limit)
    return {"expired_deleted": deleted}
```

Resumindo:

* **TTL configurável** (1, 7 ou 30 dias).
* **Limite opcional de tamanho** por upload (`MAX_UPLOAD_SIZE`).
* **Limpeza on-demand** via `/api/automations/fileshare/tasks/cleanup`
  (recomendável automatizar via cron/job em produção).

### 4.2. Limites de paginação (submissions e auditoria)

Ainda que o Postgres não imponha um limite “físico” por tabela, a API aplica limites
de **página**:

* `list_submissions` (usuário final):

  * parâmetro `limit` (padrão 50).
* `list_submissions_admin`:

  * `limit` padrão 100 (sem clamp no DB; o clamp vem do lado FastAPI/Query).
* `controle.py` (`/controle/audits`):

  * `limit: int = Query(default=100, ge=1, le=1000)`.

Ou seja:

* Chamadas normais do frontend dificilmente trarão mais do que algumas centenas
  de registros por vez.
* Para relatórios grandes, o caminho recomendado é:

  * iterar com `limit/offset`, **ou**
  * usar endpoints próprios de exportação (ex.: `controle` gera CSV de auditoria).

### 4.3. Retenção de `submissions` e `automation_audits`

Atualmente **não há** rotina automática de expurgo para:

* `submissions`
* `automation_audits`

A ideia de produto é:

* Manter um **histórico completo** das automações (execuções e eventos) até que
  a organização decida uma política de retenção (ex.: 5 anos).
* Qualquer política futura deve considerar:

  * eventuais requisitos legais (controles de compras públicas),
  * volume de dados e custo de armazenamento.

Em termos práticos, para um futuro próximo:

* Arquivamento pode ser feito via **job específico** (SELECT para arquivo externo +
  DELETE/ARCHIVE em lotes).
* O schema já tem índices suficientes para suportar filtros por `created_at`/`at`
  e `kind`, o que facilita cortes por janela de tempo.

---

## 5) Exemplos de fluxo (backup + migração simplificada)

### 5.1. “Snapshot” rápido antes de alterar schema em dev

```bash title="Passo-a-passo em dev" showLineNumbers
# 1) Dump do banco
docker exec -i portal-agepar-postgres \
  pg_dump -U "${PGUSER:-portal}" "${PGDATABASE:-portal}" \
  > /tmp/portal-dev-before-change.sql

# 2) Aplicar alterações no código:
#    - editar infra/sql/init_db.sql
#    - editar apps/bff/app/db.py (se mexer em automations)

# 3) Subir stack (BFF chamará init_db() automaticamente)
./infra/scripts/dev_up.sh

# 4) Se algo quebrar MUITO, restaurar dump
cat /tmp/portal-dev-before-change.sql | \
  docker exec -i portal-agepar-postgres \
    psql -U "${PGUSER:-portal}" "${PGDATABASE:-portal}"
```

### 5.2. Backup + limpeza de expirados (fileshare)

```bash title="Backup + limpeza (esboço)" showLineNumbers
# Dump lógico
docker exec -i portal-agepar-postgres \
  pg_dump -U "${PGUSER:-portal}" "${PGDATABASE:-portal}" \
  > /backup/portal.sql

# Backup dos uploads
docker exec portal-agepar-bff \
  tar czf - /data/uploads > /backup/uploads.tar.gz

# Limpar itens expirados (apenas admin/superuser)
curl -X POST \
  -H "Cookie: session=<session-admin>" \
  http://localhost:8000/api/automations/fileshare/tasks/cleanup
```

---

> _Criado em 2025-12-01_