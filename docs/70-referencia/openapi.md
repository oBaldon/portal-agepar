# Referência – OpenAPI

O BFF do Portal AGEPAR expõe sua especificação **OpenAPI 3.1** de forma automática via **FastAPI**.  
Este documento descreve como acessar, usar e validar o contrato da API.

---

## 🎯 Objetivos

- Fornecer documentação **interativa** dos endpoints.  
- Servir de contrato entre **backend** e **frontend**.  
- Facilitar geração de **SDKs** e integração externa.  

---

## 📍 Endpoints Disponíveis

- **Swagger UI**  
```

[http://localhost:8000/docs](http://localhost:8000/docs)

```
ou via proxy do Host:  
```

[http://localhost:5173/api/docs](http://localhost:5173/api/docs)

```

- **Redoc**  
```

[http://localhost:8000/redoc](http://localhost:8000/redoc)

```

- **Esquema bruto (JSON)**  
```

[http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

````

---

## 📦 Exemplo de Trecho do Esquema

```json
{
"openapi": "3.1.0",
"info": {
  "title": "Portal AGEPAR API",
  "version": "1.0.0"
},
"paths": {
  "/api/health": {
    "get": {
      "summary": "Health Check",
      "responses": {
        "200": {
          "description": "OK",
          "content": {
            "application/json": {
              "example": { "status": "ok" }
            }
          }
        }
      }
    }
  }
}
}
````

---

## 🛠️ Geração de SDKs

É possível gerar SDKs automaticamente a partir do **OpenAPI**:

### Python (httpx + pydantic)

```bash
openapi-python-client generate --url http://localhost:8000/openapi.json
```

### TypeScript (axios/fetch)

```bash
openapi-typescript http://localhost:8000/openapi.json -o sdk.ts
```

---

## 🧪 Validação

* O arquivo `openapi.json` deve ser válido segundo o schema oficial:

  ```bash
  curl -s http://localhost:8000/openapi.json | jq .openapi
  ```
* CI/CD pode incluir validação com [spectral](https://stoplight.io/open-source/spectral/):

  ```bash
  npx @stoplight/spectral-cli lint openapi.json
  ```

---

## 🔮 Futuro

* Adicionar exemplos detalhados de request/response no schema.
* Expandir com **tags por automação** (DFD, Form2JSON, etc.).
* Publicar OpenAPI em portal corporativo de APIs.