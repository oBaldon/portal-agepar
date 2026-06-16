---
id: proxies-do-vite-api-catalog-docs
title: "Proxies do Vite (/api, /catalog, /devdocs)"
sidebar_position: 3
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

## Efeito prático

- a SPA fala com o BFF sem expor `localhost:8000` no código da UI;
- o catálogo chega via mesmo host;
- a doc de dev é acessada em `/devdocs/`.

## Observação

Boa parte da documentação antiga ainda falava em `/docs`. O código atual está em
`/devdocs`, inclusive no `baseUrl` do Docusaurus.
