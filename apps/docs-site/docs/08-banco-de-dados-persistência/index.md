---
id: index
title: "Banco de Dados & Persistência"
sidebar_position: 0
---

O Portal AGEPAR usa **PostgreSQL** como banco principal e um diretório de **uploads** para arquivos temporários/gerados.  
O plano original falava em **SQLite no startup**, mas o repositório atual consolidou tudo em **Postgres**, com a função `init_db()` garantindo o schema mínimo das automations no início da aplicação.

## Objetivos
- Explicar como a função `init_db()` (em `apps/bff/app/db.py`) inicializa o schema mínimo no Postgres, tanto no **startup** do BFF quanto via script.
- Descrever as tabelas centrais:
  - `submissions` — execuções/solicitações das automações,
  - `automation_audits` — trilha de auditoria de eventos,
  - `fileshare_items` — metadados de compartilhamento de arquivos temporários.
- Detalhar os campos-chave de `submissions` (`payload`, `status`, `result`, `error`) e como eles modelam o ciclo de vida de uma automação.
- Documentar o modelo de **auditoria de eventos** (quem fez o quê, quando, onde e com quais metadados).
- Amarrar **backup/migração** (Postgres + uploads) e **limites** já presentes (tamanho de upload, paginação, expiração de links, etc.).

## Sumário Rápido
- `01-sqlite-no-startup-init_db` — história do plano com SQLite x implementação atual em PostgreSQL, papel da função `init_db()` e uso em startup/script.
- `02-tabelas-submissions-e-audits` — estrutura das tabelas `submissions` e `automation_audits`, índices e relação com as automations.
- `03-campos-payload-status-result-error` — semântica dos campos principais de `submissions` e boas práticas de uso.
- `04-auditoria-de-eventos` — modelo da tabela `automation_audits` e como automations registram ações relevantes.
- `05-backup-migração-se-houver-e-limites` — visão de onde os dados vivem, backups, migração de schema e limites implementados.

## Visão geral da persistência

A camada de persistência consolida três elementos:

- **PostgreSQL** (via `DATABASE_URL`), inicializado por:
  - `init_db()` em `apps/bff/app/db.py` (cria tabelas/índices idempotentes);
  - scripts SQL em `infra/sql/` (schema global consolidado em `init_db.sql`).
- **Tabelas centrais**:
  - `submissions` — registra cada execução de automação, com payload, status, resultado e erro.
  - `automation_audits` — guarda eventos relacionados às automations (quem, quando, qual `kind`, qual alvo, metadados).
  - `fileshare_items` — controla links temporários de arquivos (quando foram criados, quando expiram, dono, downloads).
- **Diretório de uploads** (`UPLOAD_ROOT`) — onde arquivos enviados/gerados são gravados, normalmente como volume no Docker.

## Tabelas centrais e campos-chave

- `submissions`
  - Representa uma “execução” de automação (`kind`, `version`).
  - Campos de ator: `actor_cpf`, `actor_nome`, `actor_email`.
  - **Campos principais**:
    - `payload` (JSONB) — entrada normalizada da automação.
    - `status` — ciclo de vida (`queued`, `running`, `done`, `error`) com `CHECK` de integridade.
    - `result` (JSONB) — saída final (ex.: caminhos de arquivos, dados calculados).
    - `error` — mensagem/código de erro, quando `status = 'error'`.
  - Índices por data, ator, `kind` e GIN em `payload`/`result` para consultas eficientes.

- `automation_audits`
  - Registra eventos relevantes: `kind`, `at` (timestamp), alvo (`sid`, `user_id`, `session_id`), `meta` (JSONB rico).
  - Usada para rastreabilidade e suporte.

- `fileshare_items`
  - Metadados de links temporários de arquivos: `token`, `path`, `expires_at`, `owner_id`, `downloads`, `deleted_at`.
  - Índices em `created_at`, `expires_at`, `owner_id` e `deleted_at` para facilitar limpeza e consultas.

## Backups, migrações e limites

- **Backups**
  - Banco: volume `pg_data` associado ao Postgres (definido em `infra/docker-compose.pg.yml`).
  - Arquivos: diretório `UPLOAD_ROOT` (também montado como volume/bind).
  - Em dev, o banco é tratado como **descartável** (`dev_down.sh` derruba containers e volumes).
  - Em ambientes corporativos, o backup é responsabilidade da **infra**, mas o repo aponta claramente quais volumes precisam ser protegidos.

- **Migração de schema**
  - Arquivo principal: `infra/sql/init_db.sql` — schema consolidado e idempotente.
  - Usa `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, etc., para permitir evolução gradual sem apagar dados.

- **Limites**
  - **Paginação**: funções de listagem (ex.: `list_submissions`) usam `limit`/`offset` no SQL.
  - **Uploads**: limites de tamanho e leitura em blocos no BFF (`UPLOAD_MAX_SIZE`, `UPLOAD_CHUNK_SIZE`, `_save_stream(...)`).
  - **Expiração**: `fileshare_items.expires_at` e `deleted_at` permitem implementar políticas de retenção e limpeza de arquivos temporários.

## Troubleshooting

- **Erro “DATABASE_URL não configurada para Postgres”**
  - Verificar variáveis de ambiente do BFF (`DATABASE_URL`) e o serviço Postgres no `docker-compose`.
- **`init_db()` falhando no startup**
  - Conferir credenciais do banco, permissões do usuário e se as extensões (`pgcrypto`, `citext`) podem ser criadas.
- **Consultas lentas em submissions/audits**
  - Checar se os índices foram criados (rodar novamente `init_db()` ou aplicar `init_db.sql`).
- **Downloads ou uploads quebrando**
  - Revisar `UPLOAD_ROOT`, limites de tamanho configurados e permissões de escrita/leitura no volume.
- **Diferença entre docs e implementação (SQLite x Postgres)**
  - Priorizar sempre o código atual (`apps/bff/app/db.py` + `infra/sql/init_db.sql`) e usar as menções a SQLite apenas como histórico.

---

> _Criado em 2025-12-04_
