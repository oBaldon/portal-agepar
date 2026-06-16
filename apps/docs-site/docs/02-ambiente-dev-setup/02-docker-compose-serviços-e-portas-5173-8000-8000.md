---
id: docker-compose-serviços-e-portas-5173-8000-8000
title: "Docker Compose: serviços, portas e composição correta"
sidebar_position: 2
---

> O nome do arquivo foi mantido por compatibilidade. O conteúdo foi atualizado.

## Arquivos de compose

### `infra/docker-compose.dev.yml`
Define:
- `bff`
- `host`
- `docs`

### `infra/docker-compose.pg.yml`
Define:
- `postgres`
- override de `DATABASE_URL` no `bff`

## Forma recomendada de subir

```bash
./infra/scripts/dev.sh up
```

## Forma equivalente, explícita

```bash
docker compose   --env-file .env   -f infra/docker-compose.dev.yml   -f infra/docker-compose.pg.yml   up -d --build
```

## Portas

- Host: `5173`
- BFF: `8000`
- Docs direto: `9000`
- Postgres: `5432` por default

## DNS interno entre containers

- `host` fala com `bff` em `http://bff:8000`
- `host` fala com `docs` em `http://docs:8000`
- `bff` fala com o banco em `postgres:5432`

## Divergência importante do estado atual

O compose base ainda injeta `AUTH_MODE: mock`, mas `apps/bff/run_dev.sh` tem
default `AUTH_MODE=local`. Essa diferença afeta login, troubleshooting e testes.
