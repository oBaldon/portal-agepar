# Automações no BFF

As **automações** são módulos independentes do **BFF (FastAPI)** que implementam fluxos específicos do processo de compras públicas.  
Cada automação possui **endpoints padronizados** e uma **UI HTML simples** renderizada em iframe pelo frontend.

---

## 🎯 Conceito

- Cada automação é um **módulo isolado** em `apps/bff/app/automations/{slug}.py`.  
- O **frontend** consome o catálogo e abre a automação em **iframe**.  
- O **backend** valida entradas, persiste submissões e audita eventos.  
- O **padrão de endpoints** garante consistência em todas as automações.  

---

## 📌 Endpoints Padrão

Cada automação `{slug}` expõe:

| Método | Endpoint | Descrição |
|--------|----------|------------|
| `GET`  | `/api/automations/{slug}/schema` | (Opcional) Retorna schema JSON esperado |
| `GET`  | `/api/automations/{slug}/ui` | Retorna UI HTML simples para iframe |
| `POST` | `/api/automations/{slug}/submit` | Cria submissão e dispara processamento |
| `GET`  | `/api/automations/{slug}/submissions` | Lista submissões existentes |
| `GET`  | `/api/automations/{slug}/submissions/{id}` | Consulta submissão específica |
| `POST` | `/api/automations/{slug}/submissions/{id}/download` | Retorna resultado (arquivo/JSON) |

---

## 📊 Estrutura de Submissão

Todas as submissões seguem o mesmo modelo de persistência na tabela `submissions`:

| Campo          | Tipo     | Descrição |
|----------------|----------|------------|
| `id`           | int      | Identificador único |
| `automation_slug` | string | Identificador da automação (`dfd`, `form2json`, etc.) |
| `payload`      | json     | Dados enviados pelo usuário |
| `status`       | string   | `pending`, `processing`, `success`, `error` |
| `result`       | json     | Resultado da automação (ex.: link de arquivo) |
| `error`        | string   | Mensagem de erro (se houver) |
| `created_at`   | datetime | Data de criação |
| `updated_at`   | datetime | Última atualização |

---

## 📂 Catálogo

Cada automação deve ser registrada no **catálogo** (`catalog/dev.json` ou `catalog/prod.json`).  

Exemplo:
```json
{
  "id": "dfd",
  "label": "DFD",
  "categoryId": "compras",
  "description": "Documento de Formalização da Demanda",
  "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" },
  "routes": ["/dfd"],
  "navigation": [{ "path": "/dfd", "label": "DFD" }],
  "requiredRoles": ["compras"]
}
````

---

## 🚀 Automações Disponíveis

* [DFD – Documento de Formalização da Demanda](dfd.md)
* [Form2JSON – Conversão de formulários em JSON](form2json.md)

---

## 🧪 Teste Rápido (cURL)

### Criar submissão

```bash
curl -X POST http://localhost:8000/api/automations/{slug}/submit \
  -H "Content-Type: application/json" \
  -d '{ "campo": "valor" }'
```

### Obter submissão

```bash
curl http://localhost:8000/api/automations/{slug}/submissions/1
```

### Baixar resultado

```bash
curl -X POST http://localhost:8000/api/automations/{slug}/submissions/1/download -o resultado.out
```

---

## 🏗️ Futuro

* Automações adicionais: **PCA, ETP, TR, Cotação/Dispensa, Contrato, Execução**.
* Padronização de schemas JSON para **validação automática**.
* Orquestração de automações em **fluxo sequencial**.

