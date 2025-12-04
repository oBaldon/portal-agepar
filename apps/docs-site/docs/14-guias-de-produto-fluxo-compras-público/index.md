---
id: index
title: "Guias de Produto (Fluxo Compras Público)"
sidebar_position: 0
---

Esta seção amarra a **visão de produto** do Portal AGEPAR para o fluxo completo de
**compras públicas**, conectando:

> DFD → PCA → ETP → TR → Cotação/Dispensa/Licitação → Contrato → Execução/Empenho/Pagamento

com o que já existe hoje no monorepo (ex.: automação **DFD**) e o que ainda está em
**desenho de produto** (PCA, ETP, TR, etapas de contratação, cruzador de orçamento, etc.).

Ela funciona como uma “ponte” entre a visão de negócio e os detalhes técnicos já
documentados nas seções de BFF, automations, catálogo e Host.

## Objetivos
- Descrever o **fluxo de compras público ponta a ponta**:
  - DFD → PCA → ETP → TR → Cotação/Dispensa/Licitação → Contrato → Execução/Empenho/Pagamento.
- Mapear cada **etapa de negócio** para:
  - **blocos/categorias** do catálogo (`catalog/catalog.dev.json`),
  - **módulos de automação** existentes ou planejados (`apps/bff/app/automations/*.py`),
  - estados “MVP”, “protótipo” ou “só desenho”.
- Explicitar o que já está implementado hoje (principalmente o **MVP de DFD**) e
  o que está em **backlog de produto**.
- Documentar a **automação paralela “cruzador de orçamento”** como peça de produto:
  - objetivos,
  - entradas/saídas esperadas,
  - encaixe com DFD/PCA e painel de controle.
- Servir como referência única para alinhar **time de produto**, **time técnico** e
  **usuários chave** sobre o roadmap do fluxo de compras dentro do Portal.

## Sumário Rápido
- `01-dfd---pca---etp---tr---cotação-dispensa-licitação---contrato---execução-empenho-pagamento`  
  visão geral do fluxo completo de compras públicas e do que já existe (MVP DFD) vs. o que está em desenho de produto.
- `02-mapeamento-de-etapas-para-blocos-automations`  
  “tabela de verdade” mapeando etapas de negócio → categorias/blocos do catálogo → automations no BFF.
- `03-automação-paralela-cruzador-de-orçamento`  
  guia de produto para a automação paralela de cruzamento de orçamento (ideia, escopo, encaixe no fluxo).
- `99-referencias.mdx`  
  links para arquivos técnicos relevantes (catálogo, automations, db, timeline).

## Visão geral do fluxo de compras público

O fluxo de compras público considerado pelo Portal AGEPAR é:

> DFD → PCA → ETP → TR → Cotação/Dispensa/Licitação → Contrato → Execução/Empenho/Pagamento

Nesta seção:

- **DFD** é detalhado como **MVP já existente** (automação `dfd.py` + bloco `dfd`);
- **PCA, ETP, TR** e etapas seguintes são tratadas como:
  - protótipos (quando há só bloco de catálogo),
  - ou **ideias de produto** ainda sem automação implementada;
- são apontadas as dependências entre etapas (dados que “viajam” ao longo do fluxo).

## Mapeamento de etapas para blocos/automations

A página de mapeamento (`02-mapeamento-de-etapas-para-blocos-automations`) mostra, etapa por etapa:

- **qual categoria/bloco** representa aquela etapa no catálogo;
- **se existe ou não** um módulo de automação correspondente no BFF;
- qual o **status** de cada peça:
  - ✅ já implementado (ex.: `dfd.py`),
  - 🧪 protótipo/placeholder (apenas bloco no catálogo ou demo),
  - 📝 desenho de produto (somente descrito na doc;
    ainda sem código).

Esse mapeamento é o ponto de partida para decisões de priorização e para abrir
issues/epics no backlog técnico com base em uma linguagem compartilhada.

## Automação paralela: cruzador de orçamento

Além da “linha principal” do fluxo de compras, a seção também descreve uma
**automação paralela**:

> **Cruzador de orçamento** — um módulo que cruza demandas (DFDs) com limites orçamentários/planejamento (PCA, centros de custo, ND, etc.).

Na página `03-automação-paralela-cruzador-de-orçamento` são definidos:

- o **problema de negócio** que a automação resolve (riscos de estouro, duplicidade, inconsistências);
- hipóteses para **entradas/saídas** (parâmetros, filtros, formatos de relatório);
- como ela se encaixa na arquitetura atual:
  - novo bloco no catálogo,
  - automação dedicada no BFF,
  - possíveis integrações com o painel de controle (`controle.py`) e com o DFD.

Importante: o repositório atual **não contém** essa automação implementada; a doc
registra a **visão de produto** para orientar o desenho técnico futuro.

## Como usar esta seção

- **Time de produto**  
  Usa as páginas desta seção para:
  - alinhar fluxos e escopos com áreas de negócio,
  - preparar histórias de usuário/épicos para o backlog.

- **Time técnico**  
  Consulta os guias daqui antes de:
  - criar novas automations ligadas ao fluxo de compras,
  - alterar o catálogo (`catalog.dev.json`) para novas etapas,
  - ajustar o painel de controle para novas visões.

- **Stakeholders e usuários chave**  
  Podem usar esta seção como:
  - mapa de “onde estamos” no fluxo completo,
  - material de apoio para apresentações internas.

## Troubleshooting

- **Dúvida se uma etapa do fluxo já tem automação implementada**
  - Verificar a página **“Mapeamento de etapas para blocos/automations”**  
    e conferir o status (implementado, protótipo, desenho).
- **Produto pede uma etapa nova que não aparece no catálogo**
  - Usar esta seção para localizar a etapa no fluxo
    e depois abrir um item de backlog para:
    - criar bloco no catálogo,
    - eventualmente criar automação correspondente.
- **Dúvida se o cruzador de orçamento “já existe”**
  - Conferir a página do **cruzador de orçamento**:  
    ela documenta apenas o desenho de produto;  
    a automação ainda não existe como código (`cruzador_orcamento.py`).
- **Fluxo de negócio e docs técnicas divergindo**
  - Validar primeiro aqui (seção 14) a visão de produto
    e depois ajustar as seções técnicas (BFF, automations, catálogo) para manter tudo alinhado.

---

> _Criado em 2025-12-04_
