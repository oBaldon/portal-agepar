---
slug: postmortem-proxy-docs
title: Postmortem — Proxy de /docs falhando
authors: [dev-team]
tags: [postmortem, observabilidade, vite]
description: Incidente 502 ao acessar /docs após deploy do Host — causa, impacto e ações.
---

**Resumo**  
Erro 502 ao acessar `/docs` após um deploy.

<!-- truncate -->

**Linha do tempo**
- 10:12 — Deploy do Host
- 10:15 — Alertas 5xx
- 10:25 — Rollback aplicado

**Causa raiz**  
Regra de proxy faltando no `vite.config.ts`.

**Ações**  
- Teste automático de saúde do proxy
- Checklist de release

🔎 **Guia**: [/devdocs/docs/build-run-deploy/proxies-do-vite-api-catalog-docs](/devdocs/docs/build-run-deploy/proxies-do-vite-api-catalog-docs)
