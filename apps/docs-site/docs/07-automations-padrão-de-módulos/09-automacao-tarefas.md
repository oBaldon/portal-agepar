---
id: "automacao-tarefas"
title: "Automação de tarefas (`tasks`)"
sidebar_position: 10
---

## Objetivo

Módulo operacional para gestão simples de tarefas no Portal AGEPAR.

## Escopo atual (Fase 2A — progresso)

- criação de tarefas
- edição pelo criador
- alteração de status pelo criador ou responsável
- comentários
- histórico de eventos
- exclusão lógica pelo criador
- restauração de tarefa excluída pelo criador
- visualizações em lista, kanban, calendário semanal e calendário mensal
- resumo operacional do módulo
- atividade recente das tarefas visíveis ao usuário
- insights preparatórios para futura visão gerencial
- filtros e modelo preparados para origem (`source_kind` / `source_id`)
- primeiros gatilhos automáticos de notificação via plataforma/e-mail para eventos selecionados de tarefa

## Endpoints principais

- `GET /api/automations/tasks/ui`
- `GET /api/automations/tasks/schema`
- `GET /api/automations/tasks/config`
- `GET /api/automations/tasks/summary`
- `GET /api/automations/tasks/activity`
- `GET /api/automations/tasks/insights`
- `GET /api/automations/tasks/management-overview`
- `GET /api/automations/tasks/tasks`
- `POST /api/automations/tasks/tasks`
- `GET /api/automations/tasks/tasks/{id}`
- `PUT /api/automations/tasks/tasks/{id}`
- `PATCH /api/automations/tasks/tasks/{id}/status`
- `DELETE /api/automations/tasks/tasks/{id}`
- `POST /api/automations/tasks/tasks/{id}/restore`
- `POST /api/automations/tasks/tasks/{id}/comments`
- `GET /api/automations/tasks/tasks/{id}/history`

## Modelo de dados

Tabelas introduzidas:

- `tasks`
- `task_events`
- `task_comments`

## Regras de acesso

- usuários autenticados acessam o módulo
- usuários comuns veem tarefas que criaram ou que lhes foram atribuídas
- admin possui visão ampliada
- somente o criador pode excluir sua tarefa na operação normal
- a restauração de tarefa excluída segue a mesma lógica do criador, com visão ampliada para perfis elevados

## Preparação para a Fase 2

A Fase 1D já deixa prontas estruturas úteis para evolução:

- histórico de eventos padronizados com rótulo/categoria/severidade
- exclusão lógica e restauração
- resumo operacional
- feed de atividade recente enriquecido
- endpoint de insights preparatórios para futura visão consolidada
- campos de origem (`source_kind` / `source_id`) para vínculo com outros módulos

## Gatilhos automáticos já ativos

Neste corte inicial da Fase 2A, o módulo passa a disparar notificações automáticas, de forma não bloqueante, para eventos selecionados:

- `task_created`: notifica responsável e/ou papel atribuído na tarefa
- `task_assigned`: notifica responsável e/ou papel atribuído
- `task_reassigned`: notifica novo responsável e/ou papel atribuído
- `task_completed`: notifica o criador da tarefa quando a conclusão for feita por outra pessoa

As notificações usam o mecanismo central do Portal, portanto podem chegar tanto na plataforma quanto por e-mail, conforme a configuração de notificações já existente.

## Próximas etapas

- métricas mais ricas de execução
- expansão controlada do catálogo de gatilhos
- integração com painel consolidado em Controle/Auditoria

## Visão gerencial preparatória

Perfis elevados (`admin`) passam a ter um primeiro bloco gerencial ainda dentro do próprio módulo de tarefas, com:

- resumo global de abertas / concluídas / atrasadas / em revisão
- distribuição por status
- resumo por responsável
- lista de concluídas recentes com lead time

Essa visão ainda não substitui a futura integração com o Painel de Controle / Auditoria; ela serve como etapa preparatória.


## Fase 2B — Ponte com o Painel de Controle

Foi adicionada a primeira ponte com o Painel de Controle/Auditoria:

- `GET /api/automations/controle/tarefas/ui`
- `GET /api/automations/controle/tarefas/overview`
- `GET /api/automations/controle/tarefas/activity`

Objetivo desta etapa:
- expor uma visão consolidada inicial de tarefas para perfis elevados;
- incluir o botão/aba **Tarefas** ao lado de **Auditoria** e **Férias**;
- reaproveitar a visão gerencial já construída na automação `tasks`, sem duplicar regras de negócio.


## Fase 2B — Refinamento da visão gerencial

A ponte com o Painel de Controle evoluiu para uma visão consolidada refinada, com:

- filtros por período, busca, responsável, status, origem e atraso;
- drill-down de tarefas diretamente dentro do painel;
- histórico da tarefa selecionada;
- atividade recente filtrável;
- distribuição por status e por origem com clique para aplicar filtro.

Novos endpoints de apoio:

- `GET /api/automations/controle/tarefas/config`
- `GET /api/automations/controle/tarefas/tasks`
- `GET /api/automations/controle/tarefas/tasks/{id}/history`

Objetivo desta etapa:
- reduzir o vai-e-volta entre a automação operacional e o Controle;
- permitir leitura gerencial com drill-down sem abrir edição;
- preparar o caminho para métricas ainda mais ricas e integrações futuras.


## Evolução desta etapa

Foi adicionado um refinamento da camada gerencial e dos gatilhos de tarefas, com:

- novas métricas no overview gerencial:
  - criadas no período
  - vencem em 7 dias
  - taxa de conclusão
- novas distribuições:
  - por prioridade
  - por papel atribuído
- série diária de criação x conclusão
- novo evento de histórico:
  - `task_due_date_changed`
- novo gatilho de notificação:
  - `task_in_review` (quando a tarefa entra em revisão)

## Estado da implementação

Esta frente está em estágio avançado, com:
- módulo operacional utilizável
- visão consolidada no Controle
- primeiros gatilhos automáticos ativos
- base pronta para scheduler/regras futuras de vencimento e alertas mais sofisticados


## Arquivos mapeados

- `apps/bff/app/automations/tasks.py`
- `apps/bff/app/automations/controle_tasks.py`
- `apps/bff/app/db.py`
- `catalog/catalog.dev.json`

## Observação sobre a UI

A UI principal da automação é servida pelo próprio BFF em
`GET /api/automations/tasks/ui` e o Host apenas a embute via iframe, seguindo
o padrão geral do portal.
