---
id: rotas-gerais-api-e-api-automations-kind
title: "Rotas gerais /api e /api/automations/{kind}"
sidebar_position: 3
---

## Rotas gerais observadas

- `GET /health`
- `GET /version`
- `GET /api/me`
- `GET /catalog/dev`
- `GET /api/eprotocolo/ping`
- `GET /api/automations`

## Rotas de auth
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/change-password`
- `POST /api/auth/logout`
- `GET /api/auth/sessions`
- `POST /api/auth/sessions/{session_id}/revoke`

## Contrato recorrente das automações

Boa parte dos módulos segue uma combinação de:
- `GET /ui`
- `GET /schema`
- `POST /submit`
- `GET /submissions`
- `GET /submissions/{id}`
- `POST /submissions/{id}/download`

## Importante

O contrato não é 100% uniforme entre todos os módulos:
- alguns têm endpoints extras (`/config`, `/overview`, `/history`, `/active`);
- alguns são administrativos;
- alguns são somente leitura;
- `whoisonline` exige superuser;
- `support` e `fileshare` têm fluxos próprios de documento/download.

Por isso esta documentação agora diferencia:
- padrão recorrente;
- inventário real de cada módulo.


## Fluxo real atual do módulo `support`

No estado atual do repositório, `support` deixou de ser apenas um formulário único
e passou a expor **três visões** diferentes, todas sob o mesmo módulo FastAPI:

- `GET /api/automations/support/padrao.html` — formulário simples que o catálogo abre por padrão;
- `GET /api/automations/support/ui` e `GET /api/automations/support/ui.html` — formulário técnico, com mais contexto;
- `GET /api/automations/support/admin/ui` — painel administrativo de leitura, filtros e detalhe.

Além do `POST /submit`, o módulo também expõe:

- `GET /api/automations/support/submissions`
- `GET /api/automations/support/submissions/{id}`
- `POST /api/automations/support/submissions/{id}/download`
- `POST /api/automations/support/submissions/{id}/document?fmt=pdf`
- `GET /api/automations/support/admin/submissions`
- `GET /api/automations/support/admin/submissions/{id}`

### Observação importante de RBAC

- O bloco de catálogo `support` continua levando o usuário para a UI padrão.
- O painel administrativo de chamados **não** entra pelo catálogo; ele é acessado
  a partir do contexto de `whoisonline`.
- `whoisonline` continua sendo **superuser only** no BFF.
- Já o backend de `support/admin/*` usa RBAC próprio (`admin`, `controle`, `auditor`).

Na prática, isso cria duas camadas de proteção:

1. o **atalho visual** nasce em uma tela já restrita;
2. a **API administrativa** do módulo `support` faz sua própria autorização.

