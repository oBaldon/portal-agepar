---
id: "build-run-deploy"
title: "Build, Run & Deploy"
sidebar_position: 0
---

Esta seção descreve como executar e empacotar o projeto sem esconder as
peculiaridades do estado atual do repositório.

## Resumo
- dev usa compose combinado ou `infra/scripts/dev.sh`
- docs vivem em `/devdocs/`
- BFF exige Postgres
- Host e Docs são buildáveis como artefato estático
- CI/CD ainda não está consolidada no repo
