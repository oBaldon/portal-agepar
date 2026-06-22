---
id: diretrizes-para-implementacoes-futuras-e-pontos-sensiveis
title: "Diretrizes para implementações futuras e pontos sensíveis"
sidebar_position: 5
---

Esta página concentra premissas práticas para futuras implementações no Portal AGEPAR.

Ela foi pensada para reduzir dois riscos recorrentes:

1. evoluir o repositório com base em uma premissa antiga;
2. alterar uma área sensível sem revisar os acoplamentos que já existem.

## 1) Leitura recomendada antes de mexer

Antes de mudanças em auth, sessão, catálogo, docs, `support` ou `whoisonline`, revise:

- `README.md`
- `IMPLEMENTACOES_FUTURAS.md`
- `docs/dev-guide.md`
- `07-automations-padrão-de-módulos/10-inventário-de-automações-e-blocos-do-estado-atual`
- `08-banco-de-dados-persistência/06-inventário-de-tabelas-e-domínios-do-estado-atual`

## 2) Premissas atuais da stack

### 2.1. Docs usam Docusaurus e `/devdocs/`

A documentação técnica atual está em `apps/docs-site` e roda com:

- **Docusaurus v3**
- `baseUrl: "/devdocs/"`
- proxy do Host em `http://localhost:5173/devdocs/`

Consequência prática:
- qualquer mudança em `docusaurus.config.ts`, `vite.config.ts` ou build do Host precisa preservar esse prefixo ou atualizar a documentação junto.

### 2.2. O ambiente dev real usa Postgres

O BFF depende do override:

- `infra/docker-compose.pg.yml`

Consequência prática:
- subir só `infra/docker-compose.dev.yml` não representa o ambiente recomendado;
- scripts, instruções de bootstrap e troubleshooting devem continuar apontando para `./infra/scripts/dev.sh up`.

### 2.3. Auth em dev tem dois comportamentos possíveis

Hoje convivem duas referências:

- `apps/bff/run_dev.sh` → `AUTH_MODE=local`
- `infra/docker-compose.dev.yml` → `AUTH_MODE=mock`

Consequência prática:
- qualquer mudança em login, sessão ou troubleshooting precisa deixar claro qual caminho está sendo testado.

### 2.4. `AUTOMATION_META` faz parte do contrato publicado

O catálogo ainda existe, mas o BFF também usa `AUTOMATION_META` para:

- expor `GET /api/automations`,
- sincronizar metadados no `GET /catalog/dev`,
- validar consistência no startup.

Consequência prática:
- não basta alterar `catalog/catalog.dev.json`;
- automações, catálogo e validação de startup precisam permanecer coerentes entre si.

### 2.5. `support` e `whoisonline` têm acoplamento de navegação

O fluxo administrativo atual funciona assim:

- `whoisonline` continua restrito a superuser;
- a UI de `whoisonline` expõe um botão para o painel de suporte;
- o painel administrativo de suporte vive em `support/admin.html`.

Consequência prática:
- mudanças de navegação, RBAC, nomes de rota ou visibilidade precisam considerar os dois módulos ao mesmo tempo.

## 3) Arquivos que merecem leitura antes de evoluções maiores

### Núcleo da aplicação
- `apps/bff/app/main.py`
- `apps/bff/app/db.py`
- `apps/bff/app/auth/routes.py`
- `apps/bff/app/auth/rbac.py`
- `catalog/catalog.dev.json`

### Host
- `apps/host/src/App.tsx`
- `apps/host/src/types.ts`
- `apps/host/src/lib/catalog.ts`
- `apps/host/vite.config.ts`

### Automações com acoplamento mais sensível
- `apps/bff/app/automations/support.py`
- `apps/bff/app/automations/whoisonline.py`
- `apps/bff/app/automations/controle.py`
- `apps/bff/app/automations/fileshare.py`
- `apps/bff/app/automations/tasks.py`

## 4) Mudanças que exigem validação explícita

### Sessão e cookies
Requer validação dedicada qualquer mudança em:
- `SessionMiddleware`
- `same_site`
- `https_only`
- política de cookies em fluxos iframe

### Docs e proxy
Requer validação dedicada qualquer mudança em:
- `apps/docs-site/docusaurus.config.ts`
- `apps/host/vite.config.ts`
- base path `/devdocs/`

### Catálogo e automações
Requer validação dedicada qualquer mudança em:
- `AUTOMATION_META`
- `catalog/catalog.dev.json`
- regras de sincronização do `GET /catalog/dev`
- consistência validada no startup do BFF

### Support / whoisonline
Requer validação dedicada qualquer mudança em:
- painel administrativo de chamados,
- `ticket_type`,
- RBAC de leitura administrativa,
- navegação entre `whoisonline` e `support`.

## 5) Passivos conhecidos para tratar em janela própria

Estes pontos existem, mas não são bons candidatos para ajustes rápidos sem janela dedicada:

- Host com `iframe` sem `sandbox`;
- `SessionMiddleware` ainda com `https_only=False`;
- ausência de proteção explícita de CSRF para o modelo com cookie;
- ausência de suíte automatizada versionada;
- coexistência de `package-lock.json` e `pnpm-lock.yaml` em `apps/docs-site`.

## 6) Regra prática para futuras entregas

Sempre que uma entrega tocar em pontos sensíveis:

1. alinhe primeiro a premissa operacional;
2. depois ajuste código;
3. por fim atualize README, docs e checklists compatíveis com a mudança real.

Essa ordem reduz bastante o risco de documentação ficar “correta no papel, mas errada no comportamento”.
