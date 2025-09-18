# Vite – Configuração de Proxies

O **Host (React + Vite + TS)** acessa o **BFF (FastAPI)** e a **Documentação (MkDocs)** por meio de **proxies** de desenvolvimento.  
Esta página descreve a configuração recomendada, por que usamos proxy e como diagnosticar problemas.

---

## 🎯 Objetivos

- Encaminhar `/api` e `/catalog` → **BFF** (porta 8000).
- Encaminhar `/docs` (e livereload) → **MkDocs** (porta 8000 do container `docs`).
- Evitar CORS em desenvolvimento (mesma origem via proxy).
- Imitar **paths reais** de produção (host serve `/docs` via BFF).

---

## 🔧 vite.config.ts (dev)

```ts
// apps/host/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true, // permite acesso externo (útil em docker)
    proxy: {
      // API do BFF
      "/api": {
        target: "http://bff:8000",
        changeOrigin: true,
        secure: false,
        // reescrita opcional: manter path como está
        // rewrite: (p) => p,
      },
      // Catálogo
      "/catalog": {
        target: "http://bff:8000",
        changeOrigin: true,
        secure: false,
      },
      // Docs (MkDocs), incluindo livereload/ws
      "/docs": {
        target: "http://docs:8000",
        changeOrigin: true,
        secure: false,
        ws: true,
      },
      // Algumas versões do MkDocs usam /livereload
      "/livereload": {
        target: "http://docs:8000",
        changeOrigin: true,
        secure: false,
        ws: true,
      },
    },
  },
  preview: {
    port: 5173,
  },
});
````

> **Importante:** Os hosts `bff` e `docs` presumem **rede Docker Compose**. Em execução local sem Docker, troque por `http://localhost:8000`.

---

## 🐳 Docker Compose (exemplo de rede)

```yaml
# docker-compose.yml (trecho)
services:
  host:
    build: ./apps/host
    ports:
      - "5173:5173"
    depends_on:
      - bff
      - docs
    environment:
      - VITE_API_BASE=/api
      - VITE_CATALOG_BASE=/catalog
      - VITE_DOCS_BASE=/docs
    # host acessa bff:8000 e docs:8000 pelo nome do serviço

  bff:
    build: ./apps/bff
    ports:
      - "8000:8000"

  docs:
    build: ./docs
    expose:
      - "8000"
```

* O Vite no `host` **não precisa** publicar portas do `bff`/`docs`, só **enxergar** esses serviços na rede do Compose.

---

## 🔒 CORS x Proxy

* Em **dev**, o proxy evita CORS: para o navegador, tudo vem de `http://localhost:5173`.
* No **BFF**, mantenha `CORS_ALLOWED_ORIGINS=http://localhost:5173` **apenas** se for acessar o BFF **direto**, sem proxy.
* Em **prod**, a recomendação é o **Host** servir tudo sob o mesmo domínio (Nginx/Traefik), mantendo caminhos `/api`, `/catalog`, `/docs`.

---

## 🧪 Testes rápidos

* **API**

  ```bash
  curl -i http://localhost:5173/api/health
  ```
* **Catálogo**

  ```bash
  curl -i http://localhost:5173/catalog/dev
  ```
* **Docs**

  * Acesse `http://localhost:5173/docs/` (deve carregar mkdocs).
  * Verifique live-reload: editar um `.md` deve refletir em \~1s.

Se **500/404** aparecer no `5173`, verifique o log do Vite (target inatingível) e se os serviços `bff`/`docs` estão de pé.

---

## 🧭 Paths e Ambiente

* **Front** deve sempre chamar **paths relativos** (`/api/...`, `/catalog/...`, `/docs/...`) para funcionar em **dev** e **prod**.
* Evite embutir hostnames. Quando necessário, use env:

  ```ts
  const API_BASE = import.meta.env.VITE_API_BASE || "/api";
  fetch(`${API_BASE}/health`);
  ```

---

## 🛡️ Segurança (produção)

* **Reverse proxy** (Nginx/Traefik) deve:

  * Restringir `frame-ancestors`/CSP apropriadamente.
  * Forçar HTTPS e definir `Secure` em cookies de sessão.
  * Passar cabeçalhos de client (`X-Forwarded-For`, `X-Real-IP`) ao BFF.

Exemplo de mapeamento (Nginx):

```nginx
location /api/ { proxy_pass http://bff:8000/api/; }
location /catalog/ { proxy_pass http://bff:8000/catalog/; }
location /docs/ { proxy_pass http://docs:8000/; }
```

> Ajuste `proxy_set_header` conforme necessidade para CORS e cookies.

---

## 🧰 Troubleshooting

* **Erro CORS mesmo com proxy**

  * Verifique se o front está chamando `http://localhost:8000` **direto** (trocar para `/api` etc.).
  * Cheque `server.proxy` do Vite e nomes de host corretos (`bff`, `docs`).

* **404 em `/docs/`**

  * MkDocs não está rodando ou proxy errado. Teste direto: `curl http://docs:8000/`.

* **WebSocket do MkDocs não recarrega**

  * Assegure `ws: true` na entrada `/docs`/`/livereload`.

* **Cookies não chegam**

  * Garanta `changeOrigin: true`; confira `SameSite` e `Secure` em dev/prod.

* **Time-out no fetch**

  * BFF lento ou indisponível. Veja logs no container `bff`.

---

## ✅ Checklist

* [ ] `/api` e `/catalog` apontando para o **BFF**.
* [ ] `/docs` e `/livereload` apontando para o **MkDocs** com `ws: true`.
* [ ] Front chama **paths relativos** sem hostname.
* [ ] Compose com serviços na mesma rede.
* [ ] Reverse proxy em prod replica esses mapeamentos.

---

## 🔮 Futuro

* Templates de vite config por ambiente (dev/stage/prod).
* Health-check de `bff` e `docs` no próprio Host com banner de status.
* Auto-fallback para `/catalog/dev` quando `/catalog/prod` falhar.

