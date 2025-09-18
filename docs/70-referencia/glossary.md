# Referência – Glossário

Este glossário reúne termos técnicos e de negócio utilizados no Portal AGEPAR.  
O objetivo é padronizar linguagem entre equipes de **desenvolvimento**, **operação** e **usuários técnicos**.

---

## 📚 Termos Técnicos

- **BFF (Backend for Frontend)** → Camada intermediária (FastAPI) que expõe APIs, integra banco e automações.  
- **Host** → Frontend principal (React + Vite + TS) que consome o catálogo e renderiza blocos.  
- **Docs** → Documentação técnica em MkDocs Material, servida via `/docs`.  
- **RBAC (Role-Based Access Control)** → Controle de acesso baseado em papéis (roles).  
- **Session Cookie** → Cookie HttpOnly usado para manter sessão do usuário autenticado.  
- **Catalog** → Definição JSON de categorias e blocos (UI dinâmica).  
- **Automation** → Módulo isolado no BFF + UI em iframe, responsável por uma tarefa (ex.: DFD, Form2JSON).  
- **Submission** → Registro persistido de entrada em uma automação.  
- **Audit** → Registro de evento de sistema (quem fez, o que fez, quando).  
- **OpenAPI** → Especificação da API em formato padronizado.  
- **JSON Schema** → Especificação usada para validar catálogos.  
- **Health Check** → Endpoint que confirma se a aplicação está saudável.  
- **Background Task** → Processamento assíncrono disparado após submissão.  

---

## 📑 Termos de Negócio

- **DFD (Documento de Formalização da Demanda)** → Primeira etapa do fluxo de compras públicas.  
- **PCA (Plano de Contratações Anual)** → Documento que consolida demandas de compras.  
- **ETP (Estudo Técnico Preliminar)** → Documento que fundamenta a contratação.  
- **TR (Termo de Referência)** → Documento que define requisitos técnicos e condições de fornecimento.  
- **Cotação** → Processo simplificado de coleta de preços.  
- **Dispensa** → Contratação sem licitação, em casos previstos em lei.  
- **Licitação** → Processo formal de seleção de fornecedor.  
- **Contrato** → Documento que formaliza o fornecimento entre órgão e fornecedor.  
- **Empenho** → Ato contábil que reserva dotação orçamentária para a despesa.  
- **Execução** → Etapa de cumprimento contratual.  
- **Pagamento** → Liquidação da despesa e quitação ao fornecedor.  

---

## 🔮 Futuro

- Adicionar termos relacionados a **observabilidade** (logs, métricas, tracing).  
- Expandir para termos de **DevOps** usados em pipelines e deploys.  
- Integrar glossário como **tooltips** no Host para novos servidores públicos.  