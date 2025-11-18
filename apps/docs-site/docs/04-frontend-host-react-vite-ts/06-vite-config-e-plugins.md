---
id: vite-config-e-plugins
title: "Vite config e plugins"
sidebar_position: 6
---

Esta página documenta a configuração do **Vite** no Host (React/TS), incluindo **proxies** para BFF/Docs, **HMR em Docker**, **build para subcaminho** e **plugins** recomendados.

> Referência principal: `apps/host/vite.config.ts`.  
> Padrão de rotas em dev: **`/api`**, **`/catalog`** → BFF; **`/docs`** → Docs (Docusaurus).

---

## 1) Arquivo base (Compose – containers)

```ts
// apps/host/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // Se rodar dentro de container, HMR pode precisar de ajustes (ver seção 3)
    proxy: {
      "/api":     { target: "http://bff:8000",  changeOrigin: true },
      "/catalog": { target: "http://bff:8000",  changeOrigin: true },
      "/docs":    { target: "http://docs:8000", changeOrigin: true },
    },
  },
});
````

**O que faz**

* **`@vitejs/plugin-react`**: JSX, Fast Refresh.
* **`server.proxy`**: encaminha as rotas do Host para BFF/Docs.
* **`host: "0.0.0.0"`**: permite acessar o Vite de fora do container.

> Se seu repositório ainda usa **`/devdocs`**, troque a chave `"/docs"` para `"/devdocs"` ou **padronize** para `"/docs"`.

---

## 2) Variante local (fora de Docker)

```ts
// apps/host/vite.config.ts (variante local - ajuste as portas conforme seu start)
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api":     { target: "http://localhost:8000", changeOrigin: true },
      "/catalog": { target: "http://localhost:8000", changeOrigin: true },
      "/docs":    { target: "http://localhost:8000", changeOrigin: true }, // Docusaurus em 8000
      // ou use a porta do seu Docusaurus local: 3000, 8001...
    },
  },
});
```

> **BFF** e **Docs** não devem compartilhar a mesma porta quando rodando localmente.

---

## 3) HMR em Docker (Hot Module Replacement)

Quando o Vite roda **em container** e o navegador está no host, pode ser necessário configurar **HMR** para apontar para o host/porta corretos:

```ts
// apps/host/vite.config.ts (trecho opcional)
server: {
  host: "0.0.0.0",
  port: 5173,
  hmr: {
    // se acessar pelo host local:
    clientPort: 5173,
    // se precisar informar hostname público:
    // host: "localhost",
    // protocol: "ws", // ou "wss" atrás de TLS
  },
  // Em ambientes com FS montado:
  // watch: { usePolling: true, interval: 1000 },
}
```

> Use `usePolling` apenas se necessário (sistemas de arquivos de rede/WSL2 lentos).

---

## 4) Build para subcaminho (base path)

Se o Host for servido sob **subcaminho** (ex.: `/portal/`), configure **`base`** no build:

```ts
// apps/host/vite.config.ts (exemplo com base)
export default defineConfig({
  base: "/portal/", // ajuste conforme o caminho público
  plugins: [react()],
  // ...
});
```

E no deploy (NGINX), garanta `try_files`/fallback para SPA. Veja a seção **Build & Deploy**.

---

## 5) Variáveis de ambiente (`VITE_*`)

Somente variáveis prefixadas com **`VITE_`** ficam **expostas ao front** em `import.meta.env`.

```ts
// uso em código TS/TSX
const apiBase = import.meta.env.VITE_API_BASE ?? "/api";
```

**Boas práticas**

* Centralize leituras em um módulo `env.ts`.
* **Não** exponha segredos; cookies/sessão são geridos no BFF.

---

## 6) Plugins úteis

* **`@vitejs/plugin-react`** *(já usado)* – Fast Refresh e transformações React.
* **`vite-tsconfig-paths`** *(opcional)* – respeita `paths` do `tsconfig.json`.
* **`rollup-plugin-visualizer`** *(opcional em build)* – analisa bundle.

```ts
// exemplo com plugins extras
import tsconfigPaths from "vite-tsconfig-paths";
import { visualizer } from "rollup-plugin-visualizer";

export default defineConfig({
  plugins: [
    react(),
    tsconfigPaths(),
    // só em build:
    visualizer({ filename: "stats.html", open: false }) as any,
  ],
});
```

---

## 7) Testes rápidos (proxy)

```bash
# via proxy do Host (dev)
curl -i http://localhost:5173/api/docs
curl -s http://localhost:5173/catalog/dev | jq .
curl -i http://localhost:5173/docs
```

As respostas devem corresponder às origens:

* `http://localhost:8000/api/docs`
* `http://localhost:8000/catalog/dev`
* `http://localhost:8000` (Docs)

---

## 8) Problemas comuns

* **`/docs` retorna 404**
  Verifique se o serviço de Docs está no ar e se a chave `"/docs"` está no `proxy`.

* **HMR não conecta (WebSocket)**
  Ajuste `server.hmr.clientPort`/`host` para o hostname acessível pelo navegador.
  Conferir no DevTools → Network → WS.

* **CORS/Sessão quebrando**
  No BFF, inclua `http://localhost:5173` **e** `http://host:5173` em `CORS_ORIGINS` quando em Compose.

* **Build em subcaminho com assets 404**
  Defina `base` no `vite.config.ts` e ajuste o servidor (NGINX/Apache) para servir estáticos no mesmo subcaminho.

---

## Próximos passos

* **[Navbar por categorias e leitura do catálogo](./navbar-por-categorias-e-leitura-do-catálogo)**
* **[Renderização de blocos (iframe ui.url)](./renderização-de-blocos-iframe-uiurl)**
* **[RBAC simples (requiredRoles ANY-of)](./rbac-simples-requiredroles-any-of)**

---

> _Criado em 2025-11-18_