# Diretrizes para implementações futuras — Plataforma AGEPAR

Este arquivo concentra as premissas e validações que devem orientar evoluções futuras do repositório.

Ele não substitui a documentação completa em `apps/docs-site`, mas serve como um ponto rápido de consulta **antes de mexer em auth, sessão, catálogo, docs, suporte ou automações sensíveis**.

## 1) Leitura recomendada antes de mudanças sensíveis

Comece por esta ordem:

1. `README.md`
2. `IMPLEMENTACOES_FUTURAS.md`
3. `apps/docs-site/docs/dev-guide.md`
4. `apps/docs-site/docs/15-apêndices/05-diretrizes-para-implementações-futuras-e-pontos-sensíveis.md`
5. `apps/docs-site/docs/15-apêndices/06-checklist-de-validação-para-mudanças-futuras.md`

## 2) Premissas atuais que precisam ser preservadas

### 2.1. Stack real do snapshot

- **BFF:** FastAPI em `apps/bff`
- **Host:** React/Vite/TypeScript em `apps/host`
- **Docs:** Docusaurus em `apps/docs-site`
- **Banco dev:** PostgreSQL via `infra/docker-compose.pg.yml`

### 2.2. URLs em dev

- Host: `http://localhost:5173`
- BFF: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/api/docs`
- Docs via Host: `http://localhost:5173/devdocs/`
- Docs direto: `http://localhost:9000/devdocs/`

### 2.3. Comando recomendado para subir tudo

```bash
cp .env.example .env
./infra/scripts/dev.sh up
```

> Não use como referência principal o `docker compose -f infra/docker-compose.dev.yml up` isolado. O BFF depende do override de Postgres em `infra/docker-compose.pg.yml`.

## 3) Pontos não óbvios que impactam futuras implementações

### 3.1. Docs não usam mais MkDocs

A documentação técnica atual vive em `apps/docs-site` e roda com **Docusaurus**, publicada em dev via **`/devdocs/`**.

### 3.2. O BFF hoje depende de PostgreSQL

O runtime atual usa Postgres, mesmo que ainda existam nomes históricos de arquivo ou texto mencionando SQLite.

### 3.3. Há dois modos de autenticação em dev

- `apps/bff/run_dev.sh` assume `AUTH_MODE=local`
- `infra/docker-compose.dev.yml` injeta `AUTH_MODE=mock`

Qualquer mudança em login, sessão ou troubleshooting deve considerar essa diferença.

### 3.4. O catálogo não é mais a única fonte de verdade de metadados

Cada automação publicada expõe `AUTOMATION_META`, e o BFF usa isso para:

- montar `GET /api/automations`,
- sincronizar `version`, `title`, `readOnly` e `superuserOnly` ao servir `GET /catalog/dev`,
- validar consistência do catálogo no startup.

### 3.5. “Chamados de suporte” ficam ancorados em “Quem está online”

O fluxo administrativo atual é:

- o bloco `whoisonline` continua **superuserOnly**;
- a UI dessa automação expõe um botão para o painel de chamados;
- o painel administrativo de suporte é servido por `support/admin.html`.

### 3.6. O módulo support concentra três experiências

`apps/bff/app/automations/support.py` hoje cobre:

- abertura de chamado padrão,
- abertura de chamado técnico,
- leitura administrativa.

Tudo é persistido em `submissions` com `kind="support"`. A diferenciação principal fica em `payload.ticket_type`.

## 4) Arquivos-chave antes de evoluções maiores

### Operação / bootstrap

- `README.md`
- `.env.example`
- `infra/scripts/dev.sh`
- `infra/docker-compose.dev.yml`
- `infra/docker-compose.pg.yml`

### Backend / catálogo

- `apps/bff/app/main.py`
- `apps/bff/app/db.py`
- `apps/bff/app/auth/routes.py`
- `apps/bff/app/auth/rbac.py`
- `catalog/catalog.dev.json`

### Frontend Host

- `apps/host/src/App.tsx`
- `apps/host/src/types.ts`
- `apps/host/src/lib/catalog.ts`
- `apps/host/vite.config.ts`

### Módulos mais sensíveis

- `apps/bff/app/automations/support.py`
- `apps/bff/app/automations/whoisonline.py`
- `apps/bff/app/automations/tasks.py`
- `apps/bff/app/automations/controle.py`
- `apps/bff/app/automations/fileshare.py`

## 5) Mudanças que pedem validação explícita

### Segurança / sessão

- `SessionMiddleware` em `apps/bff/app/main.py`
- regras de cookie / `same_site` / `https_only`
- qualquer tentativa de introduzir CSRF sem revisar o modelo de iframe e sessão

### Navegação / proxy

- `baseUrl` do Docusaurus em `apps/docs-site/docusaurus.config.ts`
- proxy `/devdocs` em `apps/host/vite.config.ts`

### Catálogo / metadados

- contratos de `AUTOMATION_META`
- validação de consistência do catálogo no startup do BFF

### Auth

- a coexistência entre `AUTH_MODE=local` e `AUTH_MODE=mock`
- rotas legadas de login mock

## 6) Passivos conhecidos que exigem janela própria

Não há uma mudança de lógica “obrigatória” neste momento, mas existem passivos que devem ser tratados só com validação dedicada:

- o Host ainda renderiza `iframe` sem `sandbox`;
- `SessionMiddleware` continua com `https_only=False` no estado atual;
- não há proteção explícita de CSRF documentada/implementada para o modelo com cookie;
- o repositório não possui suíte `pytest`, `Vitest` ou CI versionada;
- `apps/docs-site` convive com `package-lock.json` e `pnpm-lock.yaml`.

## 7) Smoke mínimo antes de fechar qualquer entrega

Executar pelo menos:

1. `./infra/scripts/dev.sh up`
2. abrir Host, BFF e `/devdocs/`
3. autenticar e validar `GET /api/me`
4. validar `GET /catalog/dev`
5. abrir uma automação de negócio (ex.: `dfd` ou `ferias`)
6. abrir `support/padrao.html` e enviar um chamado de teste
7. abrir `whoisonline` com superuser e navegar para o painel de suporte
8. baixar JSON/PDF de um chamado de teste

O roteiro completo está em:

- `apps/docs-site/docs/15-apêndices/06-checklist-de-validação-para-mudanças-futuras.md`

## 8) Diretriz final para evoluções

Se houver pouco tempo para uma mudança, preserve esta ordem:

1. manter o ambiente de dev reproduzível;
2. manter README + docs alinhados ao comportamento real;
3. só então mexer em lógica de auth, sessão, catálogo ou segurança.

O risco maior neste repositório não é “falta de feature”, e sim partir de uma premissa antiga e quebrar um fluxo que já funciona no estado atual.
