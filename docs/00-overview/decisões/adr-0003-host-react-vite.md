# ADR-0003: Host com React + Vite

- **Status:** Aceito ✅  
- **Data:** 2025-09-16  
- **Autores:** Equipe de Arquitetura do Portal AGEPAR  

---

## 🎯 Contexto

O Portal AGEPAR precisa de um **frontend moderno e performático**, capaz de:  
- Carregar dinamicamente o **catálogo de automações**.  
- Renderizar automações isoladas em **iframes**.  
- Suportar **RBAC simples** no cliente.  
- Integrar-se via proxy com o **BFF (/api, /catalog)** e a **documentação (/docs)**.  
- Ser **rápido para desenvolver** e ter suporte robusto para **TypeScript**.  

Além disso, é fundamental ter um **build rápido** para acelerar o ciclo de desenvolvimento.  

---

## 💡 Decisão

- **Framework escolhido:** [React](https://react.dev/)  
- **Bundler e dev server:** [Vite](https://vitejs.dev/)  
- **Linguagem:** TypeScript  
- **UI Kit:** [ShadCN/UI](https://ui.shadcn.com/) + [TailwindCSS](https://tailwindcss.com/)  

---

## 📊 Consequências

### ✅ Benefícios
- **React:**  
  - Ecossistema consolidado e comunidade madura.  
  - Suporte nativo a **componentização e hooks**.  
  - Fácil integração com bibliotecas externas (ex.: RBAC, charts).  

- **Vite:**  
  - Build **muito rápido** (hot module replacement ágil).  
  - Configuração simples de **proxies** para `/api`, `/catalog` e `/docs`.  
  - Melhor experiência para **desenvolvimento local**.  

- **TypeScript:**  
  - Tipagem estática robusta.  
  - Redução de erros em tempo de desenvolvimento.  
  - Melhor integração com IDEs e CI/CD.  

- **ShadCN/UI + Tailwind:**  
  - UI consistente, acessível e produtiva.  
  - Fácil customização visual.  
  - Padrão moderno e integrado com React.  

### ⚠️ Desafios
- Curva de aprendizado inicial para Vite em times acostumados com Create React App.  
- Necessidade de configurar RBAC no frontend sem depender exclusivamente do backend.  
- Manter catálogo e rotas sincronizados dinamicamente.  

---

## 🔄 Alternativas Consideradas

1. **Angular**  
   - Vantagem: opinionado, integrado.  
   - Desvantagem: curva de aprendizado maior e menor flexibilidade.  

2. **Next.js**  
   - Vantagem: fullstack e SSR pronto.  
   - Desvantagem: sobrecarga desnecessária (SSR não é prioridade no Portal).  

3. **Vue.js + Vite**  
   - Vantagem: simplicidade no binding reativo.  
   - Desvantagem: menor aderência da equipe e ecossistema interno React-first.  

**Motivo da rejeição:** React + Vite + TS oferece o melhor equilíbrio entre **produtividade, performance e alinhamento com a equipe**.  

---

## 📌 Próximos Passos

- Configurar proxies no `vite.config.ts` para `/api`, `/catalog` e `/docs`.  
- Implementar **navbar dinâmica por categorias** (com base no catálogo).  
- Criar helper `userCanSeeBlock(user, block)` para RBAC no frontend.  
- Definir **padrões de UI** (cores, tipografia, grid, acessibilidade).  

---

🔗 **Relacionado a:**  
- [ADR-0001 – Padrão Monorepo](adr-0001-padrao-monorepo.md)  
- [ADR-0002 – BFF FastAPI + Postgres](adr-0002-bff-fastapi-postgres.md)  
