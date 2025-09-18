# Operações – Desempenho e Capacidade

Este documento define práticas de **monitoramento de desempenho** e **planejamento de capacidade** para o Portal AGEPAR.

---

## 🎯 Objetivos

- Garantir que o sistema atenda **SLAs de resposta** (< 500ms na maioria das requisições).  
- Monitorar consumo de recursos (CPU, RAM, I/O, conexões DB).  
- Antecipar necessidade de **escalabilidade horizontal/vertical**.  
- Definir **KPIs** e **métricas críticas**.  

---

## 📊 Métricas Principais

### Backend (BFF – FastAPI)
- **Latência**: p95 < 300ms.  
- **Taxa de erro**: < 1% (4xx/5xx).  
- **Throughput**: requisições/segundo.  
- **Pool DB**: conexões ativas e tempo de espera.  

### Frontend (Host – React/Vite)
- **TTFB (Time to First Byte)**: < 200ms em rede padrão.  
- **FCP (First Contentful Paint)**: < 2s.  
- **LCP (Largest Contentful Paint)**: < 3s.  
- **Erros JS** capturados no Sentry/console.  

### Banco (Postgres)
- **Conexões ativas** vs limite (`max_connections`).  
- **Slow queries** (pg_stat_statements).  
- **Tamanho de tabelas** (crescimento).  
- **Locks** e deadlocks.  

---

## 🛠️ Ferramentas de Monitoramento

- **Prometheus + Grafana** → métricas de aplicação e infra.  
- **ELK Stack** (Elasticsearch + Logstash + Kibana) → logs detalhados.  
- **PgBouncer / pg_stat_statements** → tuning de DB.  
- **Sentry** → erros no frontend/backend.  

---

## 📈 Planejamento de Capacidade

- Dimensionar ambiente para **pico esperado x2**.  
- Monitorar:
  - CPU média < 70%.  
  - RAM média < 75%.  
  - Latência de API estável em carga.  
- Executar **testes de carga** trimestrais (Locust, k6).  

---

## 🚦 Alertas

- Latência p95 > 1s (BFF).  
- Erros 5xx > 5% em 5min.  
- Uso de disco > 80%.  
- Fila de submissões atrasada > 10min.  

---

## 🧪 Testes de Performance

Exemplo com **k6**:

```js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 50,
  duration: '30s',
};

export default function () {
  const res = http.get('http://localhost:5173/api/health');
  check(res, { 'status 200': (r) => r.status === 200 });
  sleep(1);
}
````

---

## ♻️ Estratégias de Escalabilidade

* **Horizontal (preferida)**:

  * Várias réplicas de BFF/Host por trás de um load balancer.
  * DB com read replicas para consultas pesadas.

* **Vertical**:

  * Aumentar vCPUs/memória do container/VM.
  * Usado como solução temporária.

---

## 🔮 Futuro

* Auto-scaling no cluster (Kubernetes HPA).
* Testes de caos (Chaos Monkey) para validar resiliência.
* Otimização de queries críticas com índices adicionais.
* CDN para assets estáticos do Host.