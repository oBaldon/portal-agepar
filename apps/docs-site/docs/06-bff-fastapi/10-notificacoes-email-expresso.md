---
id: "notificacoes-email-expresso"
title: "Notificações com e-mail via Expresso"
sidebar_position: 10
---

# Notificações com e-mail via Expresso

## Objetivo

Sempre que o BFF criar uma notificação inbox em `app.notifications.send_notification(...)`,
o sistema também pode disparar um e-mail transacional para os mesmos destinatários.

A notificação no portal continua sendo o canal principal. O e-mail é complementar e
**não pode bloquear** a criação da notificação.

## Arquitetura

- Núcleo de domínio: `apps/bff/app/notifications.py`
- Integração externa: `apps/bff/app/integrations/expresso_mail.py`

O módulo `expresso_mail.py` encapsula:
- login na API do Expresso (`/Login`);
- cache curto do token `auth`;
- envio por `POST /Mail/Send`.

## Regra de seleção de e-mail do destinatário

Regra específica do Portal AGEPAR:

1. `email_institucional` é obrigatório como pré-condição.
2. Se `email_institucional` vier em branco, o sistema **relata e não envia nada**.
3. Havendo `email` válido, ele é usado como prioridade.
4. Se `email` vier ausente ou inválido, usa `email_institucional` como fallback.

Em resumo: o portal só envia e-mail quando o usuário possui `email_institucional`
preenchido; porém, quando ambos existem, o endereço preferencial é `email`.

## Variáveis de ambiente

No serviço `bff`:

```yaml
EXPRESSO_MAIL_ENABLED: "false"
EXPRESSO_API_BASE: "https://api.expresso.pr.gov.br/celepar"
EXPRESSO_API_USER: ""
EXPRESSO_API_PASSWORD: ""
EXPRESSO_MAIL_TIMEOUT_SECONDS: "10"
EXPRESSO_MAIL_AUTH_CACHE_SECONDS: "600"
PORTAL_PUBLIC_BASE_URL: "http://localhost:5173"
```

## Comportamento operacional

- `send_notification(...)` grava a notificação e os recipients no banco.
- Em seguida, resolve os endereços dos destinatários.
- Os e-mails são disparados em thread daemon, fora do caminho crítico da request.
- Falhas do Expresso são registradas em log e **não revertem** a notificação.

## Logs esperados

- `INFO` quando houver fallback para `email_institucional`
- `WARNING` quando o envio for descartado por ausência de `email_institucional`
- `ERROR` quando o Expresso falhar
- `INFO` com resumo final de enviados/falhas por notificação

## Teste manual sugerido

1. Preencher `EXPRESSO_MAIL_ENABLED=true` e credenciais válidas.
2. Garantir que os destinatários da role tenham `email_institucional` preenchido.
3. Criar uma DFD/ETP/Férias que já dispare notificação.
4. Conferir:
   - inbox do portal;
   - chegada do e-mail;
   - logs do container `bff`.


## Arquivos mapeados

- `apps/bff/app/notifications.py`
- `apps/bff/app/integrations/expresso_mail.py`
- `infra/docker-compose.dev.yml`
- `.env.example`

## Observações

- No estado atual do repositório, `.env.example` ainda carrega variáveis sensíveis
  relacionadas ao Expresso; trate isso como passivo operacional e não como prática desejada.
