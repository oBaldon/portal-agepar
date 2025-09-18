# Automação: Form2JSON

A automação **Form2JSON** converte formulários enviados pelo usuário em **objetos JSON estruturados**, permitindo reutilização em outras automações ou integrações externas.

---

## 🎯 Objetivo

- Padronizar a **conversão de formulários em JSON**.  
- Permitir exportação de dados em formato estruturado.  
- Facilitar integração com outras etapas do processo (ex.: DFD → PCA → ETP).  

---

## 📌 Endpoints

Base: `/api/automations/form2json/*`

### 🔹 `GET /schema`
- Retorna o schema JSON esperado para submissões.  
- **Exemplo:**
```json
{
  "title": "Form2JSON",
  "type": "object",
  "properties": {
    "form_html": { "type": "string" }
  },
  "required": ["form_html"]
}
````

---

### 🔹 `GET /ui`

* Retorna uma **interface HTML simples** com editor de formulário.
* Exemplo de retorno:

```html
<html>
  <body>
    <h1>Form2JSON</h1>
    <textarea id="form-input" placeholder="Cole aqui o HTML do formulário"></textarea>
    <button>Converter</button>
  </body>
</html>
```

---

### 🔹 `POST /submit`

* Converte um formulário HTML em JSON estruturado.
* **Request exemplo:**

```json
{
  "form_html": "<form><input name='nome'/><input name='idade'/></form>"
}
```

* **Response exemplo:**

```json
{
  "status": "success",
  "submission_id": 55,
  "result": {
    "fields": [
      { "name": "nome", "type": "text" },
      { "name": "idade", "type": "text" }
    ]
  }
}
```

---

### 🔹 `GET /submissions`

* Lista submissões realizadas.
* **Exemplo:**

```json
[
  {
    "id": 55,
    "status": "success",
    "created_at": "2025-09-16T12:00:00Z"
  }
]
```

---

### 🔹 `GET /submissions/{id}`

* Retorna detalhes da submissão.
* **Exemplo:**

```json
{
  "id": 55,
  "status": "success",
  "payload": {
    "form_html": "<form><input name='nome'/></form>"
  },
  "result": {
    "fields": [
      { "name": "nome", "type": "text" }
    ]
  },
  "error": null,
  "created_at": "2025-09-16T12:00:00Z"
}
```

---

### 🔹 `POST /submissions/{id}/download`

* Retorna o JSON convertido como arquivo para download.
* **Exemplo:**

```bash
curl -X POST http://localhost:8000/api/automations/form2json/submissions/55/download -o resultado.json
```

---

## 📊 Persistência

Cada submissão é armazenada em `submissions`:

* `automation_slug = "form2json"`
* `payload` (HTML do formulário)
* `result` (JSON com os campos extraídos)
* `status` (`pending`, `success`, `error`)
* `error` (em caso de falha de parsing)

Eventos de execução são registrados em `audits`.

---

## 📂 Catálogo

Exemplo de entrada no catálogo (`catalog/dev.json`):

```json
{
  "id": "form2json",
  "label": "Form2JSON",
  "categoryId": "gestao",
  "description": "Converte formulários HTML em JSON estruturado",
  "ui": { "type": "iframe", "url": "/api/automations/form2json/ui" },
  "routes": ["/form2json"],
  "navigation": [{ "path": "/form2json", "label": "Form2JSON" }],
  "order": 2
}
```

---

## 🧪 Testes de Exemplo (cURL)

### Submeter formulário

```bash
curl -X POST http://localhost:8000/api/automations/form2json/submit \
  -H "Content-Type: application/json" \
  -d '{"form_html":"<form><input name=\"email\" type=\"email\"/></form>"}'
```

### Listar submissões

```bash
curl http://localhost:8000/api/automations/form2json/submissions
```

### Obter submissão

```bash
curl http://localhost:8000/api/automations/form2json/submissions/55
```

### Baixar JSON

```bash
curl -X POST http://localhost:8000/api/automations/form2json/submissions/55/download -o resultado.json
```

---

## 🚀 Futuro

* Suporte a **tipos avançados de campos** (select, checkbox, radio).
* Mapeamento de **valores padrão** e validações.
* Integração com outras automações para encadeamento de processos.
