---
id: mapeamento-de-etapas-para-blocos-automations
title: "Mapeamento de etapas para blocos/automations"
sidebar_position: 2
---

Esta página mostra **como o fluxo de compras público** é mapeado para:

- **categorias/blocos** do catálogo (`catalog/catalog.dev.json`); e
- **módulos de automação** no BFF (`apps/bff/app/automations/*.py`).

A ideia é servir como **“tabela de verdade”** entre visão de produto e implementação técnica, indicando o que já existe, o que é demo/protótipo e o que ainda é backlog.

> Referências no repositório:
> `catalog/catalog.dev.json`
> `apps/bff/app/main.py`
> `apps/bff/app/automations/dfd.py`
> `apps/bff/app/automations/etp.py`
> `apps/bff/app/automations/form2json.py`
> `apps/bff/app/automations/controle.py`

---

## 1) Conceitos rápidos: etapa, bloco e automação

- **Etapa do fluxo**
  Uma fase de negócio do processo de compras público
  (ex.: DFD, PCA, ETP, TR, Cotação, Contrato, Execução).

- **Bloco no catálogo** (`catalog/catalog.dev.json`)
  Um item da lista `blocks[]`, com:
  - `name`, `displayName`, `categoryId`,
  - `ui`,
  - `navigation[]`,
  - `routes[]`,
  - `requiredRoles`, `tags`, `order`, `hidden` etc.

- **Automação no BFF**
  Um módulo FastAPI em `apps/bff/app/automations/{slug}.py`.

Cada automação tende a:
- validar entrada com Pydantic;
- criar registros em `submissions`;
- registrar trilha operacional em `automation_audits`;
- gerar artefatos/saídas e expor downloads quando fizer sentido.

---

## 2) Quadro-resumo: etapas x blocos x automations

| Etapa do fluxo | Bloco no catálogo (`name`) | Categoria (`categoryId / label`) | Automação BFF | Status no produto |
| --- | --- | --- | --- | --- |
| **DFD — Documento de Formalização da Demanda** | `dfd` | `compras / Compras` | `apps/bff/app/automations/dfd.py` | ✅ Implementado |
| **PCA — Plano Anual de Contratações** | `pca` | `compras / Compras` | — | 🧪 Demo em `/api/demo?view=pca` |
| **ETP — Estudos Técnicos Preliminares** | `etp` | `compras / Compras` | `apps/bff/app/automations/etp.py` | ✅ Implementado |
| **TR — Termo de Referência / Projeto Básico** | — | `compras / Compras` | — | 📝 Backlog |
| **Cotação / Dispensa / Licitação** | — | `compras / Compras` | — | 📝 Backlog |
| **Contrato / instrumento equivalente** | — | `compras / Compras` | — | 📝 Backlog |
| **Execução / Empenho / Pagamento** | — | a definir | — | ⚪ Fora do escopo atual |
| **Apoio ao fluxo** | `form2json`, `fileshare`, `controle`, `support` | `compras`, `produtividade`, `governanca`, `suporte` | `form2json.py`, `fileshare.py`, `controle.py`, `support.py` | 🔧 Transversal |

---

## 3) Leitura prática do mapeamento

### O que já é real

- `dfd` e `etp` existem no catálogo e no BFF.
- ambos têm rota de UI em iframe e endpoints próprios.
- ambos participam do domínio operacional de automações.

### O que é demo

- `pca` já aparece para o usuário, mas hoje ainda aponta para `/api/demo?view=pca`.

### O que ainda é produto/backlog

- `tr`
- cotação/dispensa/licitação
- contrato
- execução/empenho/pagamento
- cruzador de orçamento

---

## 4) Implicação para novas automações

Novas etapas do fluxo de compras devem seguir o contrato hoje consolidado no portal:

- entrar via bloco em `catalog/catalog.dev.json`;
- expor UI no BFF;
- persistir submissões e trilha operacional;
- respeitar RBAC e categoria **`compras`** quando forem parte do fluxo principal.

## 5) Observação importante

Quando a documentação tratar de auditoria nesse contexto, o par mais importante é:

- `submissions`
- `automation_audits`

`audit_events` continua existindo e é relevante para auth e eventos gerais de plataforma,
mas não substitui a trilha operacional específica das automações.
