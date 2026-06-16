---
id: ci-cd-se-aplicável
title: "CI/CD (estado atual e lacunas)"
sidebar_position: 5
---

## Estado atual observado no repositório

- não foi encontrada pipeline versionada em `.github/workflows`;
- não há suíte automatizada que bloqueie regressões;
- não há esteira formal documentada para build/publish do Host, BFF e Docs.

## O que já está pronto para uma futura pipeline

- build do Host
- build do Docusaurus
- imagem Docker do BFF
- compose de dev reprodutível
- scripts operacionais

## O que falta documentar/automatizar

- lint e testes automatizados;
- publicação de imagem do BFF;
- publicação estática do Host;
- publicação estática das Docs;
- validação de catálogo e smoke tests de rotas principais.
