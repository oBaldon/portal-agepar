---
id: subir-com-docker-compose
title: "Subir com Docker Compose"
sidebar_position: 1
---

## Comando recomendado

Na raiz do projeto:

```bash
./infra/scripts/dev.sh up
```

## Comando compose explícito

```bash
docker compose   --env-file .env   -f infra/docker-compose.dev.yml   -f infra/docker-compose.pg.yml   up -d --build
```

## O que sobe

- Host em `http://localhost:5173`
- BFF em `http://localhost:8000`
- Docs em `http://localhost:5173/devdocs/`
- Postgres em `localhost:5432`

## Checks rápidos

```bash
curl -i http://localhost:8000/health
curl -s http://localhost:8000/version | jq .
curl -s http://localhost:8000/catalog/dev | jq .
curl -i http://localhost:5173/devdocs/
```

## Importante

A documentação antiga sugeria subir apenas `docker-compose.dev.yml`. Hoje isso
não cobre o banco nem injeta `DATABASE_URL` no BFF.
