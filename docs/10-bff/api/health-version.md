# API – Health & Version

O **BFF (FastAPI)** do Portal AGEPAR expõe endpoints básicos para **monitoramento** e **identificação da versão** em execução.  
Esses endpoints são usados em **health checks**, pipelines de CI/CD e monitoração de produção.

---

## 📌 Endpoints

### 🔹 `GET /api/health`
- **Descrição:** Verifica se a aplicação está respondendo corretamente.  
- **Status esperado:** `200 OK`  
- **Resposta:**
```json
{
  "status": "ok",
  "timestamp": "2025-09-16T12:30:45Z"
}
````

---

### 🔹 `GET /api/version`

* **Descrição:** Retorna a versão atual do BFF em execução.
* **Fonte:** A versão é extraída do pacote ou de uma variável `APP_VERSION`.
* **Status esperado:** `200 OK`
* **Resposta:**

```json
{
  "version": "1.0.0",
  "commit": "abc123",
  "build_date": "2025-09-16T11:00:00Z"
}
```

---

## 🧪 Testes de Exemplo

### Health Check

```bash
curl -i http://localhost:8000/api/health
```

### Version

```bash
curl -i http://localhost:8000/api/version
```

---

## 📊 Uso em Infraestrutura

* **Docker Compose:** health check automático no container `bff`.
* **CI/CD:** valida se a aplicação sobe corretamente após build.
* **Kubernetes (futuro):** pode ser usado em `livenessProbe` e `readinessProbe`.

---

## 🚀 Próximos Passos

* [Catalog API](catalog.md)
* [Automations API](automations.md)
* [Auth API](auth.md)
