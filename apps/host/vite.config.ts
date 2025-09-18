// vite.config.ts
import { defineConfig, Plugin } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// 1) Normaliza /docs -> /docs/ e adiciona barra final em /docs/<rota> sem extensão
const DocsSlashPlugin = (): Plugin => ({
  name: "docs-trailing-slash",
  configureServer(server) {
    server.middlewares.use((req, _res, next) => {
      if (!req.url) return next();

      // /docs -> /docs/
      if (req.url === "/docs") {
        req.url = "/docs/";
        return next();
      }

      // /docs/<algo> -> /docs/<algo>/ (se não tiver extensão e não terminar com /)
      if (req.url.startsWith("/docs/")) {
        const hasSlash = req.url.endsWith("/");
        const hasExt = /\.[a-z0-9]+(\?.*)?$/i.test(req.url);
        if (!hasSlash && !hasExt) {
          req.url = req.url + "/";
        }
      }
      next();
    });
  },
});

export default defineConfig({
  plugins: [react(), DocsSlashPlugin()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      // ---------- BFF ----------
      "/api":     { target: "http://bff:8000", changeOrigin: true },
      "/catalog": { target: "http://bff:8000", changeOrigin: true },
      // ---------- Docs ----------
      // Serve o MkDocs sob o prefixo /docs no host.
      // Importante: rewrite robusto para evitar path vazio (ex.: "/docs" -> "/").
      "/docs": {
        target: "http://docs:8000",
        changeOrigin: true,
        rewrite: (p) => {
          const np = p.replace(/^\/docs(?=\/|$)/, "");
          return np === "" ? "/" : np;
        },
      },
      // O tema Material referencia assets em /assets/... (raiz).
      // Sem esse proxy, os assets seriam servidos pelo Vite (host) e não pelo MkDocs.
      "/assets": { target: "http://docs:8000", changeOrigin: true },
      // A busca do MkDocs usa /search/search_index.json (e web workers).
      "/search": { target: "http://docs:8000", changeOrigin: true },
       
      
      // ---------- Livereload ----------
      "/livereload":    { target: "http://docs:8000", changeOrigin: true, ws: true },
      "/livereload.js": { target: "http://docs:8000", changeOrigin: true },
    },
  },
});
