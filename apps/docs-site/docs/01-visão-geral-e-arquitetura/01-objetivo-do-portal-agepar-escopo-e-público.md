---
id: objetivo-da-plataforma-agepar-escopo-e-público
title: "Objetivo da Plataforma AGEPAR, escopo e público"
sidebar_position: 1
---

A **Plataforma AGEPAR** centraliza **fluxos de compras públicas** fim‑a‑fim (DFD → PCA → ETP → TR → Cotação/Dispensa/Licitação → Contrato → Execução/Empenho/Pagamento), oferecendo **automations modulares** orquestradas por um **BFF (FastAPI)** e apresentadas em um **Host (React/Vite/TS)**. A documentação para não‑devs é servida via **MkDocs/Material** (proxy em `/docs`).

## Objetivos do produto
- **Padronizar** e **acelerar** as etapas do processo de compras públicas com automações acopladas por módulos (BFF + UI simples via iframe).
- **Traçar trilhas de auditoria** em cada submissão (tabelas `submissions` e `audits`), com logs claros e status consistentes.
- **Evitar atrito de integração**: Catálogo declarativo em `/catalog/dev` define categorias/blocos, RBAC simples (regra **ANY‑of**) e ordem preservada.
- **Operar com fricção mínima em dev**: `docker compose up --build` sobe Host/BFF/Docs, com SQLite inicializado no startup.
- **Prover erros legíveis** (HTTP `400/401/403/404/409/422`) e **validação robusta** (Pydantic v2: `populate_by_name=True`, `extra="ignore"`).

## Escopo
Inclui:
- **BFF (FastAPI)** com rotas de sessão mock (`POST /api/auth/login`, `GET /api/me`), catálogo (`/catalog/dev`) e **automations** em `/api/automations/:kind/...` (endpoints padrão: `/schema`, `/ui`, `/submit`, `/submissions`, `/submissions/:id`, `/submissions/:id/download`).
- **Host (React/Vite/TS)** com **navbar por categorias** e **cards por categoria**, renderizando blocos por `ui.type` (ex.: `iframe` → `&lt;iframe src=&lcub;url&rcub; /&gt;`), **RBAC ANY‑of** via `requiredRoles` e **proxies** para `/api`, `/catalog` e `/docs`.
- **Docs (MkDocs/Material)** servidas via Host em `/docs`, com Mermaid e Glightbox.

Fora do escopo (por enquanto):
- Integrações externas proprietárias sem especificação formal.
- Autenticação federada/SSO em produção (o BFF expõe **sessões mock** durante dev).
- Persistência além de SQLite em dev (ex.: Postgres gerenciado).

## Público‑alvo
- **Times internos (dev/ops)**: implementam automations, evoluem catálogo, monitoram auditoria/logs.
- **Servidores públicos/analistas**: utilizam a UI do Host, navegando por categorias/blocos conforme permissão.
- **Gestores/controle**: acompanham trilhas de auditoria, tempos de ciclo e qualidade de dados.

## Como a arquitetura atende esse objetivo
- **Modularidade**: cada automação é um módulo isolado no BFF + **UI no‑build** (HTML/CSS/JS) entregue via `/ui` → carregada por iframe.
- **Acoplamento declarativo**: o **Catálogo** mapeia “onde” cada automação aparece na UI, com rótulos, rotas e RBAC.
- **Observabilidade**: submissões e eventos auditáveis, logs **INFO** no caminho feliz e **ERROR** com contexto (request_id, user, automation, submission_id).
- **DX**: proxies do Vite e endpoints previsíveis reduzem o custo cognitivo e simplificam testes (cURL).

## Evidências no repositório (amostras)
- Compose: `—`
- Vite config: `apps/host/vite.config.ts`
- package.json (host): `apps/docs-site/package.json`
- Pistas FastAPI (exemplo): `apps/bff/app/main.py`
- Catálogo JSON (exemplo): `catalog/catalog.dev.json`
- Decorators de rotas (aprox.): `GET=66`, `POST=26`

## Exemplos rápidos

### Ver catálogo
```bash
curl -s http://localhost:8000/catalog/dev | jq .
```

### Sessão mock
```bash
curl -i -X POST http://localhost:8000/api/auth/login   -H "Content-Type: application/json"   -d '{"username":"dev","password":"dev"}'
```

### Automations (UI)
```bash
# Exemplo para a automação :kind
curl -s http://localhost:8000/api/automations/dfd/ui
```

## Próximos passos
- [ ] Confirmar personas e políticas de RBAC por categoria/bloco.
- [ ] Fixar SLAs (tempo de submissão/processamento) e **métricas de sucesso** (lead time por etapa, taxa de erro).
- [ ] Versionar Catálogo por ambiente (dev/hml/prod) e definir _release process_.
- [ ] Mapear integrações externas (se houver), com contratos e _healthchecks_.

---

> _Criado em 2025-10-27 12:24:32_