---
id: execução-direta-vite-uvicorn
title: "Execução direta (Vite + Uvicorn + Docusaurus)"
sidebar_position: 2
---

## Quando usar
- debug fino de frontend;
- debug fino do BFF;
- desenvolvimento das docs sem container.

## BFF

```bash
cd apps/bff
export DATABASE_URL=postgresql://portal:portaldev@localhost:5432/portal
./run_dev.sh
```

## Host

```bash
cd apps/host
npm install
npm run dev
```

## Docs

```bash
cd apps/docs-site
npm install
npm run start -- --host 0.0.0.0 --port 8000
```

## Cuidados

- o BFF não inicia sem `DATABASE_URL`;
- as docs assumem `baseUrl: "/devdocs/"`;
- não rode BFF e Docs na mesma porta;
- o Host precisa apontar proxies corretos para o ambiente em execução.
