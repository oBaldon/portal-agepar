# Operações – Backups e Retenção

Este documento define as políticas e procedimentos de **backup** e **retenção de dados** do Portal AGEPAR.

---

## 🎯 Objetivos

- Garantir que dados críticos (submissões, auditorias, sessões) nunca sejam perdidos.  
- Implementar rotina de **backup automatizado** com retenção adequada.  
- Assegurar capacidade de **restauração rápida** em caso de falha ou incidente.  

---

## 🗄️ Escopo

- Banco de dados **PostgreSQL** (produção e homolog).  
- Arquivos estáticos relevantes (se existirem no futuro).  
- Configurações críticas (`.env`, certificados TLS, scripts de migração).  

---

## ♻️ Política de Retenção

- **Backups completos**: diários.  
- **Retenção**: 30 dias em armazenamento de baixo custo (S3/Blob Storage).  
- **Backups semanais**: retidos por 3 meses.  
- **Backups mensais**: retidos por 1 ano.  
- **Pontos de restauração**: disponíveis via snapshots no provedor de cloud.  

---

## 🔧 Estratégia Técnica

### Dump Lógico (pg_dump)

- Usado para **migrações** ou cópia para dev/homolog.  
- Arquivo `.sql` versionado fora do repositório (armazenado em storage seguro).  

```bash
pg_dump -h db-prod -U agepar_user agepar > backup-$(date +%F).sql
````

### Backup Físico (base + WAL)

* Usado para **recuperação rápida** e **point-in-time recovery (PITR)**.
* Executado com ferramentas como `pg_basebackup` ou `wal-g`.

---

## 🚀 Automação (Exemplo com cron + pg\_dump)

```bash
#!/bin/bash
set -e
DATE=$(date +%F_%H-%M)
pg_dump -h db-prod -U agepar_user agepar | gzip > /backups/db-$DATE.sql.gz

# Enviar para storage S3
aws s3 cp /backups/db-$DATE.sql.gz s3://agepar-backups/prod/
```

Agendamento no crontab:

```
0 2 * * * /infra/scripts/backup.sh
```

---

## 🔎 Restauração

### Restaurar dump lógico

```bash
psql -h db-prod -U agepar_user -d agepar < backup-2023-09-01.sql
```

### Restaurar PITR (WAL)

1. Restaurar backup base (`pg_basebackup`).
2. Reaplicar logs (`restore_command` no `postgresql.conf`).
3. Subir instância até o ponto desejado.

---

## 🛡️ Segurança

* Criptografar backups (AES256 ou SSE-KMS em S3).
* Restringir acesso a buckets de backup (somente equipe infra).
* Monitorar tamanho dos backups → alertas em caso de crescimento anormal.

---

## 🧪 Testes de Restauração

* Devem ser realizados **mensalmente** em ambiente de homolog.
* Checklist:

  * Importar backup → validar consistência.
  * Rodar smoke tests (`/api/health`, `/catalog/prod`).
  * Comparar com métricas do ambiente de origem.

---

## 🔮 Futuro

* Implementar **wal-g** para retenção otimizada e PITR granular.
* Automação de restore em pipelines de DR (Disaster Recovery).
* Replicação assíncrona multi-região para maior resiliência.