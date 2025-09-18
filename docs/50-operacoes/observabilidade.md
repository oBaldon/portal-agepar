# Operações – Observabilidade

Este documento define a estratégia de **observabilidade** para o Portal AGEPAR, cobrindo **logs**, **métricas** e **tracing**.

---

## 🎯 Objetivos

- Garantir **visibilidade ponta a ponta** do sistema.  
- Ajudar na identificação de **falhas** e **gargalos de performance**.  
- Fornecer dados confiáveis para auditoria e relatórios de capacidade.  

---

## 📚 Pilares da Observabilidade

### 1. Logs
- **Nível INFO**: fluxo normal (ex.: submissão criada).  
- **Nível ERROR**: falhas técnicas (stack trace, contexto).  
- **Nível DEBUG**: usado apenas em dev/homolog.  
- Formato estruturado JSON para parsing via ELK.  

Exemplo (BFF FastAPI):

```python
logger.info("submission_created", extra={"submission_id": sid, "user": user.id})
logger.error("db_failure", exc_info=e, extra={"query": sql})
````

---

### 2. Métricas

* **API**: latência (p50, p95, p99), taxa de erros.
* **DB**: conexões ativas, queries lentas.
* **Host**: métricas Web Vitals (LCP, FID, CLS).
* **Infra**: CPU, RAM, disco.

> Coletadas via **Prometheus** e visualizadas no **Grafana**.

---

### 3. Tracing

* **OpenTelemetry** integrado ao FastAPI e ao React.
* Permite rastrear uma requisição desde o **frontend → BFF → DB**.
* Útil para encontrar gargalos (ex.: API lenta devido a query).

---

## 🛠️ Stack Recomendada

* **Logs**: ELK (Elasticsearch + Logstash + Kibana).
* **Métricas**: Prometheus + Grafana.
* **Tracing**: OpenTelemetry + Jaeger.
* **Alertas**: Prometheus Alertmanager integrado ao MS Teams/Slack.

---

## 🚦 Alertas Operacionais

* Erros 5xx > 5% em 5min.
* Latência p95 > 1s.
* Falha no `/api/health` consecutiva por 3 checks.
* Uso de disco do DB > 80%.

---

## 📊 Dashboards Recomendados

1. **Visão API (BFF)**

   * Latência p50/p95/p99.
   * Throughput.
   * Taxa de erros.

2. **Banco de Dados**

   * Conexões ativas.
   * Queries mais lentas.
   * Crescimento de tabelas.

3. **Frontend (Host)**

   * Web Vitals (LCP, FCP, CLS).
   * Erros capturados no Sentry.

---

## 🧪 Testes de Observabilidade

* Validar se logs são enviados em JSON estruturado.
* Checar se métricas do BFF aparecem no `/metrics`.
* Rodar requisição de teste e verificar trace completo no Jaeger.

---

## 🔮 Futuro

* Correlação automática entre **logs, métricas e traces**.
* Dashboards de **uso de automações** (DFD, Form2JSON, etc.).
* Relatórios mensais de disponibilidade (uptime).
* Monitoramento de custo de cloud (FinOps).