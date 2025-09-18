# Referência – Changelog

Este documento mantém o **histórico de mudanças técnicas** do Portal AGEPAR.  
Serve como registro para desenvolvedores, DevOps e operações.

---

## 📌 Formato

- **Versão** segue **SemVer** (`MAJOR.MINOR.PATCH`).  
- Cada release deve incluir:
  - 🔧 **Added** → novas features.  
  - 🛠️ **Changed** → alterações de comportamento.  
  - 🐞 **Fixed** → correções de bugs.  
  - 🔐 **Security** → patches críticos de segurança.  

---

## 🕒 Histórico de Releases

### [1.0.0] – 2025-09-01
- 🔧 Primeira versão estável do Portal AGEPAR.  
- Added:  
  - Estrutura monorepo com **BFF (FastAPI)**, **Host (React+Vite)**, **Docs (MkDocs)**.  
  - Catálogo dinâmico (`/catalog/dev`, `/catalog/prod`).  
  - Automações iniciais: **DFD**, **Form2JSON**.  
  - RBAC simples no BFF e no Host.  
- Security:  
  - Cookies `HttpOnly` e `SameSite=Strict`.  
  - CORS restrito.  

---

### [0.3.0] – 2025-08-20
- Added:  
  - Integração de **observabilidade** (Prometheus + Grafana).  
  - Runbooks iniciais (BFF, DB, Host).  
- Changed:  
  - Catálogo agora respeita `order` explícito.  
- Fixed:  
  - Corrigido bug de sessão inválida em múltiplos logins.  

---

### [0.2.0] – 2025-08-05
- Added:  
  - Estrutura inicial de **CI/CD** com Docker Compose.  
  - Testes unitários no backend com Pytest.  
  - Proxies do Host para `/api`, `/catalog`, `/docs`.  

---

### [0.1.0] – 2025-07-15
- Added:  
  - Protótipo inicial do BFF com endpoints de auth (`/login`, `/me`).  
  - Protótipo inicial do Host com React/Vite.  
  - MkDocs para documentação básica.  

---

## 🔮 Futuro

- Publicar changelog no **repositório oficial** com tag/release do GitHub.  
- Automatizar geração via [git-chglog](https://github.com/git-chglog/git-chglog) ou [changesets](https://github.com/changesets/changesets).  
- Associar PRs e issues automaticamente ao changelog.  
