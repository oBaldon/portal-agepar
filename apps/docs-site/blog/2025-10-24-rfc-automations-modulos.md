---
slug: rfc-automations-modulos
title: RFC — Padrão de Módulos de Automações
authors: [baldon]
tags: [rfc, automations, fastapi]
description: Proposta para consolidar os endpoints e a UI das automações no BFF.
---

**Problema**  
Consolidar endpoints e UI das automações para padronizar desenvolvimento e documentação.

{/* truncate */}

**Proposta**  
Arquivos `apps/bff/app/automations/{slug}.py` com:
- `GET /schema`
- `GET /ui`
- `POST /submit` (BackgroundTasks)
- `GET /submissions`, `GET /submissions/{id}`, `POST /submissions/{id}/download`

**Impacto**  
Padroniza dev e docs.

🔗 **Spec**: [/devdocs/docs/automations-padrão-de-módulos](/devdocs/docs/automations-padrão-de-módulos)
