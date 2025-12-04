---
id: index
title: "Observabilidade"
sidebar_position: 0
---

Esta seção documenta como o Portal AGEPAR se **observa em produção**:  
desde os **padrões de log** (trilha feliz vs erros), passando pelo **contexto em exceptions/audits**, até os **healthchecks HTTP** usados por containers e integrações.

## Objetivos
- Descrever os **padrões de log** no BFF:
  - trilha feliz em `INFO`,
  - erros em `ERROR` (com contexto suficiente: usuário, submission, automação),
  - pontos-chave como startup, autenticação, automations e downloads.
- Explicar como o **contexto** é carregado em:
  - exceptions (`logger.exception(...)`),
  - respostas HTTP de erro,
  - registros em `automation_audits` no banco.
- Documentar os **healthchecks e checks de container**:
  - `/health` (liveness do BFF),
  - `/version` (versão/configuração em runtime),
  - checks de Postgres no Docker Compose,
  - ping lógico do eProtocolo (`/api/eprotocolo/ping`), quando disponível.

## Sumário Rápido
- `01-padrões-de-log-trilha-feliz-vs-erros` — filosofia de logging, o que vai em `INFO` vs `ERROR`, e pontos obrigatórios de log.
- `02-contexto-em-exceptions-audits` — como exceções, erros HTTP e auditoria em banco compartilham o mesmo contexto (IDs, usuário, sessão).
- `03-métricas-healthchecks-se-houver` — visão atual de healthchecks HTTP, checks de container e próximos passos para métricas.

## Visão geral da observabilidade

Hoje a observabilidade do Portal AGEPAR é focada em:

- **Logs de aplicação (BFF)**:
  - estruturados o suficiente para suporte/ops,
  - com mensagens estáveis para filtros em agregadores (quando existirem).
- **Auditoria em banco**:
  - tabela `automation_audits` guarda o “livro caixa” de eventos de automations.
- **Healthchecks HTTP**:
  - verificam disponibilidade básica do BFF e conectividade com dependências.

Ainda **não** há métricas formais (ex.: Prometheus), mas a base de logs + auditoria + healthchecks já permite:

- diagnosticar erros de automations,
- identificar picos de falha de integração,
- monitorar se o BFF está de pé e falando com o banco.

## Padrões de log (trilha feliz vs erros)

- **Trilha feliz (`INFO`)**:
  - startup do BFF (ENV, `AUTH_MODE`, CORS, banco),
  - login/logout e criação de sessões,
  - criação e conclusão de submissions de automations,
  - eventos relevantes de arquivos (upload/download) e eProtocolo.
- **Erros (`ERROR`/`EXCEPTION`)**:
  - exceções não tratadas ou inesperadas,
  - falhas em integrações externas (eProtocolo, banco),
  - problemas de IO (arquivos/paths).
- Convenções:
  - sempre incluir **contexto mínimo**: `kind` da automação, `submission_id`, `user_id`/CPF, caminho do arquivo ou endpoint alvo;
  - mensagens claras e estáveis para poder filtrar nos logs no futuro.

## Contexto em exceptions/audits

Para cada operação importante, o sistema busca deixar **três rastros coerentes**:

1. **Log/exception** para dev/ops  
   - `logger.exception("erro ao gerar documento", extra={...})`  
   - sempre com IDs chave (`sid`, `user_id`, `session_id`, `kind`).

2. **Erro HTTP estruturado** para o cliente  
   - estruturas como `err_json(code, message, details, hint)` em automations:
     - facilitam o trabalho do frontend,
     - permitem exibir mensagens amigáveis para o usuário final.

3. **Evento de auditoria** em banco  
   - registro na tabela `automation_audits`:
     - `kind`,
     - `at` (timestamp),
     - alvo (`sid`, `user_id`, `session_id`),
     - `meta` com dados adicionais (ex.: parâmetros de chamada, resultado resumido).

Essa convergência garante que, ao investigar um problema, você consiga:

- achar o log de erro,
- ver o que o cliente recebeu,
- entender o contexto de negócio no banco.

## Métricas e healthchecks

Mesmo sem um stack de métricas completo, o Portal AGEPAR já expõe:

- `GET /health`
  - responde se o processo FastAPI está vivo;
  - usado em checks de container e load balancer.
- `GET /version`
  - retorna versão/build e alguns detalhes de configuração;
  - útil para confirmar deploy correto.
- Checks de Postgres no Docker Compose
  - `infra/docker-compose.pg.yml` define healthchecks do banco;
  - o BFF depende desses checks para subidas mais previsíveis.
- `GET /api/eprotocolo/ping` (quando configurado)
  - testa a conectividade lógica com o eProtocolo;
  - ajuda a separar “BFF fora do ar” de “integração externa fora do ar”.

A seção de métricas/healthchecks também aponta caminhos futuros:

- exposição de métricas de contagem de submissions por status,
- latência média de automations,
- dashboards simples em ferramentas padrão de observabilidade.

## Troubleshooting

- **Não sei o que logar em um endpoint novo**
  - Logue em `INFO`:
    - entrada/sucesso com IDs chave (user, submission, kind).
  - Logue em `ERROR`:
    - falhas inesperadas, sempre com `logger.exception(...)`.
- **Erros em produção sem contexto suficiente**
  - Revisar a página de “Contexto em exceptions/audits” e garantir que os logs incluam:
    - `sid`, `user_id`, `session_id`, `kind` e, se possível, identificadores de artefato.
- **Healthcheck `/health` responde 200, mas o serviço está “quebrado”**
  - Complementar monitoria usando:
    - `/version`,
    - pings de automations simples (ex.: automação de teste),
    - ping de integrações (`/api/eprotocolo/ping`).
- **Dificuldade para correlacionar logs com auditoria**
  - Garanta que o `submission_id` utilizado em `automation_audits` também apareça nos logs do módulo.
- **Quero adicionar métricas (Prometheus, etc.)**
  - Use os healthchecks atuais como ponto de partida e siga o padrão de IDs/contexto já descrito nesta seção.

---

> _Criado em 2025-12-04_
