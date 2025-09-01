
# Portal AGEPAR (dev)

Arquitetura **BFF (FastAPI)** + **Host (React + Vite + TS + Tailwind)**. Catálogo dirigido: o host lê `/catalog/dev` e gera navegação/rotas. Autenticação **mock** com sessão de cookie.

## Subir em desenvolvimento

```bash
docker compose -f infra/docker-compose.dev.yml up -d --build
docker compose -f infra/docker-compose.dev.yml ps
docker compose -f infra/docker-compose.dev.yml logs -f bff


Abra: http://localhost:5173

Variáveis (dev)

bff: ENV=dev, AUTH_MODE=mock, EP_MODE=mock, SESSION_SECRET=dev-secret, CORS_ORIGINS=http://localhost:5173, CATALOG_FILE=/catalog/catalog.dev.json.

host: VITE_CATALOG_URL=http://localhost:8000/catalog/dev.

Smoke tests

GET http://localhost:8000/health → {"status":"ok"}

Acessar http://localhost:5173 → tela de Login.

Botão Pular → cria sessão mock, redireciona ao primeiro item do catálogo.

Header mostra Portal AGEPAR e menu Início; /home renderiza <iframe> do BFF (/demo/home).

Botão Sair → POST /api/auth/logout e volta ao Login.

Extensões

Adicionar módulo: edite catalog/catalog.dev.json (navigation + routes). O host reflete automaticamente.

Futuro OIDC: placeholders no BFF (variáveis OIDC_*) para implementação com fluxo Authorization Code + PKCE e validação via JWKS.

Blocos React nativos: já reservado ui.type: "react" / routes[].kind: "react" (renderiza mensagem “não implementado”).


---

## Como rodar (resumo)

```bash
# 1) Subir
docker compose -f infra/docker-compose.dev.yml up -d --build

# 2) Ver serviços
docker compose -f infra/docker-compose.dev.yml ps

# 3) Logs (BFF)
docker compose -f infra/docker-compose.dev.yml logs -f bff

# 4) Abrir no navegador
# http://localhost:5173
```
