---
id: "frontend-host-react-vite-ts"
title: "Frontend (Host – React/Vite/TS)"
sidebar_position: 0
---

Esta seção documenta o Host do portal no estado atual do repositório.

## Objetivos
- mapear `src/`;
- explicar leitura do catálogo;
- descrever RBAC de vitrine;
- registrar a renderização iframe;
- documentar o proxy real do Vite.

## Proxy atual do Host

- `/api`
- `/catalog`
- `/devdocs`

## Observações importantes

- o Host preserva a ordem do catálogo;
- categorias só aparecem quando possuem ao menos um bloco visível;
- o iframe hoje ainda não usa `sandbox`;
- a documentação antiga citava `/docs`, mas o código atual usa `/devdocs`.
