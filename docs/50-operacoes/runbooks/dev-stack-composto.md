# Runbook — Stack dev com Postgres (compose composto)

## Por que dois composes?
- `docker-compose.dev.yml` sobe **bff/host/docs**.
- `docker-compose.pg.yml` adiciona **postgres** e faz override no **bff** (injeta `DATABASE_URL` e `depends_on` com `service_healthy`).

> O BFF depende de `DATABASE_URL`. Portanto, **sempre** execute com os **dois** arquivos.

## Requisitos
- Docker Compose v2.
- Arquivo `.env` na raiz (já incluso no repo) com:
```

PGDATABASE=plataforma
PGUSER=plataforma
PGPASSWORD=plataformadev
PGPORT\_MAP=5432

````

## Sobe o stack (dev+pg)
```bash
./infra/scripts/dev_up.sh
````

## Smoke-tests

1. **Postgres**: o container já executa `pg_isready` no healthcheck.
2. **Login mock**:

   ```bash
   curl -i -c cookies.txt -X POST \
     -H "Content-Type: application/json" \
     -d '{"identifier":"dev@exemplo.gov.br","password":"dev"}' \
     http://localhost:8000/api/auth/login
   ```
3. **Sessão**:

   ```bash
   curl -b cookies.txt http://localhost:8000/api/me
   ```
4. **UI DFD**:

   * Abrir `http://localhost:8000/api/automations/dfd/ui` (deve renderizar o iframe no Host via catálogo).
5. **Docs (proxy)**:

   * `http://localhost:5173/docs`

## Derrubar e limpar

```bash
./infra/scripts/dev_down.sh
```

## Logs

```bash
./infra/scripts/dev_logs.sh
```

## Dicas

* Para rodar pg localmente em outra porta: ajuste `PGPORT_MAP` no `.env`.
* Para usar profiles (opcional): execute `docker compose --profile db up` se o `postgres` tiver `profiles: ["db"]` no compose.

