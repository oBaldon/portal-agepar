# Visão Geral do Portal AGEPAR

O **Portal AGEPAR** é uma plataforma modular destinada a **automatizar e centralizar o fluxo de compras públicas**, oferecendo um ecossistema integrado de backend, frontend e documentação técnica.

---

## 🎯 Objetivos do Sistema

- **Centralizar processos** de compras em uma interface única.  
- **Padronizar automações** para DFD, PCA, ETP, TR, Cotação/Dispensa/Licitação, Contrato e Execução.  
- **Oferecer modularidade**, onde cada automação é um módulo independente.  
- **Garantir segurança e rastreabilidade**, com autenticação, RBAC e auditoria.  
- **Fornecer documentação técnica contínua**, acessível via `/docs`.  

---

## 🧩 Componentes Principais

### **1. BFF (Backend for Frontend – FastAPI)**
- Camada de orquestração entre frontend, catálogo e banco de dados.  
- Responsável por autenticação, sessões e RBAC.  
- Exposição de automações via endpoints dedicados.  
- Persistência em **SQLite (desenvolvimento)** ou **Postgres (produção)**.  

### **2. Host (Frontend – React + Vite + TS)**
- Consome o catálogo e monta a navegação dinâmica.  
- Renderiza automações em **iframes isolados**.  
- Implementa RBAC simplificado no cliente.  
- Proxies configurados para `/api`, `/catalog` e `/docs`.  

### **3. Documentação (MkDocs Material)**
- Fornece documentação **técnica e profissional**.  
- Inclui diagramas em **Mermaid**, exemplos de uso e ADRs.  
- Hospedado no próprio host em `/docs`.  

---

## 📂 Estrutura do Repositório

```plaintext
portal-agepar/
├── apps/
│   ├── bff/          # Backend (FastAPI)
│   └── host/         # Frontend (React/Vite/TS)
├── docs/             # Documentação (MkDocs)
├── catalog/          # Catálogo de automações
├── docker-compose.yml
└── mkdocs.yml
````

---

## 🔄 Fluxo de Uso

1. O usuário acessa o **Host** (React/Vite).
2. O Host lê o **Catálogo** e monta a navegação.
3. Ao acessar uma automação, o Host abre um **iframe** apontando para o BFF.
4. O **BFF** valida permissões, persiste submissões e dispara automações.
5. Logs e auditorias são armazenados no banco de dados.
6. A **documentação técnica** está disponível em `/docs`.

---

## 🚀 Diferenciais Técnicos

* Arquitetura **modular e extensível** (novas automações como módulos independentes).
* Integração ponta a ponta entre **frontend, backend e docs**.
* Uso de **padrões de projeto** no BFF (validações Pydantic, logs, auditoria).
* Documentação técnica sempre alinhada ao código.

---

📖 **Próximo passo:** [Arquitetura](arquitetura.md)
