# Runbook – BFF (FastAPI)

Este runbook documenta os procedimentos de operação, diagnóstico e recuperação do **BFF** do Portal AGEPAR.

---

## 🎯 Objetivo

- Fornecer passos claros para lidar com incidentes no **BFF**.  
- Minimizar tempo de indisponibilidade.  
- Garantir rastreabilidade de eventos.  

---

## 🛠️ Health Check

- Endpoint: `GET /api/health`  
- Esperado:  
  ```json
  { "status": "ok" }
````

* Se falhar → investigar logs (`docker compose logs -f bff`).

---

## 📂 Logs

* Local: `stdout` (capturado pelo Docker).
* Níveis: `INFO` (fluxo normal), `ERROR` (falhas técnicas).
* Buscar entradas por `submission_id` para rastrear requisições.

---

## 🗄️ Banco de Dados

* Testar conectividade:

  ```bash
  docker compose exec bff python -c "import sqlalchemy; from app.db import engine; print(engine.connect())"
  ```
* Se falha: verificar serviço `db` e variáveis `DB_URL`.

---

## 🚦 Problemas Comuns

### API fora do ar

1. `docker compose ps` → verificar se container está up.
2. `docker compose logs bff` → checar erros.
3. Se crash loop → revisar `.env` (DB\_URL, SESSION\_SECRET).

### Erros 500 nas automações

1. Revisar logs da automação em `/api/automations/{kind}/submit`.
2. Checar se migrations foram aplicadas:

   ```bash
   docker compose exec bff alembic upgrade head
   ```

### Sessões não funcionam

* Confirmar cookie `agepar_session` presente e válido.
* Verificar `SESSION_SECRET` igual em todos os pods/containers.

---

## ♻️ Restart Seguro

```bash
docker compose restart bff
```

Em Kubernetes (futuro):

```bash
kubectl rollout restart deploy bff
```

---

## 🧪 Testes Pós-Restart

* `curl /api/health` → 200 OK.
* Login/logout funciona (`/api/auth/login`).
* Catálogo disponível em `/catalog/dev`.

---

## 🚨 Escalonamento

* Se problema persistir:

  * Notificar equipe **Infra**.
  * Abrir chamado com logs e horário de incidente.

---

## 🔮 Futuro

* Adicionar readinessProbe/livenessProbe no Kubernetes.
* Dashboards específicos no Grafana para métricas do BFF.