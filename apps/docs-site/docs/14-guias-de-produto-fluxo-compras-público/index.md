---
id: "guias-de-produto-fluxo-compras-publico"
title: "Guias de Produto (Fluxo Compras Público)"
sidebar_position: 0
---

Esta seção amarra a **visão de produto** do Portal AGEPAR para o fluxo completo de
**compras públicas**, conectando:

> DFD → PCA → ETP → TR → Cotação/Dispensa/Licitação → Contrato → Execução/Empenho/Pagamento

com o que já existe hoje no monorepo e o que ainda está em desenho de produto.

Ela funciona como uma “ponte” entre a visão de negócio e os detalhes técnicos já
documentados nas seções de BFF, automations, catálogo e Host.

## Objetivos

- Descrever o **fluxo de compras público ponta a ponta**.
- Mapear cada **etapa de negócio** para:
  - **blocos/categorias** do catálogo (`catalog/catalog.dev.json`);
  - **módulos de automação** existentes ou planejados (`apps/bff/app/automations/*.py`);
  - estados “implementado”, “demo/protótipo” ou “backlog”.
- Explicitar o que já está implementado hoje em compras:
  - **DFD** como automação consolidada;
  - **ETP** como automação real no BFF e no catálogo;
  - **PCA** como bloco de demonstração;
  - demais etapas como backlog de produto.
- Documentar a **automação paralela “cruzador de orçamento”** como peça de produto futuro.
- Servir como referência única para alinhar **time de produto**, **time técnico** e
  **usuários chave** sobre o roadmap do fluxo de compras dentro do Portal.

## Sumário rápido

- `01-dfd---pca---etp---tr---cotação-dispensa-licitação---contrato---execução-empenho-pagamento`  
  visão geral do fluxo completo de compras públicas e do que já existe hoje.
- `02-mapeamento-de-etapas-para-blocos-automations`  
  “tabela de verdade” mapeando etapas de negócio → categorias/blocos do catálogo → automations no BFF.
- `03-automação-paralela-cruzador-de-orçamento`  
  guia de produto para a automação paralela de cruzamento de orçamento.
- `99-referencias.mdx`  
  links para arquivos técnicos relevantes.

## Visão geral do fluxo de compras público

O fluxo de compras público considerado pelo Portal AGEPAR é:

> DFD → PCA → ETP → TR → Cotação/Dispensa/Licitação → Contrato → Execução/Empenho/Pagamento

Nesta seção:

- **DFD** é detalhado como automação já implementada;
- **ETP** é tratado como automação já implementada, com UI, schema, submit e downloads;
- **PCA** aparece hoje como bloco de demonstração no catálogo;
- **TR** e etapas seguintes continuam como backlog de produto;
- são apontadas as dependências entre etapas e os módulos transversais de apoio.

## Como usar esta seção

- **Time de produto**  
  Usa as páginas desta seção para alinhar backlog, fluxos e histórias de usuário.

- **Time técnico**  
  Consulta os guias daqui antes de criar novas automations ligadas ao fluxo de compras ou alterar o catálogo.

- **Stakeholders e usuários chave**  
  Podem usar esta seção como mapa de “onde estamos” no fluxo completo.

## Observação importante

Para o estado atual do repositório, a trilha operacional ligada às automações de
compras passa principalmente por:

- `submissions`;
- `automation_audits`;

enquanto `audit_events` permanece relevante para o domínio mais amplo de auth,
sessões e auditoria de plataforma.
