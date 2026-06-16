---
id: estratégia-de-build-prod-e-artefatos
title: "Estratégia de build (prod) e artefatos"
sidebar_position: 4
---

## Host
Dentro de `apps/host`:

```bash
npm install
npm run build
```

Artefato:
- `apps/host/dist/`

## Docs
Dentro de `apps/docs-site`:

```bash
npm install
npm run build
```

Artefato:
- `apps/docs-site/build/`

## BFF
Imagem Docker baseada em:
- `apps/bff/Dockerfile.dev` no estado atual do repositório

> O repo ainda não traz um `Dockerfile` de produção separado e consolidado.

## Atenção com as docs

O build do Docusaurus assume `baseUrl: "/devdocs/"`. Se a publicação final usar
outro path, ajuste `docusaurus.config.ts` antes do build.
