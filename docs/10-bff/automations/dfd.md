# Automação: DFD (Documento de Formalização da Demanda)

A automação **DFD** auxilia na elaboração do **Documento de Formalização da Demanda**, etapa inicial do processo de compras públicas.

---

## 🎯 Objetivo

- Padronizar a coleta de informações para criação do **DFD**.  
- Reduzir retrabalho e inconsistências nos documentos.  
- Automatizar a geração de arquivos finais (ex.: `.docx`).  

---

## 📌 Endpoints

Base: `/api/automations/dfd/*`

### 🔹 `GET /schema`
- Retorna o schema JSON esperado para submissões.  
- **Exemplo:**
```json
{
  "title": "DFD",
  "type": "object",
  "properties": {
    "ano": { "type": "integer" },
    "orgao": { "type": "string" },
    "responsavel": { "type": "string" },
    "justificativa": { "type": "string" }
  },
  "required": ["ano", "orgao", "responsavel"]
}
````

---

### 🔹 `GET /ui`

* Retorna uma **interface simples em HTML** (renderizada em iframe no frontend).
* Exemplo de retorno:

```html
<html>
  <body>
    <h1>DFD - Documento de Formalização da Demanda</h1>
    <form id="dfd-form"> ... </form>
  </body>
</html>
```

---

### 🔹 `POST /submit`

* Cria uma nova submissão de DFD.
* **Request exemplo:**

```json
{
  "ano": 2025,
  "orgao": "Secretaria de Administração",
  "responsavel": "Maria Oliveira",
  "justificativa": "Necessidade de contratação de serviços de TI"
}
```

* **Response exemplo:**

```json
{
  "status": "success",
  "submission_id": 101,
  "message": "Submissão registrada com sucesso"
}
```

---

### 🔹 `GET /submissions`

* Lista submissões do DFD.
* **Exemplo:**

```json
[
  {
    "id": 101,
    "status": "processing",
    "created_at": "2025-09-16T10:00:00Z"
  }
]
```

---

### 🔹 `GET /submissions/{id}`

* Detalha uma submissão.
* **Exemplo:**

```json
{
  "id": 101,
  "status": "success",
  "payload": {
    "ano": 2025,
    "orgao": "Secretaria de Administração",
    "responsavel": "Maria Oliveira"
  },
  "result": {
    "arquivo": "dfd-2025.docx"
  },
  "error": null,
  "created_at": "2025-09-16T10:00:00Z"
}
```

---

### 🔹 `POST /submissions/{id}/download`

* Retorna o arquivo final gerado (ex.: `.docx`).
* **Exemplo:**

```bash
curl -X POST http://localhost:8000/api/automations/dfd/submissions/101/download -o dfd.docx
```

---

## 📊 Persistência

Cada submissão é registrada na tabela `submissions`:

* `automation_slug = "dfd"`
* `payload` (JSON com dados do DFD)
* `status` (`pending`, `processing`, `success`, `error`)
* `result` (JSON com metadados, ex.: caminho do arquivo)
* `error` (texto se falha)

Eventos são auditados em `audits`.

---

## 📂 Catálogo

Exemplo de entrada no catálogo (`catalog/dev.json`):

```json
{
  "id": "dfd",
  "label": "DFD",
  "categoryId": "compras",
  "description": "Documento de Formalização da Demanda",
  "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" },
  "routes": ["/dfd"],
  "navigation": [{ "path": "/dfd", "label": "DFD" }],
  "requiredRoles": ["admin", "compras"],
  "order": 1
}
```

---

## 🧪 Testes de Exemplo (cURL)

### Criar submissão

```bash
curl -X POST http://localhost:8000/api/automations/dfd/submit \
  -H "Content-Type: application/json" \
  -d '{"ano":2025,"orgao":"Secretaria de Administração","responsavel":"Maria Oliveira","justificativa":"Necessidade de contratação de serviços de TI"}'
```

### Listar submissões

```bash
curl http://localhost:8000/api/automations/dfd/submissions
```

### Obter submissão

```bash
curl http://localhost:8000/api/automations/dfd/submissions/101
```

### Baixar arquivo

```bash
curl -X POST http://localhost:8000/api/automations/dfd/submissions/101/download -o dfd.docx
```

---

## 🚀 Futuro

* Validações adicionais de campos (datas, justificativas mínimas).
* Geração de diferentes formatos (`.pdf`, `.odt`).
* Integração com sistemas externos de gestão de compras.

