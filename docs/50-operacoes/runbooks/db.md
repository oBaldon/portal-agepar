# Runbook – Banco de Dados (PostgreSQL)

Este runbook cobre procedimentos de operação, diagnóstico e recuperação do **banco de dados PostgreSQL** usado pelo Portal AGEPAR.

---

## 🎯 Objetivo

- Fornecer passos para lidar com incidentes relacionados ao banco.  
- Garantir integridade dos dados.  
- Minimizar tempo de indisponibilidade.  

---

## 🛠️ Health Check

- Testar conectividade:

```bash
docker compose exec db pg_isready -U agepar_user -d agepar
````

* Esperado:

  ```
  agepar:5432 - accepting connections
  ```

---

## 📂 Logs

* Local: `/var/lib/postgresql/data/pg_log/` (dentro do container).
* Acessar via:

```bash
docker compose logs db
```

* Em produção: coletados por **Prometheus Postgres Exporter**.

---

## 🚦 Problemas Comuns

### DB não inicializa

1. Verificar variáveis (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`).
2. Apagar volume local em dev:

   ```bash
   docker compose down -v
   docker compose up -d db
   ```

### Conexões recusadas

1. Checar se porta 5432 exposta.
2. Validar `DB_URL` no BFF.
3. Aumentar `max_connections` se atingir limite.

### Query lenta

1. Ativar `pg_stat_statements`.
2. Identificar query com maior tempo.
3. Avaliar criação de índice.

---

## ♻️ Backup & Restore

### Backup manual

```bash
docker compose exec db pg_dump -U agepar_user agepar > backup.sql
```

### Restore manual

```bash
docker compose exec -T db psql -U agepar_user -d agepar < backup.sql
```

> Backups automáticos e retenção estão documentados em [Backups e Retenção](../backups-e-retencao.md).

---

## 🧪 Testes Pós-Restart

* `pg_isready` retorna sucesso.
* `docker compose exec db psql -U agepar_user -c "\dt"` lista tabelas.
* BFF responde `/api/health` sem erro de DB.

---

## 🚨 Escalonamento

* Se dados corrompidos → restaurar último backup válido.
* Se falha persistente em prod → acionar equipe **DBA**.

---

## 🔮 Futuro

* Configurar **replicação assíncrona** para failover.
* Adotar **PgBouncer** como pooler externo.
* Automatizar PITR (Point-In-Time Recovery) com **wal-g**.