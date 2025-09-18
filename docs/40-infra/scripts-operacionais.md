# Infra – Scripts Operacionais

Este documento reúne **scripts utilitários** e **comandos operacionais** usados no ciclo de vida do Portal AGEPAR.  
Eles auxiliam em tarefas de **setup local**, **deploy**, **migrations**, **backup** e **manutenção**.

---

## 🎯 Objetivos

- Padronizar operações comuns entre dev, homolog e prod.  
- Evitar execução manual de comandos perigosos.  
- Garantir repetibilidade (scripts versionados no repo).  

---

## 🖥️ Scripts Locais (Dev)

### Subir ambiente completo

```bash
docker compose up --build
````

### Derrubar ambiente

```bash
docker compose down -v
```

### Rebuild apenas do Host

```bash
docker compose up -d --build host
```

### Logs em tempo real

```bash
docker compose logs -f bff
docker compose logs -f host
docker compose logs -f docs
```

---

## 🗄️ Banco de Dados

### Executar migrações (Alembic)

```bash
docker compose exec bff alembic upgrade head
```

### Criar nova migration

```bash
docker compose exec bff alembic revision --autogenerate -m "nova tabela"
```

### Acessar psql

```bash
docker compose exec db psql -U agepar_user -d agepar
```

---

## ♻️ Backup & Restore

### Dump completo

```bash
docker compose exec db pg_dump -U agepar_user agepar > backup.sql
```

### Restore

```bash
docker compose exec -T db psql -U agepar_user -d agepar < backup.sql
```

---

## 🚀 Deploy Manual (Homolog/Prod)

> Apenas em caso de fallback quando CI/CD indisponível.

```bash
ssh deploy@homolog "cd portal-agepar && git pull && docker compose pull && docker compose up -d"
```

---

## 🔎 Diagnóstico Rápido

### Testar saúde da API

```bash
curl -i http://localhost:5173/api/health
```

### Testar catálogo

```bash
curl -s http://localhost:5173/catalog/dev | jq .
```

### Testar docs

```bash
curl -I http://localhost:5173/docs/
```

---

## 🛡️ Boas Práticas

* Nunca rodar migrations direto em **prod** sem revisão.
* Validar catálogo com script antes de subir:

```bash
node scripts/validate-catalog.js catalog/prod.json
```

* Sempre versionar scripts em `infra/scripts/` para rastreabilidade.

---

## 📂 Estrutura Recomendada

```
infra/
 ├── scripts/
 │    ├── validate-catalog.js
 │    ├── backup.sh
 │    ├── restore.sh
 │    ├── migrate.sh
 │    └── deploy.sh
 └── ...
```

---

## 🔮 Futuro

* Automatizar execuções via **Makefile** (`make up`, `make migrate`, etc.).
* Integrar scripts ao **CI/CD** (ex.: backup automatizado antes de deploy).
* Substituir scripts bash por CLI própria (`ageparctl`).