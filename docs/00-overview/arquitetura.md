# Arquitetura do Portal AGEPAR

Este documento descreve a arquitetura técnica do **Portal AGEPAR**, cobrindo seus principais componentes, responsabilidades e integrações.

---

## 📐 Visão Geral

O Portal AGEPAR adota uma arquitetura **modular em monorepo**, composta por três camadas principais:

1. **BFF (Backend for Frontend)** – FastAPI  
   - Exposição de APIs unificadas  
   - Sessões de autenticação (mock / real)  
   - Gestão do catálogo de automações  
   - Execução e auditoria das automações  

2. **Host (Frontend)** – React + Vite + TypeScript  
   - Interface principal do usuário  
   - Consome catálogo para montar navegação e blocos  
   - Integração com BFF via proxy `/api` e `/catalog`  
   - RBAC (controle de acesso) simples no cliente  

3. **Docs (Documentação)** – MkDocs Material  
   - Conteúdo técnico hospedado sob `/docs`  
   - Diagramas Mermaid e recursos interativos  
   - Disponível para consulta interna  

---

## 🔄 Fluxo de Dados

```mermaid
flowchart LR
    subgraph Client[Usuário]
        UI[Frontend - React/Vite]
    end

    subgraph BFF[Backend (FastAPI)]
        API[/API Endpoints/]
        CAT[/Catalogo/]
        AUT[/Autenticação/]
        MODS[Automations]
        DB[(SQLite/Postgres)]
    end

    subgraph Docs[Documentação]
        MK[ MkDocs Material ]
    end

    UI -->|HTTP/HTTPS| API
    UI -->|/catalog| CAT
    API --> DB
    CAT --> DB
    MODS --> DB
    AUT --> DB
    UI -->|/docs| MK
````

---

## ⚙️ Componentes

### 🔹 **BFF (FastAPI)**

* Porta: **8000**
* Endpoints principais:

  * `/api/auth/*` → login, sessão, RBAC
  * `/api/automations/{slug}` → execuções modulares
  * `/catalog/*` → catálogo de categorias e blocos
* Banco de dados: **SQLite (dev)** / **Postgres (prod)**
* Logging: INFO/ERROR estruturado

### 🔹 **Host (React/Vite)**

* Porta: **5173**
* Navegação baseada no catálogo
* Carregamento de automações em `<iframe>`
* RBAC via helper `userCanSeeBlock`

### 🔹 **Docs (MkDocs Material)**

* Servido em `/docs` via proxy
* Configuração customizada com:

  * **Mermaid** (diagramas)
  * **Glightbox** (visualização de mídia)
  * **Material for MkDocs** (UI moderna)

---

## 🏗️ Integrações

* **Frontend ↔ Backend** → Proxy Vite (`/api` e `/catalog`)
* **Frontend ↔ Docs** → Proxy para MkDocs (`/docs`)
* **BFF ↔ DB** → ORM + migrações automáticas na inicialização
* **Automations** → módulos isolados que expõem UI em `/ui` e lógica em `/submit`

---

## 📊 Observabilidade

* **Logs estruturados** em JSON
* **Auditoria** de eventos em tabela `audits`
* **Métricas** (futuro): Prometheus/OpenTelemetry

---

## 🚧 Decisões de Arquitetura (ADRs)

* [ADR-0001 – Padrão Monorepo](decisões/adr-0001-padrao-monorepo.md)
* [ADR-0002 – BFF FastAPI + Postgres](decisões/adr-0002-bff-fastapi-postgres.md)
* [ADR-0003 – Host React + Vite](decisões/adr-0003-host-react-vite.md)

---
