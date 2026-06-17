---
id: auditoria-estado-atual-do-repositorio
title: "Auditoria do estado atual do repositório"
sidebar_position: 5
---

Esta página consolida o que o código realmente implementa hoje e os principais
passivos observáveis sem depender de premissas antigas.

## Stack real do monorepo

- **BFF**: FastAPI em `apps/bff`
- **Host**: React 18 + Vite 6 + TypeScript em `apps/host`
- **Docs**: Docusaurus v3 em `apps/docs-site`
- **Banco**: PostgreSQL em dev
- **Orquestração**: `infra/docker-compose.dev.yml` + `infra/docker-compose.pg.yml`

## Contratos observados no código

### Host
- proxy de `/api` e `/catalog` para `http://bff:8000`
- proxy de `/devdocs` para `http://docs:8000`
- catálogo em `catalog/catalog.dev.json`
- blocos iframe renderizados pelo Host com regras de RBAC de vitrine
- rota de perfil self-service em `/conta/perfil`, fora do catálogo principal

### BFF
- `APP = FastAPI(..., docs_url="/api/docs", redoc_url="/api/redoc")`
- `init_db()` roda no startup
- autenticação local com sessão persistida em banco
- `AUTH_LEGACY_MOCK=1` mantém o atalho legado de mock
- módulos ativos para DFD, ETP, férias, tarefas, fileshare, suporte, avisos, usuários e outros
- `GET /api/automations` é montado a partir de `AUTOMATION_META` de cada módulo
- `GET /catalog/dev` reconcilia metadados canônicos (`version`, `title`,
  `displayName`, `readOnly`, `superuserOnly`) antes de responder
- o startup valida a consistência entre catálogo e automações publicadas
- `profile` é publicado pelo backend, mas marcado como `catalogPublished: false`

### Banco
- `infra/sql/init_db.sql` inicializa o domínio base de auth/RBAC/auditoria/RH
- `apps/bff/app/db.py` garante tabelas operacionais como `submissions`,
  `automation_audits`, `notifications`, `tasks` e `fileshare_items`

### Tarefas e compilado semanal
- `tasks.py` é o módulo operacional de tarefas
- `controle_tasks.py` expõe a visão consolidada gerencial e o download manual
  do compilado semanal
- `task_weekly_report.py` gera o workbook XLSX
- `task_weekly_email.py` executa o envio semanal por cargo
- o critério do compilado já considera tarefas que **estavam em andamento ao
  entrar na semana**, não apenas tarefas criadas no período

## Principais passivos ainda observáveis

- quickstart alternativo fora de `infra/scripts/dev.sh` ainda é fácil de errar,
  porque o BFF depende do compose com Postgres;
- o Host continua embutindo módulos em `iframe` sem `sandbox`;
- o repositório continua sem suíte de testes automatizados versionada;
- coexistem `package-lock.json` e `pnpm-lock.yaml` no projeto `apps/docs-site`;
- a stack de docs ainda instala dependências com warnings de `npm audit` e
  pacotes deprecated no ambiente dev;
- ainda existem nomes históricos em alguns arquivos da documentação.

## O que mudou nesta revisão

- o catálogo estático foi saneado para refletir títulos, versões e flags do
  backend;
- a centralização de metadados das automações saiu da `main.py` e foi para os
  próprios módulos via `AUTOMATION_META`;
- o compilado semanal de tarefas deixou de esconder tarefas antigas que seguem
  em execução;
- a planilha semanal ficou mais legível para usuários leigos, com destaque para
  descrição da atividade e cabeçalhos mais claros.

## Leitura relacionada

- `../../dev-guide`
- `../../02-ambiente-dev-setup`
- `../../08-banco-de-dados-persistência`
- `../../14-guias-de-produto-fluxo-compras-público`
