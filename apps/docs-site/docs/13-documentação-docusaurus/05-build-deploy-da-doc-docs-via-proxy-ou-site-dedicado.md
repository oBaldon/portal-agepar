---
id: build-deploy-da-doc-docs-via-proxy-ou-site-dedicado
title: "Build & deploy da doc (`/devdocs` via proxy ou site dedicado)"
sidebar_position: 5
---

## Estado atual em desenvolvimento

- Docusaurus sobe no serviço `docs`
- porta interna: `8000`
- porta direta exposta: `9000`
- Host proxia `"/devdocs"` para `http://docs:8000`
- `docusaurus.config.ts` usa `baseUrl: "/devdocs/"`

## Build

```bash
cd apps/docs-site
npm install
npm run build
```

## Publicação via Host

Para servir as docs atrás do portal, mantenha:
- o proxy em `/devdocs`
- o `baseUrl` do Docusaurus coerente

## Publicação dedicada

Se o site for publicado em outro caminho:
- ajuste `url`
- ajuste `baseUrl`
- gere novo build

## Observação

A documentação antiga misturava `/docs` e `/devdocs`. O código atual está
alinhado em `/devdocs/`.
