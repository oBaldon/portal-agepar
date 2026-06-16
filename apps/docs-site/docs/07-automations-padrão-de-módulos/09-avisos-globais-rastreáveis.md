---
id: "avisos-globais-rastreaveis"
title: "Avisos globais rastreáveis"
sidebar_position: 9
---

A automação `avisos` permite que um administrador publique um comunicado global
para todos os usuários com sessão ativa no momento do disparo.

## O que ela entrega

- painel administrativo em `/api/automations/avisos/ui`;
- popup global no host, exibido em qualquer rota protegida;
- rastreamento por usuário: pendente, visualizado, confirmado ou objetado;
- objeção com mensagem de retorno ao administrador;
- badge no título da aba (`(1) Portal AGEPAR`) enquanto houver aviso pendente;
- histórico administrativo com destinatários, confirmações e objeções.
- trilha de eventos por aviso e exportação CSV de destinatários, objeções e auditoria.

## Regras do MVP

- apenas **1 aviso ativo por vez**;
- público-alvo = snapshot de usuários presentes em `auth_sessions` na publicação;
- o aviso pode ser:
  - bloqueante; ou
  - dispensável temporariamente (`allow_dismiss=true`);
- o administrador consegue encerrar o aviso antes da expiração;
- as ações são auditadas em:
  - `submissions`,
  - `automation_audits`,
  - `audit_events`.

## Endpoints principais

### Painel administrativo

- `GET /api/automations/avisos/ui`
- `GET /api/automations/avisos/schema`
- `GET /api/automations/avisos`
- `POST /api/automations/avisos`
- `GET /api/automations/avisos/{id}`
- `GET /api/automations/avisos/{id}/recipients`
- `GET /api/automations/avisos/{id}/objections`
- `GET /api/automations/avisos/{id}/events`
- `GET /api/automations/avisos/{id}/download?kind=recipients|objections|events`
- `POST /api/automations/avisos/{id}/close`

### Consumo pelo host / usuário atual

- `GET /api/automations/avisos/mine/pending`
- `POST /api/automations/avisos/{id}/seen`
- `POST /api/automations/avisos/{id}/confirm`
- `POST /api/automations/avisos/{id}/object`

## Persistência

As tabelas utilizadas são:

- `platform_alerts`
- `platform_alert_recipients`

Elas guardam:

- conteúdo e configuração do aviso;
- quem recebeu;
- quem visualizou;
- quem confirmou;
- quem objetou e qual mensagem enviou.

## Host

O host adiciona um `GlobalAlertCenter` acima das rotas. Ele faz polling leve e
também sincroniza múltiplas abas via `localStorage` e `BroadcastChannel` para remover o popup quando
o usuário responde em outra aba. Dismiss temporário é persistido por aba em `sessionStorage`.


## Arquivos mapeados

- `apps/bff/app/automations/avisos.py`
- `apps/bff/app/notifications.py`
- `apps/host/src/components/GlobalAlertCenter.tsx`
- `catalog/catalog.dev.json`
