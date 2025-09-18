# Layout do Monorepo

Este documento descreve a organização do repositório **Portal AGEPAR**, destacando os principais diretórios, responsabilidades e convenções de projeto.

---

## 📂 Estrutura Geral

```plaintext
portal-agepar/
├── apps/
│   ├── bff/              # Backend (FastAPI)
│   │   ├── app/          # Código principal
│   │   │   ├── api/      # Rotas globais (auth, catalog, health)
│   │   │   ├── automations/ # Módulos de automação isolados
│   │   │   ├── core/     # Config, middlewares, segurança, logging
│   │   │   ├── db/       # Modelos e inicialização do banco
│   │   │   └── utils/    # Funções auxiliares
│   │   └── tests/        # Testes de unidade e integração (pytest)
│   │
│   └── host/             # Frontend (React + Vite + TS)
│       ├── src/
│       │   ├── components/  # Componentes reutilizáveis
│       │   ├── pages/       # Páginas principais
│       │   ├── hooks/       # React hooks
│       │   ├── utils/       # Funções auxiliares
│       │   └── types/       # Tipagens globais
│       └── tests/           # Testes frontend (Vitest)
│
├── catalog/              # Catálogo de categorias e blocos
│   ├── dev.json          # Catálogo de desenvolvimento
│   └── prod.json         # Catálogo de produção (separado futuramente)
│
├── docs/                 # Documentação técnica (MkDocs)
│   ├── 00-overview/      # Visão geral e ADRs
│   ├── 10-bff/           # Backend
│   ├── 20-host/          # Frontend
│   ├── 30-catalog/       # Catálogo
│   ├── 40-infra/         # Infraestrutura
│   ├── 50-operacoes/     # Operações
│   ├── 60-testes/        # Testes
│   └── 70-referencia/    # Referências
│
├── mkdocs.yml            # Configuração MkDocs Material
├── docker-compose.yml    # Orquestração local com containers
└── README.md             # Entrada do projeto
````

---

## 📦 Convenções

* **Automations**: Cada automação é um módulo independente em `apps/bff/app/automations/{slug}.py`.
* **Docs**: Sempre criar documentação para cada automação em `docs/10-bff/automations/{slug}.md`.
* **Tests**: Testes devem ser escritos próximos ao código (`tests/` em cada serviço).
* **Catalog**: O catálogo define a navegação do frontend e deve ser mantido sincronizado com o BFF.

---

## 🔄 Fluxos de Desenvolvimento

1. Criar nova automação → `apps/bff/app/automations/`
2. Adicionar entrada no catálogo → `catalog/dev.json`
3. Criar docs correspondentes → `docs/10-bff/automations/{slug}.md`
4. Executar testes → `pytest` no BFF ou `vitest` no Host
5. Atualizar ADRs se necessário → `docs/00-overview/decisões/`

---

## 🛠 Ferramentas e Stack

* **Backend:** FastAPI, Pydantic v2, SQLAlchemy, SQLite/Postgres
* **Frontend:** React, Vite, TypeScript, ShadCN/UI, Tailwind
* **Infra:** Docker Compose, CI/CD pipelines
* **Docs:** MkDocs Material + plugins (Mermaid, Glightbox)

---

📖 **Próximo passo:** [Decisões de Arquitetura](decisões/adr-0001-padrao-monorepo.md)
