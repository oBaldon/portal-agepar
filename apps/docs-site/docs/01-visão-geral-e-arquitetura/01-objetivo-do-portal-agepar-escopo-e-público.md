---
id: objetivo-do-portal-agepar-escopo-e-público
title: "Objetivo do Portal AGEPAR, escopo e público"
sidebar_position: 1
---

O Portal AGEPAR é uma plataforma interna modular para centralizar rotinas
operacionais e automações de negócio, com foco forte em fluxo documental,
compras públicas, apoio administrativo e produtividade institucional.

## Público principal

- desenvolvimento e sustentação da plataforma
- áreas administrativas da AGEPAR
- equipes que operam compras, férias, tarefas, suporte, avisos e gestão de usuários
- perfis com governança/auditoria

## Escopo técnico atual

O escopo realmente implementado hoje inclui:

- autenticação local com sessão persistida em banco;
- leitura de catálogo por categorias;
- SPA com páginas públicas e protegidas;
- módulos de automação servidos por HTML simples via iframe;
- geração de documentos e downloads;
- trilha de auditoria;
- notificações e avisos globais;
- gestão de tarefas;
- gestão de usuários, contas e sessões.

## Macrofluxos de produto já representados

### Compras
- DFD
- ETP
- PCA ainda como bloco demonstrativo
- módulos auxiliares como `form2json`

### Pessoas
- férias
- saldo de ponto
- usuários
- perfil

### Produtividade e governança
- tarefas
- controle / auditoria
- fileshare
- avisos
- whoisonline

## O que não é mais verdade no estado atual

A base já não é mais:
- um portal com docs MkDocs;
- um backend apoiado em SQLite;
- um app centrado apenas em “sessões mock”.

A documentação desta seção foi atualizada justamente para refletir a evolução do projeto.
