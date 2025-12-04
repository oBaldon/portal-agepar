---
id: index
title: "BFF (FastAPI)"
sidebar_position: 0
---

O BFF (FastAPI) é o **backend de fronteira** do Portal AGEPAR: concentra autenticação, sessões, catálogo, automations e integração com o banco de dados.  
Ele expõe as rotas em `/api` e `/api/automations/{kind}/...`, aplica validações (Pydantic v2), faz o mapeamento de erros e registra logs de forma padronizada.

## Objetivos
- Descrever a **estrutura do app** em `apps/bff/app/` (pontos de entrada, módulos de auth, automations, db, utils).
- Documentar o fluxo de **sessões mock**: `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/me` e como isso alimenta o Host.
- Explicar as **rotas gerais** em `/api` e o contrato base de `/api/automations/{kind}/...` (schema, ui, submit, submissions, download).
- Consolidar os **padrões de validação** com **Pydantic v2** (`ConfigDict(populate_by_name=True, extra="ignore")`) e estratégias para evitar `422` triviais.
- Descrever o **mapeamento de erros** (`400–422`) com respostas JSON legíveis e padronizadas entre automations.
- Definir o padrão de **logging** (níveis, contexto mínimo) para o caminho feliz (INFO) e fluxos de erro (ERROR).

## Sumário Rápido
- `01-estrutura-do-app-apps-bff-app` — árvore de diretórios, módulos principais e ponto de entrada em `main.py`.
- `02-sessões-mock-post-api-auth-login-get-api-me` — fluxo de login, cookie de sessão e endpoint `/api/me`.
- `03-rotas-gerais-api-e-api-automations-kind` — mapa de rotas gerais e contrato mínimo de automations.
- `04-pydantic-v2-configdict-populate_by_name-extraignore` — configurações padrão de modelos e motivos para usá-las.
- `05-normalização-validação-evitar-422` — técnicas para normalizar input e reduzir erros de validação no cliente.
- `06-mapeamento-de-erros-400422` — como estruturar erros legíveis e consistentes entre módulos.
- `07-logging-info-error` — convenções de logs e exemplos práticos em endpoints e automations.

## Visão geral do BFF

O BFF vive em `apps/bff/app/` e é responsável por:

- inicializar a aplicação FastAPI (`main.py`);
- configurar middlewares (sessão em banco, CORS, cookies);
- expor rotas de:
  - autenticação e sessões (`/api/auth/*`, `/api/me`);
  - catálogo (`/catalog/dev`);
  - automations (`/api/automations/{kind}/...`);
  - utilidades (ex.: whoisonline, fileshare);
- inicializar o banco (`init_db`) com tabelas de **submissions** e **auditoria** das automations.

## Padrões transversais

Alguns padrões se repetem em praticamente todo o código do BFF:

- **Pydantic v2 com `ConfigDict`**
  - `populate_by_name=True` para aceitar tanto `snake_case` quanto `camelCase`.
  - `extra="ignore"` para tolerar campos adicionais sem quebrar o request.
- **Normalização e validação**
  - pré-processamento de campos (trim, normalização de CPF/CNPJ, datas) antes de validar;
  - modelos de entrada/saída explícitos, evitando `dict` solto em endpoints.
- **Erros padronizados**
  - uso de estruturas JSON com `code`, `message`, `details`, `hint` quando possível;
  - mapeamento consistente de `400`, `401`, `403`, `404`, `409`, `422`.
- **Logging**
  - `INFO` para eventos do caminho feliz (startup, login ok, submission criada/concluída);
  - `ERROR` com contexto suficiente (id da submission, usuário, kind da automação) para suporte e auditoria.

## Fluxo típico de requisição

1. **Usuário faz login** via Host → `POST /api/auth/login`.
2. O BFF cria/valida a **sessão** e grava no banco; o cookie é retornado ao navegador.
3. O Host chama `GET /api/me` para obter dados do usuário (incluindo `roles` para RBAC).
4. Usuário acessa um bloco → Host abre um **iframe** para `/api/automations/{kind}/ui`.
5. A UI da automação faz `POST /submit` com o payload validado por Pydantic.
6. O BFF cria uma **submission**, registra **auditoria**, executa o processamento (direto ou via `BackgroundTasks`) e devolve o resultado ou um id para consulta.

## Troubleshooting

- **`/api` ou `/api/docs` fora do ar**
  - Verifique logs de inicialização do BFF e se o container/serviço está escutando na porta esperada.
- **Login aparenta funcionar, mas `/api/me` retorna 401**
  - Checar configuração de cookies (domínio, `SameSite`, HTTPS) e se a sessão está sendo persistida corretamente.
- **Muitos erros 422 (Unprocessable Entity)**
  - Revisar modelos Pydantic e normalizações descritas nas páginas de validação; conferir se o frontend está enviando os campos esperados.
- **Automations retornando 500 genérico**
  - Confirmar se exceções estão sendo tratadas com mapeamento adequado para `4xx/422` quando for erro de entrada, e `5xx` apenas para falhas internas.
- **Logs insuficientes para debug**
  - Ajustar pontos de `logger.info`/`logger.error` conforme o padrão da página de logging, incluindo sempre o `kind` da automação e o `submission_id` quando existir.

---

> _Criado em 2025-12-04_
