---
id: inventario-de-automacoes-e-blocos-do-estado-atual
title: "Inventário de automações e blocos do estado atual"
sidebar_position: 11
---

Esta página lista o que está ativo no código e no catálogo do portal neste estado
do repositório.

## Blocos presentes em `catalog/catalog.dev.json`

| Bloco | Categoria | UI | Roles | Observação |
| --- | --- | --- | --- | --- |
| `dfd` | `compras` | `/api/automations/dfd/ui` | `compras` | Geração de DFD |
| `etp` | `compras` | `/api/automations/etp/ui` | `compras` | Geração de ETP |
| `pca` | `compras` | `/api/demo` | `admin` | Ainda representado como placeholder/demo |
| `controle` | `governanca` | `/api/automations/controle/ui` | `admin`, `daf`, `dfq`, `dre`, `dnr`, `dp` | Painel administrativo |
| `accounts` | `governanca` | `/api/automations/accounts/ui` | catálogo sem restrição própria | Gestão de usuários e papéis |
| `usuarios` | `pessoas` | `/api/automations/usuarios/ui` | `rh`, `admin` | Cadastro e histórico de usuários |
| `ferias` | `pessoas` | `/api/automations/ferias/ui` | `ferias` | Solicitações e documentos |
| `tasks` | `produtividade` | `/api/automations/tasks/ui` | catálogo sem restrição própria | Tarefas, comentários e histórico |
| `support` | `suporte` | `/api/automations/support/ui` | catálogo sem restrição própria | Chamados/documentos |
| `fileshare` | `produtividade` | `/api/automations/fileshare/ui` | catálogo sem restrição própria | Compartilhamento temporário |
| `ponto_saldo` | `pessoas` | `/api/automations/ponto_saldo/ui` | `ca`, `rh`, `cof` | Leitura de PDF de espelho |
| `avisos` | `governanca` | `/api/automations/avisos/ui` | `admin` | Avisos globais rastreáveis |
| `whoisonline` | `governanca` | `/api/automations/whoisonline/ui` | catálogo sem restrição própria | Sessões e presença |
| `demo`, `form2json`, `automacao2`, `automacao3`, `possibilidades` | ocultos/lab | variado | variado | Blocos ocultos ou de apoio |

## Módulos Python observados em `apps/bff/app/automations`

- `accounts.py`
- `avisos.py`
- `controle.py`
- `controle_ferias.py`
- `controle_tasks.py`
- `dfd.py`
- `etp.py`
- `ferias.py`
- `fileshare.py`
- `form2json.py`
- `ponto_saldo.py`
- `profile.py`
- `support.py`
- `tasks.py`
- `usuarios.py`
- `whoisonline.py`

## Módulos auxiliares sem bloco direto no catálogo

- `task_weekly_email.py`
- `task_weekly_report.py`

Esses arquivos suportam rotinas de notificação ou agregação operacional, mas não
aparecem como bloco navegável próprio no catálogo.

## Leitura recomendada em conjunto

- `./06-checklist-para-criar-nova-automação`
- `./07-ui-via-iframe-e-integração-com-catálogo`
- `../05-catálogo-catalog-dev/01-estrutura-json-categories-blocks`
