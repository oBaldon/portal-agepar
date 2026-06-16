---
id: index
title: "BFF (FastAPI)"
sidebar_position: 0
---

O BFF é o backend de fronteira do Portal AGEPAR e hoje concentra:
- auth local e sessões persistidas;
- catálogo;
- automações;
- notificações;
- trilha de auditoria;
- tarefas;
- endpoints utilitários.

## Ponto-chave desta revisão

A documentação antiga enfatizava “sessões mock” como padrão do sistema. O código
atual, porém, já está orientado a **auth local com banco**, com mock legado como
suporte de dev em cenários específicos.

## Mapa rápido

- `main.py` → aplicação, middlewares, startup, routers
- `db.py` → persistência operacional
- `auth/` → login, sessão, RBAC, política de senha
- `automations/` → módulos do produto
