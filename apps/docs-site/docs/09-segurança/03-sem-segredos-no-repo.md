---
id: sem-segredos-no-repo
title: "Segredos no repositório: regra, desvio atual e ação esperada"
sidebar_position: 3
---

## Regra

Nenhum segredo real deveria estar versionado.

## Estado atual observado

O arquivo `.env.example` do repositório hoje contém valores sensíveis, incluindo
credenciais relacionadas a integração de e-mail. Isso deve ser tratado como
**desvio do padrão esperado**, e não como exemplo aceitável.

## Como interpretar corretamente o repo

- `SESSION_SECRET=dev-secret` é um placeholder de laboratório;
- `PGPASSWORD=portaldev` é um default de dev;
- credenciais nominais para integrações externas **não devem permanecer** em
  arquivo versionado, mesmo em `.env.example`.

## O que a documentação passa a registrar

1. o padrão correto continua sendo “segredos via ambiente/secret manager”;
2. o estado atual do repo ainda tem passivo de saneamento;
3. qualquer uso externo do `.env.example` deve passar por revisão e substituição
   imediata dos valores.
