# API – Automations

As **automações** do Portal AGEPAR são implementadas como **módulos isolados** no BFF (FastAPI).  
Cada automação expõe endpoints padronizados para **UI, schema, submissão e auditoria**.

---

## 📌 Estrutura dos Endpoints

Cada automação é acessível em:  

```

/api/automations/{slug}/...

````

Onde `{slug}` é o identificador único da automação (ex.: `dfd`, `form2json`).  

---

## 📂 Endpoints Padrão

### 🔹 `GET /api/automations/{slug}/schema`
- **Descrição:** Retorna o schema da automação em JSON (opcional).  
- **Uso:** Permite validar payloads no frontend ou documentar campos esperados.  
- **Resposta Exemplo:**
```json
{
  "title": "DFD",
  "type": "object",
  "properties": {
    "ano": { "type": "integer" },
    "orgao": { "type": "string" }
  },
  "required": ["ano", "orgao"]
}
````

---

### 🔹 `GET /api/automations/{slug}/ui`

* **Descrição:** Retorna uma interface simples em HTML/JS/CSS (sem build).
* **Uso:** O frontend renderiza em `<iframe>`.
* **Resposta Exemplo:**

```html
<html>
  <body>
    <h1>Formulário DFD</h1>
    <form id="dfd-form"> ... </form>
  </body>
</html>
```

---

### 🔹 `POST /api/automations/{slug}/submit`

* **Descrição:** Cria uma nova submissão da automação.
* **Ações:**

  * Persiste payload na tabela `submissions`.
  * Dispara execução assíncrona (via `BackgroundTasks`).
  * Registra auditoria em `audits`.
* **Request Exemplo:**

```json
{
  "ano": 2025,
  "orgao": "Secretaria de Administração"
}
```

* **Resposta Exemplo:**

```json
{
  "status": "success",
  "submission_id": 42,
  "message": "Submissão criada com sucesso"
}
```

---

### 🔹 `GET /api/automations/{slug}/submissions`

* **Descrição:** Lista todas as submissões de uma automação.
* **Resposta Exemplo:**

```json
[
  {
    "id": 42,
    "status": "processing",
    "created_at": "2025-09-16T10:00:00Z"
  }
]
```

---

### 🔹 `GET /api/automations/{slug}/submissions/{id}`

* **Descrição:** Retorna os detalhes de uma submissão específica.
* **Resposta Exemplo:**

```json
{
  "id": 42,
  "status": "success",
  "payload": { "ano": 2025, "orgao": "Secretaria de Administração" },
  "result": { "arquivo": "dfd-2025.docx" },
  "error": null,
  "created_at": "2025-09-16T10:00:00Z"
}
```

---

### 🔹 `POST /api/automations/{slug}/submissions/{id}/download`

* **Descrição:** Disponibiliza o resultado de uma submissão (ex.: arquivo gerado).
* **Resposta:** Retorna o conteúdo em **streaming** (PDF, DOCX, JSON, etc.).

---

## 🗄️ Persistência

Todas as submissões são gravadas na tabela `submissions`, com colunas:

* `id`
* `automation_slug`
* `payload` (JSON)
* `status` (`pending`, `processing`, `success`, `error`)
* `result` (JSON ou nulo)
* `error` (texto ou nulo)
* `created_at`, `updated_at`

Auditoria registrada em `audits`.

---

## 🧪 Testes de Exemplo

### Submeter automação (DFD)

```bash
curl -X POST http://localhost:8000/api/automations/dfd/submit \
  -H "Content-Type: application/json" \
  -d '{"ano": 2025, "orgao": "Secretaria de Administração"}'
```

### Listar submissões

```bash
curl http://localhost:8000/api/automations/dfd/submissions
```

### Obter submissão específica

```bash
curl http://localhost:8000/api/automations/dfd/submissions/42
```

### Baixar resultado

```bash
curl -X POST http://localhost:8000/api/automations/dfd/submissions/42/download -o resultado.docx
```

---

## 🚀 Próximos Passos

* [Auth API](auth.md)
