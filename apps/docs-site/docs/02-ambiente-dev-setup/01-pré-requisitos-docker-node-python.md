---
id: pré-requisitos-docker-node-python
title: "Pré-requisitos (Docker, Node, Python)"
sidebar_position: 1
---

_Criado em 2025-10-27 13:48:02_

Esta página lista os **pré‑requisitos** para rodar o ambiente de desenvolvimento da Plataforma AGEPAR com estabilidade e performance.

> Requisitos mínimos recomendados: **Docker 24+**, **Docker Compose v2+**, **Node.js 18+** (com **pnpm**), **Python 3.11+**.

## Sistemas suportados

- **Windows 11/10** (com **WSL2** habilitado — recomendado)
- **macOS** (Intel/Apple Silicon)
- **Linux** (Debian/Ubuntu/Fedora/Arch e derivados)

---

## 1) Docker & Docker Compose

### Instalação
- **Windows/macOS**: instale **Docker Desktop** (inclui Compose v2).  
- **Linux**: instale `docker` e `docker compose` via repo oficial da sua distro.

### Verificação rápida
```bash
docker --version
docker compose version
docker run --rm hello-world
```

### Ajustes recomendados
- Alocar **CPU/RAM** suficientes no Docker Desktop (ex.: 4 CPUs / 6–8 GB RAM).
- Mapear um diretório de código **no sistema de arquivos local** (no Windows, usar `/home/<user>/...` dentro do WSL2 melhora MUITO a performance).

---

## 2) Node.js (18+) e pnpm

### Instalação
- **nvm** (multiplataforma): recomendado para gerenciar versões
```bash
# Linux/macOS
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
# feche e reabra o shell, então:
nvm install 18
nvm use 18
```

- **pnpm** (gerenciador recomendado)
```bash
npm i -g pnpm
pnpm --version
```

### Verificação rápida
```bash
node -v
pnpm -v
```

> O Host (Vite/React) usa Node durante o desenvolvimento; em produção ele é servido já **buildado**.

---

## 3) Python 3.11+

### Instalação
- **Linux**: use o gerenciador da distro (ou `pyenv`).
- **macOS**: `brew install python@3.11`
- **Windows**: Microsoft Store ou `pyenv-win` (preferir WSL2 para dev).

### Ambiente virtual e dependências
```bash
# dentro do diretório apps/bff (exemplo)
python -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate   # Windows (PowerShell/cmd)
pip install -r requirements.txt
python -V
```

> Para rodar o BFF localmente (fora do Docker): `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

---

## 4) Utilitários úteis (opcional, mas recomendados)

```bash
# CLI
curl --version
jq --version

# Git
git --version
```

No Windows, use **Windows Terminal** + **WSL2 (Ubuntu)** para melhor compatibilidade.

---

## 5) Smoke tests do ambiente

Depois de instalar tudo, valide com:

```bash
# Docker OK?
docker run --rm hello-world

# Node/pnpm OK?
node -v && pnpm -v

# Python OK?
python -V
```

Se já estiver com o projeto clonado, você deve conseguir subir tudo com:
```bash
docker compose up --build
```

---

## Problemas comuns

- **Docker lento no Windows**  
  Use o projeto dentro do **sistema de arquivos do WSL2** (ex.: `/home/<user>/repo`) e não em `C:\Users\...`.

- **Portas em uso (5173/8000)**  
  Finalize processos em conflito ou ajuste as portas no `docker-compose`/Vite/uvicorn.

- **CORS ou sessão não funcionando**  
  Confirme origens liberadas no BFF e que os **proxies do Vite** estão apontando para `http://localhost:8000` (ver página _Proxies do Vite_).

- **Erro 422 (Pydantic)**  
  Normalize os campos de entrada e garanta `extra="ignore"` e `populate_by_name=True` nos modelos.

---

## Próximos passos

- Siga para **[Ambiente Dev — Setup](./index)** para subir e testar.  
- Veja **[Proxies do Vite](./02-proxies-do-vite)** para o roteamento durante o desenvolvimento.  
- Consulte **Troubleshooting** para erros frequentes.

---

_Criado em 2025-10-27 13:48:02_