# Testes – Estratégia de Testes

Este documento descreve a estratégia geral de **testes** aplicada ao Portal AGEPAR, garantindo qualidade em todo o ciclo de vida do software.

---

## 🎯 Objetivos

- Definir níveis de testes e responsabilidades.  
- Cobrir **BFF**, **Host**, **Catálogo** e **infraestrutura**.  
- Integrar testes à **pipeline CI/CD**.  
- Facilitar detecção precoce de regressões.  

---

## 📚 Pirâmide de Testes

1. **Unitários (base)**  
   - Testam funções isoladas.  
   - Ex.: validação Pydantic no BFF, helpers de RBAC no Host.  

2. **Integração**  
   - Testam interação entre componentes.  
   - Ex.: submissão de automação salva no banco e registrada em auditoria.  

3. **End-to-End (E2E)**  
   - Testam fluxo completo do usuário.  
   - Ex.: login → carregar catálogo → abrir automação DFD.  

4. **Testes Manuais**  
   - Fluxos críticos, UX e validação visual.  

---

## 🛠️ Ferramentas

- **BFF (Python/FastAPI)**:  
  - `pytest` para unitários e integração.  
  - `httpx` para simular requisições.  

- **Host (React/Vite/TS)**:  
  - `Vitest` para unitários.  
  - `React Testing Library` para componentes.  
  - `Playwright` para E2E.  

- **Infra**:  
  - `curl` para smoke tests.  
  - `k6` ou `Locust` para carga/performance.  

---

## 📦 Escopo de Testes

- **BFF**  
  - Validação de payloads.  
  - Respostas de erro padronizadas.  
  - Persistência no banco.  
  - RBAC em endpoints.  

- **Host**  
  - Navbar e Home exibem apenas blocos visíveis.  
  - Rotas são geradas corretamente a partir do catálogo.  
  - Sessão e login/logout.  

- **Catálogo**  
  - JSON validado contra schema.  
  - Duplicidade de rotas ou IDs bloqueada.  

- **Docs**  
  - Build MkDocs sem erros.  
  - Links internos válidos.  

---

## 🧪 Integração no CI/CD

Pipeline roda automaticamente em cada PR:  
1. Lint + testes unitários (rápidos).  
2. Testes de integração (containers docker).  
3. Testes de API via `curl` ou Postman CLI.  
4. Validação de catálogo contra JSON Schema.  
5. Build do Host e Docs.  

---

## 🚦 Critérios de Aceite

- **Cobertura mínima**:  
  - Backend unitários: 70%.  
  - Frontend unitários: 60%.  
- **Zero erros críticos** em CI.  
- **Catálogo válido** antes de merge.  

---

## 🔮 Futuro

- Testes de **resiliência** (Chaos Engineering).  
- Testes de **segurança automatizados** (OWASP ZAP).  
- Dashboards de qualidade com métricas de testes (Allure Reports).  
