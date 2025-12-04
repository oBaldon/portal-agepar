---
id: index
title: "Segurança"
sidebar_position: 0
---

Esta seção concentra a visão de **segurança aplicada** do Portal AGEPAR:  
desde **CORS restrito** e **cookies de sessão**, passando por **RBAC no Host**, até **validações Pydantic** e o mapeamento das **superfícies públicas** (`/api`, `/catalog`, `/devdocs`).

## Objetivos
- Descrever como o **CORS restrito** é configurado no BFF (via `CORS_ORIGINS`) e por que nunca usamos `"*"` em produção.
- Explicar o modelo de **sessão** baseado em **cookie HTTP**, tabela `auth_sessions` e snapshot de usuário em `request.session["user"]`.
- Reforçar a regra de **“sem segredos no repo”** (somente placeholders/valores de dev; segredos reais sempre em variáveis de ambiente/secret manager).
- Documentar o **RBAC de vitrine** no Host (modelo **ANY-of**, `requiredRoles`, `superuserOnly`, `is_superuser`).
- Mostrar como **validações e saneamento com Pydantic v2** ajudam a evitar entradas malformadas (e reduzir 422 “bobos”).
- Mapear as **superfícies públicas** (`/api`, `/catalog/dev`, `/devdocs`, Host) e resumir as estratégias de mitigação recomendadas.

## Sumário Rápido
- `01-cors-restrito` — como o CORS é configurado no BFF, exemplos de envs e cURLs de teste.
- `02-cookies-de-sessão` — modelo de sessão: cookie `portal_agepar_session` + `auth_sessions` + snapshot de usuário.
- `03-sem-segredos-no-repo` — o que é considerado segredo, onde eles vivem (e onde **não** devem viver).
- `04-rbac-no-host-any-of` — regra de visibilidade no frontend (ANY-of) e interação com `roles`, `requiredRoles` e `is_superuser`.
- `05-validações-e-saneamento-pydantic` — padrões de `ConfigDict`, saneamento de dados e exemplos de modelos em automations.
- `06-superfícies-públicas-api-catalog-docs-e-mitigação` — mapa das frentes HTTP do portal e recomendações de endurecimento.

## Camadas de segurança

A segurança do Portal AGEPAR é construída em camadas:

- **BFF (FastAPI)**
  - CORS restrito (`CORS_ORIGINS`),
  - sessões persistidas em banco (tabela `auth_sessions`),
  - validação/saneamento de payloads com Pydantic v2,
  - regras de acesso em endpoints críticos (ex.: automations, downloads).

- **Host (React/Vite/TS)**
  - RBAC de vitrine com base em `user.roles`, `requiredRoles` e `superuserOnly`,
  - consumo do catálogo apenas após autenticação (`/api/me`),
  - isolamento das automations em **iframes**.

- **Infraestrutura**
  - segredos injetados por variáveis de ambiente,
  - exposição controlada de `/api`, `/catalog` e `/devdocs`,
  - uso de reverse proxy para terminação TLS, rate limiting, logs centralizados.

## Tópicos principais da seção

### CORS restrito

- O BFF aplica um **CORS restrito a origens confiáveis**:
  - origens vêm de `CORS_ORIGINS` (variável de ambiente),
  - `allow_credentials=True` (para suportar cookies de sessão),
  - métodos/headers liberados, mas **origens nunca são `"*"`**.
- A documentação mostra exemplos de:
  - configuração em `apps/bff/app/main.py`,
  - uso de `infra/docker-compose.dev.yml` para dev,
  - cURLs simulando origens legítimas vs. maliciosas.

### Cookies de sessão e sessões persistidas

- Autenticação baseada em três peças:
  1. **Cookie HTTP** `portal_agepar_session` (Starlette `SessionMiddleware`).
  2. **Sessão em banco** (`auth_sessions` no Postgres, gerida pelo `DbSessionMiddleware`).
  3. **Snapshot de usuário** em `request.session["user"]`, consumido pelo BFF/Host.
- Benefícios:
  - revogação centralizada de sessões,
  - expiração deslizante (sliding TTL),
  - auditoria mais rica (quem, de onde, quando).

### Sem segredos no repositório

- Regra de ouro: **nenhum segredo real no repo**.
- Só entram:
  - placeholders e valores de dev (ex.: `dev-secret`, `portaldev`),
  - exemplos de `DATABASE_URL` para laboratório.
- Segredos reais (senha de banco, `SESSION_SECRET`, chaves de OIDC, tokens de registry, etc.) ficam em:
  - variáveis de ambiente,
  - mecanismos de segredos da infraestrutura (vault, secret manager, etc.).

### RBAC no Host (ANY-of)

- O Host aplica um RBAC **de vitrine** sobre o catálogo:
  - usa `user.roles` vindo de `/api/me`,
  - compara com `block.requiredRoles`, `block.superuserOnly` e `category.requiredRoles`.
- Regra:
  - **ANY-of**: basta o usuário ter **uma** das roles exigidas.
  - `is_superuser` pode **bypassar** certas restrições.
- O BFF ainda pode reforçar regras em endpoints sensíveis (ex.: `/ui`, `/submit`, downloads).

### Validações e saneamento (Pydantic v2)

- Modelos Pydantic são configurados com:
  - `ConfigDict(populate_by_name=True, extra="ignore")`:
    - aceitam `snake_case` e `camelCase`,
    - ignoram campos extras em vez de responder 422.
- Saneamento:
  - normalização de strings (trim, upper/lower quando faz sentido),
  - tipos específicos (`EmailStr`, `conint`, enums) para reduzir erros de entrada.
- Objetivo:
  - **centralizar** validação/saneamento nos modelos,
  - reduzir `if/else` espalhado em endpoints,
  - evitar 422 “triviais” que pioram a experiência do usuário.

### Superfícies públicas e mitigação

- Superfícies mapeadas:
  - `/api` (BFF, incluindo `/health`, `/version`, `/catalog/dev`),
  - `/` (Host, SPA),
  - `/devdocs` (docs de dev, via proxy do Host).
- Recomendações:
  - restringir `/devdocs` a redes internas ou auth extra em produção,
  - expor `/api` e `/catalog` sempre atrás de reverse proxy com TLS,
  - monitorar access logs e aplicar rate limiting onde fizer sentido.

## Troubleshooting

- **CORS falhando (erros no browser, mas curl funciona)**
  - Verificar se a origem do frontend está em `CORS_ORIGINS` e se `allow_credentials=True` está configurado.
- **Login funciona via curl, mas o navegador “perde” a sessão**
  - Checar domínio, `SameSite`, HTTPS e flags do cookie `portal_agepar_session`.
- **Alguém quer adicionar segredo “temporário” no repo**
  - Reforçar a regra de “sem segredos no repo” e usar variáveis de ambiente/secret manager.
- **Blocos/categorias não aparecem mesmo com usuário autenticado**
  - Conferir `user.roles`, `requiredRoles`, `superuserOnly` e se `is_superuser` está sendo usado corretamente.
- **422 frequentes em automations**
  - Revisar modelos Pydantic, uso de `populate_by_name` e `extra="ignore"`, e garantir que o frontend envia campos esperados.
- **Superfícies de dev (ex.: `/devdocs`) expostas em ambiente produtivo**
  - Ajustar a configuração do reverse proxy para restringir o acesso ou despublicar rota em produção.

---

> _Criado em 2025-12-04_
