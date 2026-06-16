---
id: pré-requisitos-docker-node-python
title: "Pré-requisitos: Docker, Node e Python"
sidebar_position: 1
---

## Obrigatórios para o fluxo recomendado
- Docker
- Docker Compose v2

## Opcionais para rodar partes fora de container
- Node 20+
- Python 3.11+

## Ferramentas úteis
- `jq` para inspecionar `/version` e o catálogo
- `psql` para checar o banco local
- `curl` para smoke tests

## Observação
O BFF atual não sobe sem `DATABASE_URL`, então rodar “só o app Python” sem banco
não representa mais um cenário suportado pelo código do repositório.
