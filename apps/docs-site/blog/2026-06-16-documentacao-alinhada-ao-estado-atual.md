---
slug: documentacao-alinhada-ao-estado-atual
title: Bastidores — documentação alinhada ao estado atual do Portal AGEPAR
authors: [baldon]
tags: [documentação, docusaurus, arquitetura, portal-agepar]
description: O que foi revisado na documentação para refletir o estado atual do monorepo, das automações, do banco e do fluxo de compras.
---
A documentação do Portal AGEPAR passou por uma revisão para se aproximar do **estado real do repositório**, reduzindo o drift entre código, infra, catálogo e guias funcionais.

A revisão focou em quatro frentes:

- consolidar a arquitetura atual com **Host React/Vite/TS + BFF FastAPI + docs em Docusaurus + PostgreSQL**;
- alinhar o fluxo de desenvolvimento local com `infra/scripts/dev.sh` e os arquivos de compose realmente usados;
- atualizar o inventário de automações, blocos do catálogo e domínios persistidos;
- revisar a documentação do fluxo de compras para refletir o que já existe hoje, especialmente em **DFD** e **ETP**.

{/* truncate */}

## O que mudou

### 1. Arquitetura e operação

As páginas de visão geral, setup e operação foram revisadas para refletir o comportamento atual do repositório, incluindo:

- docs servidas em **`/devdocs/`**;
- uso de **PostgreSQL** no ambiente atual;
- fluxo de desenvolvimento baseado nos scripts e composes da pasta `infra/`;
- coexistência de modos de autenticação local e mock, conforme o snapshot do projeto.

📘 **Ver mais**: [/devdocs/docs/visão-geral-e-arquitetura/auditoria-do-estado-atual-do-repo](/devdocs/docs/visão-geral-e-arquitetura/auditoria-do-estado-atual-do-repo)

### 2. Inventário técnico

Também foi reforçada a documentação que ajuda a responder perguntas como:

- quais automações estão ativas no BFF;
- quais blocos aparecem no catálogo;
- quais tabelas e domínios persistidos existem hoje no banco.

📚 **Automações e blocos**: [/devdocs/docs/automations-padrão-de-módulos/inventário-de-automações-e-blocos-do-estado-atual](/devdocs/docs/automations-padrão-de-módulos/inventário-de-automações-e-blocos-do-estado-atual)

🗃️ **Banco e persistência**: [/devdocs/docs/banco-de-dados-persistência/inventário-de-tabelas-e-domínios-do-estado-atual](/devdocs/docs/banco-de-dados-persistência/inventário-de-tabelas-e-domínios-do-estado-atual)

### 3. Padrão editorial

Os arquivos mais novos da doc também foram revisitados para reduzir diferenças de estilo e estrutura entre páginas antigas e recentes, com atenção para:

- `frontmatter`;
- títulos e descrições;
- IDs/rotas consistentes;
- links internos navegáveis;
- separação entre **estado atual**, **legado** e **proposta futura**.

🧭 **Padrão editorial**: [/devdocs/docs/documentação-docusaurus/padrão-editorial-e-template-de-página](/devdocs/docs/documentação-docusaurus/padrão-editorial-e-template-de-página)

### 4. Fluxo de compras público

Uma parte importante da revisão foi atualizar a narrativa do fluxo de compras para que a documentação não descreva um produto antigo.

Hoje, a base já contempla automações reais como **DFD** e **ETP**, além de blocos e categorias concretas no catálogo. Com isso, a documentação passou a tratar com mais clareza:

- o que já está implementado;
- o que ainda é demonstração;
- o que permanece como evolução futura.

🧾 **Guia do fluxo**: [/devdocs/docs/guias-de-produto-fluxo-compras-público](/devdocs/docs/guias-de-produto-fluxo-compras-público)

## Por que isso importa

Quando a documentação acompanha o estado real do repositório:

- onboarding fica mais previsível;
- troubleshooting fica mais rápido;
- automações novas seguem padrões com menos retrabalho;
- decisões de arquitetura ficam registradas de forma mais confiável.

A ideia desta passada não foi “embelezar” a doc, mas torná-la mais útil para quem desenvolve, opera e evolui o Portal AGEPAR no dia a dia.
