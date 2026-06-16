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
