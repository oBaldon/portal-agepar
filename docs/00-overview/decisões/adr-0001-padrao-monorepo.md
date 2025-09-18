# ADR-0001: Padrão Monorepo

- **Status:** Aceito ✅  
- **Data:** 2025-09-16  
- **Autores:** Equipe de Arquitetura do Portal AGEPAR  

---

## 🎯 Contexto

O desenvolvimento do Portal AGEPAR envolve múltiplos componentes:  
- **Backend (BFF)** em FastAPI  
- **Frontend (Host)** em React + Vite + TypeScript  
- **Catálogo** central de automações  
- **Documentação técnica** em MkDocs  

Esses componentes são fortemente interdependentes e precisam evoluir de forma coordenada.  
Manter cada parte em repositórios separados aumentaria a complexidade de integração, versionamento e CI/CD.  

---

## 💡 Decisão

Adotar um **monorepo único** contendo todos os serviços, documentação e infraestrutura do Portal AGEPAR.  

**Organização:**
- `apps/bff` → Backend (FastAPI)  
- `apps/host` → Frontend (React + Vite)  
- `catalog/` → Catálogo de automações  
- `docs/` → Documentação (MkDocs)  
- `docker-compose.yml` → Orquestração local  
- `mkdocs.yml` → Configuração de documentação  

---

## 📊 Consequências

### ✅ Benefícios
- **Integração simplificada** entre backend, frontend e docs.  
- **Versionamento único** → uma única fonte de verdade.  
- **CI/CD unificado** → pipelines centralizados.  
- **Facilidade de navegação** para novos desenvolvedores.  
- **Documentação alinhada ao código**.  

### ⚠️ Desafios
- Crescimento do repositório pode dificultar **builds parciais**.  
- Requer disciplina em **isolamento modular** (cada automação deve ser independente).  
- Necessidade de **pipelines inteligentes** (executar apenas jobs afetados por mudanças).  

---

## 🔄 Alternativas Consideradas

1. **Multi-repo (repos separados por serviço)**  
   - Vantagens: maior isolamento.  
   - Desvantagens: gestão mais complexa de versões e integração.  

2. **Hybrid repo (monorepo parcial, docs separados)**  
   - Vantagens: separação de escopo.  
   - Desvantagens: risco de documentação ficar desatualizada.  

**Motivo da rejeição:** Ambos aumentam o custo operacional e dificultam a evolução coordenada.  

---

## 📌 Próximos Passos

- Configurar **CI/CD incremental** para evitar builds desnecessários.  
- Definir guidelines para **módulos isolados** dentro do monorepo.  
- Criar ADRs complementares sobre:
  - Estrutura do BFF e automations  
  - Catálogo centralizado  
  - Estratégia de documentação contínua  

---

🔗 **Relacionado a:**  
- [ADR-0002 – BFF FastAPI + Postgres](adr-0002-bff-fastapi-postgres.md)  
- [ADR-0003 – Host React + Vite](adr-0003-host-react-vite.md)  
