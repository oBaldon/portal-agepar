# Portal AGEPAR

Monorepo do **Portal AGEPAR** com **BFF FastAPI**, **Host React/Vite/TypeScript**,
**Docs em Docusaurus** e **PostgreSQL** no ambiente de desenvolvimento.

> Este README foi alinhado ao **estado atual do repositório**. Onde houver dívida
> técnica ou desvio de segurança, o texto explicita isso em vez de documentar o
> “estado desejado”.

---

## Visão geral

O repositório hoje está organizado em quatro pilares:

- **BFF** em `apps/bff`  
  FastAPI, autenticação local com sessão persistida em banco, catálogo e automações.
- **Host** em `apps/host`  
  React + Vite + TypeScript; carrega o catálogo, aplica RBAC de vitrine e embute
  módulos via `<iframe>`.
- **Docs** em `apps/docs-site`  
  Docusaurus v3, servido em dev via proxy do Host em **`/devdocs/`**.
- **Infra** em `infra/`  
  Docker Compose dividido em `docker-compose.dev.yml` + `docker-compose.pg.yml`.

---

## Estado atual da stack

### Backend
- Python 3.11
- FastAPI
- Pydantic v2
- psycopg 3
- PostgreSQL
- autenticação **local** com sessão persistida em `auth_sessions`
- modo **mock legado** opcional via `AUTH_LEGACY_MOCK=1`

### Frontend
- React 18
- Vite 6
- TypeScript
- Tailwind CSS 4
- React Router 6

### Docs
- Docusaurus v3
- Mermaid
- TypeDoc / OpenAPI / pdoc (scripts auxiliares)

### Infra dev
- Docker Compose
- Postgres 16
- `infra/scripts/dev.sh` como entrypoint operacional recomendado

---

## Estrutura do monorepo

```text
apps/
  bff/                  # FastAPI + auth + automations + db
  host/                 # React/Vite/TypeScript
  docs-site/            # Docusaurus
catalog/
  catalog.dev.json      # catálogo consumido pelo Host
infra/
  docker-compose.dev.yml
  docker-compose.pg.yml
  scripts/dev.sh
  sql/init_db.sql
```

---

## Quickstart correto para o estado atual

### 1) Preparar ambiente

Na raiz do projeto:

```bash
cp .env.example .env
```

> **Observação:** o `.env.example` deste snapshot já está sanitizado para uso de
> laboratório, com placeholders vazios para integrações externas. Ainda assim,
> cada ambiente deve preencher seus próprios segredos fora do versionamento.

### 2) Subir a stack completa de dev + Postgres

A forma mais alinhada ao repositório atual é:

```bash
./infra/scripts/dev.sh up
```

Esse script:
- carrega `.env` da raiz;
- combina `docker-compose.dev.yml` **com** `docker-compose.pg.yml`;
- valida a presença do serviço `postgres`;
- sobe `bff`, `host`, `docs` e `postgres` com os overrides corretos.

### 3) URLs esperadas

- **Host:** `http://localhost:5173`
- **Docs via Host:** `http://localhost:5173/devdocs/`
- **Docs direto no serviço:** `http://localhost:9000/devdocs/`
- **BFF:** `http://localhost:8000`
- **OpenAPI:** `http://localhost:8000/api/docs`

---

## Docker Compose: o que realmente existe

### `infra/docker-compose.dev.yml`
Sobe:
- `bff`
- `host`
- `docs`

### `infra/docker-compose.pg.yml`
Adiciona:
- `postgres`
- `DATABASE_URL` no `bff`

Isso significa que o comando abaixo, isoladamente, **não representa mais o
quickstart real do projeto**:

```bash
docker compose -f infra/docker-compose.dev.yml up -d --build
```

Ele sobe `bff`, `host` e `docs`, mas o `bff` depende de `DATABASE_URL`, que hoje
vem do override de Postgres. Use o script `infra/scripts/dev.sh` ou combine os
dois arquivos explicitamente.

---

## Autenticação e sessão

O comportamento atual é este:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/change-password`
- `POST /api/auth/logout`
- `GET /api/auth/sessions`
- `POST /api/auth/sessions/{session_id}/revoke`
- `GET /api/me`

### Regra prática
- O fluxo principal é **auth local** com sessão persistida em PostgreSQL.
- `run_dev.sh` assume `AUTH_MODE=local` por padrão.
- `docker-compose.dev.yml` hoje injeta `AUTH_MODE=mock`.
- `GET /api/auth/login` é um **atalho legado** e só existe quando
  `AUTH_LEGACY_MOCK=1`.

Em outras palavras: o repositório convive com dois modos de autenticação em dev,
e isso está documentado porque impacta onboarding e troubleshooting.

---

## Host, catálogo e RBAC

O Host:
- lê o catálogo em `GET /catalog/dev`;
- filtra categorias e blocos respeitando `hidden`, `requiredRoles` e
  `superuserOnly`;
- preserva a ordem declarada no catálogo;
- renderiza módulos `iframe` com `src = block.ui.url`;
- expõe a rota self-service de perfil em `/conta/perfil`, fora do catálogo
  principal.

O proxy do Vite hoje aponta para:
- `/api`     → `http://bff:8000`
- `/catalog` → `http://bff:8000`
- `/devdocs` → `http://docs:8000`

Arquivo de referência:
- `apps/host/vite.config.ts`

---

## Catálogo atual

O arquivo `catalog/catalog.dev.json` atualmente publica:

- **8 categorias**
- **18 blocos**

Categorias de negócio expostas:
- Compras
- Gestão de Pessoas
- Produtividade
- Suporte
- Governança & Administração

Categorias/laboratório ocultas:
- Central de Viagens
- Sistema PRIME
- Testes & Lab

Há blocos plenamente implementados e blocos ainda de demonstração, como:
- `dfd`
- `etp`
- `ferias`
- `tasks`
- `support`
- `fileshare`
- `avisos`
- `whoisonline`
- `pca` (ainda apontando para `/api/demo?view=pca`)

O ponto importante do estado atual é que **versão, título e flags canônicas das
automações não ficam mais duplicados na `main.py`**. Cada módulo publicado agora
expõe um `AUTOMATION_META`, e o BFF usa isso para:

- montar `GET /api/automations`;
- sincronizar `version`, `title`, `displayName`, `readOnly` e
  `superuserOnly` ao servir `GET /catalog/dev`;
- validar no startup se o catálogo está coerente com os módulos.

O módulo `profile` continua publicado pelo backend, mas fica fora do catálogo
principal porque é acessado pelo menu da conta (`catalogPublished: false`).

---

## Banco e persistência

O runtime atual do BFF usa **PostgreSQL** e inicializa schema no startup com
`init_db()`.

Tabelas garantidas por `apps/bff/app/db.py`:
- `submissions`
- `automation_audits`
- `fileshare_items`
- `notifications`
- `notification_recipients`
- `platform_alerts`
- `platform_alert_recipients`
- `tasks`
- `task_events`
- `task_comments`

Além disso, `infra/sql/init_db.sql` mantém o schema consolidado de:
- `users`
- `roles`
- `user_roles`
- `auth_sessions`
- `login_attempts`
- estruturas auxiliares de RH e avisos

---

## Automações ativas no código

Routers montados em `apps/bff/app/main.py`:

- `accounts`
- `avisos`
- `controle`
- `controle_ferias`
- `controle_tasks`
- `dfd`
- `etp`
- `ferias`
- `fileshare`
- `form2json`
- `ponto_saldo`
- `profile`
- `support`
- `tasks`
- `usuarios`
- `whoisonline`

Há ainda:
- `task_weekly_email.py`
- `task_weekly_report.py`

que não expõem UI própria, mas suportam o envio/resumo semanal de tarefas.

No módulo de tarefas, o estado atual já inclui um **compilado semanal** com
duas formas de uso:

- **download manual** pelo painel `Controle > Tarefas`, respeitando o escopo do
  usuário logado;
- **anexo de e-mail semanal** por cargo, gerado pelo scheduler.

Ambos usam o mesmo gerador de workbook, mas com **escopos diferentes**. O
critério do compilado também foi corrigido: a planilha passou a incluir tarefas
que **já estavam em andamento ao entrar na semana**, além das iniciadas,
concluídas ou canceladas no período.

---

## Testes no estado atual

### O que existe
- smoke tests manuais e cURLs documentados
- testes manuais de navegação, proxy e RBAC

### O que não existe no repo
- suíte `pytest`
- suíte `Vitest`
- CI automatizada versionada em `.github/workflows`

Esse ponto é relevante porque o projeto já tem superfície suficiente para sofrer
regressões silenciosas.

---

## Segurança: estado atual e passivos já identificados

O repositório já implementa:
- CORS com lista de origens
- cookie de sessão
- sessão persistida em banco
- RBAC no BFF e no Host
- auditoria

Mas também carrega passivos que a documentação agora explicita:

- `.env.example` está sanitizado neste snapshot, mas continua sendo apenas um exemplo de laboratório;
- `iframe` do Host ainda é renderizado sem `sandbox`;
- `SessionMiddleware` está com `https_only=False` no estado atual;
- não há proteção explícita de CSRF documentada/implementada para o modelo com cookie.

---

## Problemas comuns

### BFF não sobe
Confirme que o Postgres entrou na composição e que `DATABASE_URL` foi injetada.
O caminho recomendado é `./infra/scripts/dev.sh up`.

### `/devdocs` retorna 404 ou erro de proxy
Cheque:
- se o serviço `docs` está de pé;
- se o Host subiu depois do serviço `docs`;
- se `apps/docs-site/docusaurus.config.ts` continua com `baseUrl: "/devdocs/"`.

### Login falha em dev
Confirme o modo efetivo:
- `AUTH_MODE=local` com usuário existente no banco; ou
- `AUTH_LEGACY_MOCK=1` para habilitar o atalho legado `GET /api/auth/login`.

### Docs locais com lock inconsistente
`apps/docs-site` hoje possui **`package-lock.json` e `pnpm-lock.yaml`**.
No container, a stack usa **npm**. Localmente, escolha um gerenciador e evite
misturar locks ao mesmo tempo.

---

## Diretrizes para implementações futuras

Antes de evoluções sensíveis, a ordem de leitura recomendada é:

- `README.md`
- `IMPLEMENTACOES_FUTURAS.md`
- `apps/docs-site/docs/dev-guide.md`
- `apps/docs-site/docs/15-apêndices/05-diretrizes-para-implementações-futuras-e-pontos-sensíveis.md`
- `apps/docs-site/docs/15-apêndices/06-checklist-de-validação-para-mudanças-futuras.md`

Esses arquivos concentram:
- bootstrap real do ambiente,
- diferenças entre estado atual e premissas antigas,
- pontos sensíveis de auth, catálogo, docs e suporte,
- checklist mínimo para validar que a stack continua funcional.

---

## Onde continuar lendo

- `apps/docs-site/docs/intro.md`
- `apps/docs-site/docs/dev-guide.md`
- `apps/docs-site/docs/06-bff-fastapi/`
- `apps/docs-site/docs/07-automations-padrão-de-módulos/`
- `apps/docs-site/docs/08-banco-de-dados-persistência/`
