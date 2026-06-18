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

O comportamento implementado hoje em `apps/bff/app/notifications.py` é:

1. tenta normalizar e usar `email`;
2. se `email` estiver ausente ou inválido, tenta `email_institucional`;
3. se ambos estiverem ausentes/inválidos, o envio é descartado e fica só a notificação inbox.

Em resumo: **`email` é preferencial e `email_institucional` é fallback**.

### Observação importante de domínio

Esse comportamento funciona com o contrato técnico atual, mas há uma **pendência de modelagem**
registrada na página seguinte:

- `users.email` hoje já é o campo canônico para login e sessão;
- no negócio desejado, ele também deve ser tratado como **e-mail institucional**;
- `users.email_institucional` tende a ser reinterpretado futuramente como **e-mail secundário**.

Por isso, qualquer revisão desta lógica precisa ser feita em conjunto com:

- auth/login;
- perfil e cadastro de usuários;
- autocomplete do ETP;
- documentação e contratos de API/UI.

Veja a página: `./11-modelagem-de-e-mails-de-usuario-pendencia`.

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
- `WARNING` quando o envio for descartado por ausência ou invalidez dos endereços disponíveis
- `ERROR` quando o Expresso falhar
- `INFO` com resumo final de enviados/falhas por notificação

## Teste manual sugerido

1. Preencher `EXPRESSO_MAIL_ENABLED=true` e credenciais válidas.
2. Garantir que os destinatários tenham ao menos um endereço válido entre `email` e `email_institucional`.
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

- Neste snapshot, `.env.example` já traz `EXPRESSO_API_USER` e
  `EXPRESSO_API_PASSWORD` vazios.
- O comportamento desejado continua sendo preencher credenciais reais apenas via
  ambiente/secret manager.
