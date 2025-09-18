# Infra – Pipelines CI/CD

Este documento descreve a estratégia de **CI/CD** do Portal AGEPAR, incluindo validações, builds e deploys em múltiplos ambientes.

---

## 🎯 Objetivos

- Garantir **qualidade** de código e catálogos via pipelines automáticos.  
- Entregar artefatos (imagens Docker, pacotes estáticos).  
- Automatizar deploy em **homologação** e **produção**.  
- Fornecer rollback rápido em caso de falha.  

---

## 🏗️ Estrutura de Pipeline

### Estágios principais

1. **Lint & Test**  
   - Rodar linters (ESLint, Ruff, etc.).  
   - Rodar testes unitários e de integração (Vitest, Pytest).  

2. **Build & Validate**  
   - Build do BFF (FastAPI) em container.  
   - Build do Host (React + Vite).  
   - Build do Docs (MkDocs).  
   - Validar catálogos com JSON Schema.  

3. **Publish**  
   - Publicar imagens no **Registry** (GHCR, ECR, etc.).  
   - Versionamento semântico ou `git sha`.  

4. **Deploy**  
   - Homologação: automático a cada push na `main`.  
   - Produção: manual (`workflow_dispatch` / approval gate).  
   - Rodar migrations (Alembic) como job separado.  

---

## 📦 Exemplo (GitHub Actions)

```yaml
name: CI/CD Portal AGEPAR

on:
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "main" ]
  workflow_dispatch:

jobs:
  lint-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v3
        with: { node-version: 18 }
      - uses: actions/setup-python@v4
        with: { python-version: 3.11 }
      - run: npm ci --prefix apps/host
      - run: npm test --prefix apps/host
      - run: pip install -r apps/bff/requirements.txt
      - run: pytest apps/bff

  build-validate:
    runs-on: ubuntu-latest
    needs: lint-test
    steps:
      - uses: actions/checkout@v4
      - run: docker compose build
      - run: node scripts/validate-catalog.js catalog/dev.json

  publish:
    runs-on: ubuntu-latest
    needs: build-validate
    steps:
      - uses: actions/checkout@v4
      - name: Log in to GHCR
        uses: docker/login-action@v2
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - run: docker compose push

  deploy-homolog:
    runs-on: ubuntu-latest
    needs: publish
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - run: ssh deploy@homolog "cd portal-agepar && docker compose pull && docker compose up -d"

  deploy-prod:
    runs-on: ubuntu-latest
    needs: publish
    if: github.event_name == 'workflow_dispatch'
    steps:
      - uses: actions/checkout@v4
      - run: ssh deploy@prod "cd portal-agepar && docker compose pull && docker compose up -d"
````

---

## 🔐 Segurança

* Segredos armazenados no **GitHub Secrets** / Vault.
* Deploy via **chaves SSH** com usuário restrito.
* CI nunca expõe `SESSION_SECRET` ou credenciais do banco.

---

## 🧪 Validações Obrigatórias

* Lint (TS, Python).
* Testes unitários (Pytest, Vitest).
* Testes de API (`curl` ou Postman CLI).
* Validação do **catálogo JSON**.

---

## ♻️ Rollback

* **Homologação**: redeploy da versão anterior (`docker compose up -d image:tag`).
* **Produção**:

  * Imagens versionadas permitem rollback rápido.
  * Banco de dados exige rollback via restore de backup → runbook em `docs/50-operacoes/backups-e-retencao.md`.

---

## 🔮 Futuro

* Adicionar **canary releases** para novas automações.
* Telemetria integrada: métricas de pipeline (tempo, falhas).
* Deploy com **ArgoCD** ou **FluxCD** para GitOps.