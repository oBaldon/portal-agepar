---
id: vite-config-e-plugins
title: "Vite config e plugins"
sidebar_position: 6
---

Arquivo de referência:
- `apps/host/vite.config.ts`

## Estado atual do proxy

```ts
proxy: {
  "/api":     { target: "http://bff:8000", changeOrigin: true },
  "/catalog": { target: "http://bff:8000", changeOrigin: true },
  "/devdocs": { target: "http://docs:8000", changeOrigin: true },
}
```

## O que isso significa

- o Host não fala direto com URLs externas no código das páginas;
- o catálogo vem pelo mesmo host;
- as docs de dev são publicadas em `/devdocs/`.

## Quando rodar local sem Docker

Ajuste os targets para `localhost`, mas mantenha a ideia:
- `/api` e `/catalog` → BFF
- `/devdocs` → Docusaurus
