---
id: automação-paralela-cruzador-de-orçamento
title: "Automação paralela: cruzador de orçamento"
sidebar_position: 3
---

Esta página descreve a **ideia de produto** da automação paralela **“cruzador de
orçamento”**: um módulo que cruza informações de demandas com limites
orçamentários/planejamento para apontar riscos de **estouro de orçamento**,
**duplicidade** e **inconsistências**.

> Referências no repositório (estado atual):
> `catalog/catalog.dev.json`
> `apps/bff/app/automations/dfd.py`
> `apps/bff/app/automations/etp.py`
> `apps/bff/app/automations/controle.py`
> `apps/bff/app/automations/fileshare.py`
> `apps/bff/app/db.py`

> Importante: neste snapshot, **não existe ainda** uma automação implementada
> para o cruzador de orçamento.
> Esta página documenta o **desenho de produto** e como essa automação deve se
> encaixar na arquitetura existente.

---

## 1) O que é o “cruzador de orçamento” no contexto do Portal

No fluxo de compras público, várias decisões dependem de limites orçamentários:

- quanto cada diretoria pode gastar em determinado tipo de objeto;
- limites por fonte de recurso, natureza de despesa, UG/gestão;
- teto anual de determinadas linhas do PCA.

O Portal AGEPAR já tem:

- **DFD** como porta de entrada das demandas;
- **ETP** como etapa técnica subsequente já automatizada;
- trilha operacional em `submissions` + `automation_audits`;
- automações de apoio como `controle` e `fileshare`.

O **cruzador de orçamento** é pensado como uma **automação paralela** que:

- **não substitui** DFD, PCA, ETP, TR etc.;
- cruza demandas já cadastradas com limites orçamentários;
- devolve um relatório consolidado com sobras, estouros e conflitos de prioridade.

---

## 2) Cenários de uso

1. **Antes de fechar o PCA do ano**
   Cruzar demandas e limites para identificar excesso por diretoria ou natureza de despesa.

2. **Ao priorizar demandas dentro de uma diretoria**
   Usar prioridade e valor estimado para entender quais demandas cabem no orçamento.

3. **Monitorar impacto de novas demandas**
   Simular o efeito de um novo DFD ou ETP em relação ao orçamento disponível.

4. **Auditoria e transparência**
   Produzir relatórios que expliquem quais decisões foram tomadas sob restrição orçamentária.

---

## 3) Status atual no repositório

Até este snapshot:

- não há `apps/bff/app/automations/cruzador_orcamento.py`;
- não há bloco dedicado no catálogo;
- não há UI HTML específica para esse tema.

O que já existe para suportar esse futuro módulo é:

- padrão de automations no BFF;
- categoria **`compras`** no catálogo;
- persistência operacional em `submissions`;
- trilha operacional em `automation_audits`;
- painéis administrativos em `controle.py`.

---

## 4) Encaixe sugerido na arquitetura

### Slug e nomes sugeridos

- **slug do módulo**: `cruzador-orcamento`
- **arquivo BFF**: `apps/bff/app/automations/cruzador_orcamento.py`
- **KIND**: `cruzador_orcamento`
- **bloco de catálogo**: categoria `compras`

### Exemplo de bloco proposto

```json
{
  "name": "cruzador-orcamento",
  "displayName": "Cruzador de Orçamento",
  "version": "0.1.0",
  "categoryId": "compras",
  "ui": { "type": "iframe", "url": "/api/automations/cruzador-orcamento/ui" },
  "navigation": [{ "label": "Cruzador de Orçamento", "path": "/cruzador-orcamento", "icon": "Scale" }],
  "routes": [{ "path": "/cruzador-orcamento", "kind": "iframe" }],
  "requiredRoles": ["compras", "admin"]
}
```

---

## 5) Relação com DFD, PCA e ETP

- **DFD** fornece a demanda de negócio;
- **PCA** tende a concentrar a visão anual/planejamento;
- **ETP** fornece maior detalhamento técnico e alternativas;
- o cruzador de orçamento funciona como camada analítica transversal sobre esses dados.

## 6) Observação importante

A categoria correta para compras, no catálogo atual, é **`compras`**.

Exemplos antigos usando `cat1` não refletem mais o estado atual do repositório.
