# Guia para Criar Nova Automação

Este guia descreve o processo padrão para adicionar uma **nova automação** ao BFF (FastAPI) e integrá-la ao **catálogo** e ao **frontend (Host)**.

---

## 🎯 Objetivos

- Garantir **padronização** entre todas as automações.  
- Facilitar manutenção e extensibilidade.  
- Evitar duplicação de código.  
- Garantir **testes, documentação e auditoria** desde o início.  

---

## 📂 Estrutura

Cada automação é implementada como um módulo isolado em:

```

apps/bff/app/automations/{slug}.py

````

Onde `{slug}` é o identificador único da automação (ex.: `dfd`, `form2json`).  

---

## 📌 Endpoints Obrigatórios

Cada automação deve expor os seguintes endpoints:

| Método | Rota | Obrigatório | Descrição |
|--------|------|-------------|------------|
| `GET`  | `/api/automations/{slug}/schema` | Opcional | Retorna schema JSON esperado |
| `GET`  | `/api/automations/{slug}/ui` | ✅ | Retorna UI HTML simples (iframe) |
| `POST` | `/api/automations/{slug}/submit` | ✅ | Cria submissão e inicia execução |
| `GET`  | `/api/automations/{slug}/submissions` | ✅ | Lista submissões da automação |
| `GET`  | `/api/automations/{slug}/submissions/{id}` | ✅ | Detalha submissão específica |
| `POST` | `/api/automations/{slug}/submissions/{id}/download` | ✅ | Retorna resultado (arquivo/JSON) |

---

## 🧩 Exemplo de Automação (`exemplo.py`)

```python
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from ..db import save_submission, get_submission, list_submissions

router = APIRouter(prefix="/api/automations/exemplo", tags=["automations"])

class ExemploPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    nome: str
    idade: int

@router.get("/schema")
def get_schema():
    return ExemploPayload.model_json_schema()

@router.get("/ui")
def get_ui():
    return """
    <html>
      <body>
        <h1>Exemplo Automação</h1>
        <form id="form"> ... </form>
      </body>
    </html>
    """

@router.post("/submit")
def submit(data: ExemploPayload, background: BackgroundTasks):
    submission_id = save_submission("exemplo", data.model_dump())
    background.add_task(process_submission, submission_id)
    return {"status": "success", "submission_id": submission_id}

@router.get("/submissions")
def submissions():
    return list_submissions("exemplo")

@router.get("/submissions/{id}")
def submission_detail(id: int):
    submission = get_submission(id)
    if not submission:
        raise HTTPException(404, "Submissão não encontrada")
    return submission

@router.post("/submissions/{id}/download")
def download(id: int):
    submission = get_submission(id)
    if not submission:
        raise HTTPException(404, "Submissão não encontrada")
    return submission.result
````

---

## 📂 Catálogo

Após criar a automação, adicione-a ao catálogo (`catalog/dev.json`):

```json
{
  "id": "exemplo",
  "label": "Exemplo",
  "categoryId": "gestao",
  "description": "Automação de exemplo para novos módulos",
  "ui": { "type": "iframe", "url": "/api/automations/exemplo/ui" },
  "routes": ["/exemplo"],
  "navigation": [{ "path": "/exemplo", "label": "Exemplo" }],
  "requiredRoles": ["admin"],
  "order": 99
}
```

---

## 🧪 Testes Recomendados

### Criar submissão

```bash
curl -X POST http://localhost:8000/api/automations/exemplo/submit \
  -H "Content-Type: application/json" \
  -d '{"nome":"João","idade":30}'
```

### Listar submissões

```bash
curl http://localhost:8000/api/automations/exemplo/submissions
```

### Obter submissão

```bash
curl http://localhost:8000/api/automations/exemplo/submissions/1
```

### Baixar resultado

```bash
curl -X POST http://localhost:8000/api/automations/exemplo/submissions/1/download -o resultado.json
```

---

## ✅ Checklist ao Criar Automação

* [ ] Criar módulo em `apps/bff/app/automations/{slug}.py`.
* [ ] Implementar endpoints obrigatórios.
* [ ] Adicionar entrada no catálogo (`catalog/dev.json`).
* [ ] Criar documentação em `docs/10-bff/automations/{slug}.md`.
* [ ] Adicionar testes (`pytest`).
* [ ] Validar RBAC se necessário (`requiredRoles`).
* [ ] Garantir logs e auditoria em eventos principais.

---

## 🚀 Futuro

* Templates automáticos para novas automações.
* Suporte a dependências entre automações (ex.: DFD → PCA → ETP).
* Geração automática de documentação OpenAPI para cada módulo.