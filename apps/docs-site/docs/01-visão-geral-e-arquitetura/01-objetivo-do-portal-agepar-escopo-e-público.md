---
id: objetivo-do-portal-agepar-escopo-e-publico
title: "Objetivo do Portal AGEPAR, escopo e público"
sidebar_position: 1
---

O Portal AGEPAR é um monorepo voltado a **fluxos internos de trabalho**, com
ênfase em automações institucionais e, em especial, no fluxo de **compras
públicas**.

## Objetivo do portal

O objetivo do produto é oferecer uma camada única para:

- autenticação e sessão de usuários;
- navegação por catálogo de módulos;
- automações com UI simples, embutidas no Host;
- persistência e trilha de auditoria;
- documentação técnica para evolução do portal.

No estado atual do repositório, esse objetivo já aparece em módulos como:

- DFD;
- ETP;
- Férias;
- Tasks;
- Fileshare;
- Support;
- Avisos;
- WhoIsOnline;
- Painéis de controle e administração.

## Escopo funcional atual

Hoje o portal cobre, ao mesmo tempo:

- **módulos de compras** (`dfd`, `etp`, `pca` em modo demo, `form2json`);
- **módulos de pessoas** (`usuarios`, `ferias`, `ponto_saldo`);
- **módulos de produtividade** (`tasks`, `fileshare`);
- **módulos de governança/administração** (`controle`, `accounts`, `avisos`, `whoisonline`);
- **blocos de laboratório e demonstração** (`demo`, `snake`, `cat2`, `cat3`).

## Público principal

A plataforma serve principalmente:

- devs que mantêm o monorepo;
- áreas internas da AGEPAR que usam as automações;
- times de governança, compras, RH e suporte;
- gestores que precisam de relatórios, auditoria e visibilidade operacional.

## O que esta seção substitui da narrativa antiga

Esta documentação deixa de tratar como estado atual coisas que hoje são apenas
histórico do projeto, por exemplo:

- um backend apoiado em SQLite;
- um site de docs em MkDocs/Material;
- um app centrado apenas em “sessões mock”.

O código atual já representa outro estágio: **FastAPI + React/Vite + Docusaurus
+ PostgreSQL**, com autenticação local persistida e mock legado opcional.
