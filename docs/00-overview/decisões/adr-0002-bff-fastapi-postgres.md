# ADR-0002: BFF com FastAPI + Postgres

- **Status:** Aceito ✅  
- **Data:** 2025-09-16  
- **Autores:** Equipe de Arquitetura do Portal AGEPAR  

---

## 🎯 Contexto

O Portal AGEPAR exige uma camada de **Backend for Frontend (BFF)** que:  
- Centralize a comunicação entre frontend e serviços internos.  
- Gerencie autenticação e sessões de usuários.  
- Exponha **módulos de automação** de forma isolada.  
- Mantenha registros em banco de dados com **auditabilidade**.  
- Seja **rápido de desenvolver**, com **validações seguras** e suporte a **async I/O**.  

Além disso, é necessário um banco de dados relacional robusto, capaz de lidar com:  
- **Persistência de submissões** e auditorias.  
- **Consultas estruturadas** (relatórios e integrações futuras).  
- **Migrações consistentes** entre ambientes de dev e produção.  

---

## 💡 Decisão

- **Backend escolhido:** [FastAPI](https://fastapi.tiangolo.com/)  
- **Banco de dados padrão:** [PostgreSQL](https://www.postgresql.org/) (produção)  
- **Banco alternativo:** SQLite (desenvolvimento local)  

---

## 📊 Consequências

### ✅ Benefícios
- **FastAPI**:  
  - Suporte nativo a **async I/O**.  
  - Integração com **Pydantic v2** para validações robustas.  
  - Documentação automática via **OpenAPI/Swagger**.  
  - Comunidade ativa e suporte amplo.  

- **Postgres**:  
  - Banco **relacional maduro e confiável**.  
  - Suporte avançado a JSON, índices, e funções.  
  - Escalabilidade para produção.  
  - Facilidade de migração e integração com ferramentas de BI.  

- **SQLite (dev)**:  
  - Zero configuração.  
  - Rápido para testes locais.  

### ⚠️ Desafios
- Necessidade de **mecanismo de migração** (ex.: Alembic).  
- Manter compatibilidade entre **SQLite (dev)** e **Postgres (prod)**.  
- Garantir que queries complexas não dependam de recursos exclusivos do Postgres.  

---

## 🔄 Alternativas Consideradas

1. **Django REST Framework + Postgres**  
   - Vantagem: ORM maduro, administração embutida.  
   - Desvantagem: mais pesado, menos ágil para automações modulares.  

2. **Node.js (Express/NestJS) + Postgres**  
   - Vantagem: stack unificado JS/TS.  
   - Desvantagem: menor maturidade em validação e OpenAPI.  

3. **FastAPI + MySQL/MariaDB**  
   - Vantagem: alternativa relacional estável.  
   - Desvantagem: Postgres tem mais recursos modernos (JSONB, CTEs, funções).  

**Motivo da rejeição:** todas as alternativas aumentam a complexidade ou reduzem a agilidade.  

---

## 📌 Próximos Passos

- Implementar **migrações automáticas** (Alembic).  
- Criar **tabelas padrão** (`submissions`, `audits`).  
- Definir **boas práticas de queries** para evitar dependência em recursos exclusivos de Postgres.  
- Configurar **testes automatizados** em SQLite e Postgres.  

---

🔗 **Relacionado a:**  
- [ADR-0001 – Padrão Monorepo](adr-0001-padrao-monorepo.md)  
- [ADR-0003 – Host React + Vite](adr-0003-host-react-vite.md)  
