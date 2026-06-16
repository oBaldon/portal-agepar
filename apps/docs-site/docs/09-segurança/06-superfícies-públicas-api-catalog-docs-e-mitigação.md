---
id: superfícies-públicas-api-catalog-docs-e-mitigação
title: "Superfícies públicas (/api, /catalog, /devdocs) e mitigação"
sidebar_position: 6
---

## Superfícies expostas hoje

- BFF: `/api`, `/health`, `/version`, `/catalog/dev`
- Host: `/`
- Docs: `/devdocs/`

## O que já existe

- CORS configurável
- cookie de sessão
- sessão server-side validada em banco
- RBAC no BFF
- RBAC de vitrine no Host
- auditoria

## O que continua pendente

- endurecimento do iframe do Host com `sandbox`
- revisão de CSRF para o modelo com cookie
- saneamento de segredos versionados
- hardening de produção para cookie seguro/TLS
