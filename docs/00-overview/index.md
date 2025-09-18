# Visão Geral Técnica

A seção **Visão Geral** documenta os fundamentos arquiteturais do **Portal AGEPAR**, incluindo:  
- Conceitos principais do sistema  
- Estrutura do monorepo  
- Arquitetura técnica  
- Decisões de arquitetura (ADRs)  

---

## 📑 Conteúdo

- [Visão Geral](visao-geral.md)  
- [Arquitetura](arquitetura.md)  
- [Layout do Monorepo](layout-do-monorepo.md)  

### 📝 Decisões de Arquitetura (ADRs)
- [ADR-0001 – Padrão Monorepo](decisões/adr-0001-padrao-monorepo.md)  
- [ADR-0002 – BFF FastAPI + Postgres](decisões/adr-0002-bff-fastapi-postgres.md)  
- [ADR-0003 – Host React + Vite](decisões/adr-0003-host-react-vite.md)  

---

## 🔄 Fluxo de Referência

```mermaid
graph TD
    A[Visão Geral] --> B[Arquitetura]
    B --> C[Layout do Monorepo]
    C --> D[ADRs]
    D --> D1[ADR-0001 Monorepo]
    D --> D2[ADR-0002 BFF FastAPI + Postgres]
    D --> D3[ADR-0003 Host React + Vite]
````

---

## 📌 Próximos Passos

👉 Após entender a visão geral, consulte:

* [Backend (BFF)](../10-bff/overview.md)
* [Frontend (Host)](../20-host/overview.md)
* [Catálogo](../30-catalog/overview.md)
