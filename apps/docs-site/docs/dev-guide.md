---
id: dev-guide
title: "Guia de dev (setup, run e leitura do estado atual)"
sidebar_position: 1
---

Este guia serve para duas coisas ao mesmo tempo:

1. colocar o ambiente para rodar;
2. evitar onboarding com premissas antigas que já não representam o repositório.

## Pré-requisitos

- Docker 24+
- Docker Compose v2
- Node 20+ para execução local do Host/Docs
- Python 3.11+ para execução local do BFF
- arquivo `.env` na raiz

## Setup recomendado

Na raiz do projeto:

```bash
cp .env.example .env
./infra/scripts/dev.sh up
```

## Por que usar `infra/scripts/dev.sh`

Porque o estado atual do projeto depende da composição de:
- `infra/docker-compose.dev.yml`
- `infra/docker-compose.pg.yml`

O script já:
- carrega `.env`;
- valida os arquivos;
- sobe a stack completa;
- inclui o serviço `postgres`;
- injeta `DATABASE_URL` corretamente no BFF.

## URLs de desenvolvimento

- Host: `http://localhost:5173`
- Docs via Host: `http://localhost:5173/devdocs/`
- Docs direto: `http://localhost:9000/devdocs/`
- BFF: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/api/docs`

## Modo de autenticação em dev

Há um detalhe importante no estado atual:

- `apps/bff/run_dev.sh` assume `AUTH_MODE=local`;
- `infra/docker-compose.dev.yml` hoje injeta `AUTH_MODE=mock`.

Além disso:
- `POST /api/auth/login` existe como fluxo normal;
- `GET /api/auth/login` é legado e só existe se `AUTH_LEGACY_MOCK=1`.

Sempre confira `/version` para ver o modo efetivo:

```bash
curl -s http://localhost:8000/version | jq .
```

## Estrutura resumida do repositório

```text
apps/
  bff/
  host/
  docs-site/
catalog/
infra/
```

## Principais leituras para começar

- `README.md`
- `apps/bff/app/main.py`
- `apps/bff/app/db.py`
- `apps/bff/app/auth/routes.py`
- `apps/host/src/App.tsx`
- `apps/host/src/types.ts`
- `apps/host/vite.config.ts`
- `catalog/catalog.dev.json`
- `apps/docs-site/docusaurus.config.ts`

## Passivos que o dev precisa conhecer

- `.env.example` está sanitizado neste snapshot, mas continua sendo apenas um
  exemplo de laboratório; segredos reais devem entrar por ambiente.
- O Host usa iframe sem `sandbox`.
- Não há suíte de testes automatizados versionada.
- Há coexistência de `package-lock.json` e `pnpm-lock.yaml` em `apps/docs-site`.
- Parte da documentação antiga ainda falava em MkDocs/SQLite; esta revisão corrige isso.
- Há nomes históricos de alguns arquivos de doc que ainda não refletem o nome final ideal.

## Onde registrar ajustes de documentação

- mudanças de arquitetura: `01-visão-geral-e-arquitetura/`
- mudanças de setup/operação: `02-ambiente-dev-setup/` e `03-build-run-deploy/`
- mudanças de padrão editorial da doc: `13-documentação-docusaurus/06-padrão-editorial-e-template-de-página`
- inventários atualizados de módulos e tabelas:
  - `07-automations-padrão-de-módulos/10-inventário-de-automações-e-blocos-do-estado-atual`
  - `08-banco-de-dados-persistência/06-inventário-de-tabelas-e-domínios-do-estado-atual`
