---
id: build-deploy-da-doc-docs-via-proxy-ou-site-dedicado
title: "Build & deploy da doc (/docs via proxy ou site dedicado)"
sidebar_position: 5
---

Esta página explica como **gerar e publicar** o portal de documentação de dev
(Docusaurus) da Plataforma AGEPAR, tanto:

- **via proxy do Host** (mesmo domínio do portal, em `/docs` ou `/devdocs`),
- quanto como **site dedicado** (subdomínio próprio ou outro host).

> Referências principais no repositório:  
> `apps/docs-site/README.md`, `apps/docs-site/docusaurus.config.ts`,  
> `apps/docs-site/package.json`, `infra/docker-compose.dev.yml`,  
> `apps/host/vite.config.ts`,  
> `apps/docs-site/docs/03-build-run-deploy/04-estratégia-de-build-prod-e-artefatos.md`

---

## 1) Componentes e URLs (visão geral)

O site de docs usa **Docusaurus v3** e é um projeto independente dentro do monorepo:

```text
apps/
  docs-site/
    docs/
    src/
    static/
    docusaurus.config.ts
    package.json
```

No ambiente de desenvolvimento, temos:

* **Serviço `docs`** no Docker Compose:

  * sobe em `http://docs:8000`,
  * roda `npm install` (se necessário) e `npm run start`.
* **Proxy do Host (Vite)**:

  * `apps/host/vite.config.ts` define um proxy para `/devdocs` → `http://docs:8000`,
  * o Host fica em `http://localhost:5173`.

Na prática, em dev:

* **Docs via Host**: `http://localhost:5173/devdocs/`
* **Docs direto no serviço**: `http://localhost:9000/devdocs/` (quando publicado sozinho)

No Docusaurus, o `docusaurus.config.ts` está configurado com:

```ts
const config: Config = {
  url: 'http://localhost',
  baseUrl: '/devdocs/',
  // ...
};
```

Ou seja:

* as URLs internas assumem que o site vive em `/devdocs/`,
* em produção, vamos **ajustar `baseUrl`** conforme a estratégia:

  * `/docs/` (quando atrás do Host),
  * `/` ou outro subcaminho (site dedicado).

---

## 2) Build da doc (local)

Para gerar o site estático das docs:

```bash
# 1) Ir para o projeto de docs
cd apps/docs-site

# 2) Instalar dependências (primeira vez ou após alterações em package.json)
npm install

# 3) Build de produção
npm run build
```

Ao final, o Docusaurus gera o site estático em:

```text
apps/docs-site/build/
  index.html
  assets/
  docs/
  ...
```

Se quiser testar o build localmente:

```bash
# ainda em apps/docs-site
npm run serve
# por padrão, sobe em http://localhost:3000/devdocs/
```

> Dica: o comando `npm run serve` é apenas para conferir o build localmente;
> em produção usaremos um servidor estático (ex.: Nginx) ou container dedicado.

---

## 3) Deploy via Host + proxy (/docs)

### 3.1. Ideia geral

Cenário típico:

* **Host (SPA)** servido em `/`,
* **Docs** servidas em um subcaminho (idealmente `/docs`),
* um **proxy (Nginx/Apache)** encaminha as URLs estáticas para as pastas `dist/` e `build/`.

Nesse cenário:

1. O Host é buildado em `apps/host/dist/`.
2. As Docs são buildadas em `apps/docs-site/build/`.
3. O servidor web é configurado para:

   * servir `dist/` em `/`,
   * servir `build/` em `/docs/`,
   * fazer fallback para `index.html` (spa) quando necessário.

### 3.2. Exemplo de Nginx (Host em `/`, Docs em `/docs`)

Exemplo simplificado baseado na doc de build geral:

```nginx
server {
  listen 80;
  server_name _;

  # Host (SPA) em /
  root /var/www/portal-agepar/host/dist;
  index index.html;

  # Docs (Docusaurus) em /docs
  location /docs/ {
    alias /var/www/portal-agepar/docs/build/;
    try_files $uri $uri/ /docs/index.html;
  }

  # Fallback para SPA do Host
  location / {
    try_files $uri $uri/ /index.html;
  }
}
```

Checklist para este modo:

* [ ] Copiei o build do Host para algo como `/var/www/portal-agepar/host/dist/`.
* [ ] Copiei o build das Docs para algo como `/var/www/portal-agepar/docs/build/`.
* [ ] Configurei o Nginx (ou equivalente) para mapear `/` → Host e `/docs` → Docs.
* [ ] Testei:

  * `https://<dominio>/` (Host),
  * `https://<dominio>/docs/` (Docs).

### 3.3. Ajustando `baseUrl` para `/docs/`

Se as docs forem servir **em `/docs/`**, o Docusaurus precisa saber disso:

```ts
// apps/docs-site/docusaurus.config.ts
const config: Config = {
  url: 'https://<dominio-do-portal>',
  baseUrl: '/docs/',
  // ...
};
```

Cuidados:

* Links internos, breadcrumbs e assets passam a apontar para `/docs/...`.
* Em dev, se você quiser manter `/devdocs/`, use um branch/config separado ou um patch rápido antes do build de produção.

---

## 4) Deploy como site dedicado

Outra opção é publicar as docs como **site independente**, por exemplo:

* `https://devdocs.portal-agepar.pr.gov.br/`

### 4.1. Site dedicado na raiz (`/`)

Se o domínio das docs for exclusivo para a doc (raiz `/`), configure:

```ts
const config: Config = {
  url: 'https://devdocs.portal-agepar.pr.gov.br',
  baseUrl: '/',
  // ...
};
```

Fluxo:

1. Rodar `npm run build` em `apps/docs-site`.
2. Publicar o conteúdo de `build/` no servidor do domínio das docs.
3. Configurar o servidor web para servir `build/` diretamente em `/`.

Checklist:

* [ ] `url` e `baseUrl` configurados para o domínio dedicado.
* [ ] DNS aponta o subdomínio para o servidor das docs.
* [ ] Servidor está servindo `build/` como raiz do site.

### 4.2. Site dedicado em subcaminho

Se as docs ficarem em um subcaminho, por exemplo:

* `https://intra.agepar.pr.gov.br/devdocs/`

então:

```ts
const config: Config = {
  url: 'https://intra.agepar.pr.gov.br',
  baseUrl: '/devdocs/',
  // ...
};
```

E o servidor web precisa mapear esse subcaminho para o `build/` do Docusaurus, com fallback para `/devdocs/index.html`.

---

## 5) Integração com o Host (links de navegação)

No Host (React/Vite), o proxy para as docs em desenvolvimento está configurado em:

```ts
// apps/host/vite.config.ts
server: {
  proxy: {
    "/devdocs": { target: "http://docs:8000", changeOrigin: true },
  },
}
```

Na UI, os links para docs podem apontar para:

* `/devdocs/` no ambiente dev,
* `/docs/` ou para o domínio dedicado nas builds de produção.

Boas práticas:

* Centralizar a URL base das docs em uma **config** (ex.: variável de ambiente ou arquivo de constants).
* Evitar “strings mágicas” de URL espalhadas pelo código.
* Se usar domínio dedicado, considerar abrir as docs em **nova aba/janela**.

---

## 6) Troubleshooting e checklist de deploy

### 6.1. Erros comuns

* **404 em assets das docs**

  * Conferir se `baseUrl` está alinhado com o caminho real (`/docs/`, `/devdocs/` ou `/`).
  * Verificar se o servidor usa `alias` correto e se o caminho do `build/` está certo.

* **Links quebrados após trocar de `/devdocs/` para `/docs/`**

  * Revisar `docusaurus.config.ts` (`url` + `baseUrl`).
  * Rebuildar (`npm run build`) depois de mudar configuração.

* **Loop ou erro de proxy**

  * Garantir que o proxy do Host (`vite.config.ts`) está ligado ao serviço correto (`docs:8000` em dev).
  * Em produção, o proxy (Nginx/ingress) precisa apontar para o servidor estático correto.

### 6.2. Checklist final

* [ ] `apps/docs-site` buildado (`npm run build` → `build/`).
* [ ] `docusaurus.config.ts` com `url`/`baseUrl` corretos para o ambiente.
* [ ] Servidor estático configurado para o diretório `build/`.
* [ ] Rota final das docs acessível (via `/docs`, `/devdocs` ou domínio dedicado).
* [ ] Links do Host apontando para o caminho correto das docs.
* [ ] Smoke tests básicos rodados (acesso à home das docs, algumas páginas internas, assets).

---

## Próximos passos

* Revisar a [estratégia de build (prod) e artefatos](../../03-build-run-deploy/estratégia-de-build-prod-e-artefatos).
* Definir **qual estratégia oficial** será usada em produção (proxy `/docs` ou site dedicado).
* Automatizar o fluxo em **CI/CD** (build do Docusaurus + publicação dos arquivos estáticos).

---

> _Criado em 2025-12-03_