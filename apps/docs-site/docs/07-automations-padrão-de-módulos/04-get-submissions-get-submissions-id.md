---
id: get-submissions-get-submissions-id
title: "GET /submissions, GET /submissions/`{id}`"
sidebar_position: 4
---

Esta página documenta as rotas de **consulta de submissões** de uma automação:  
- **`GET /api/automations/{slug}/submissions`** (lista/paginação/filtros)  
- **`GET /api/automations/{slug}/submissions/{id}`** (detalhe de uma submissão)

> Referências no repo: `apps/bff/app/automations/*.py`, `apps/bff/app/db.py`  
> Relacionado: **[POST /submit (BackgroundTasks)](./post-submit-backgroundtasks)**

---

## 1) Contrato (resumo)

| Método | Caminho | Descrição |
|---:|---|---|
| GET | ``/api/automations/{slug}/submissions`` | Lista submissões da automação, com suporte a filtros simples. |
| GET | ``/api/automations/{slug}/submissions/{id}`` | Retorna uma submissão específica (status, `result`, `error`). |

**Campos típicos da submissão**

```json
{
  "id": "s_abcd1234",
  "kind": "example",
  "status": "queued | processing | done | failed",
  "payload": { "...": "recebido no submit" },
  "result": { "artifact": "/downloads/s_abcd1234.pdf" },
  "error": null,
  "created_at": "2025-11-18T20:06:00Z",
  "updated_at": "2025-11-18T20:06:05Z"
}
````

> Estados canônicos: `queued → processing → done` (ou `failed`).
> O `db.py` mantém colunas para `payload`, `status`, `result`, `error`, datas.

---

## 2) Listagem — `GET /submissions`

### Query params sugeridos (opcional)

* `status`: filtra por estado (`queued`, `processing`, `done`, `failed`).
* `limit`/`offset`: paginação simples (ex.: `limit=20`, `offset=0`).
* `q`: busca livre em campos conhecidos (id, parte do `payload`, etc.).

### Exemplo de resposta

```json
{
  "items": [
    { "id": "s_1", "status": "done", "created_at": "2025-11-18T20:00:00Z" },
    { "id": "s_2", "status": "processing", "created_at": "2025-11-18T20:02:00Z" }
  ],
  "total": 2,
  "limit": 20,
  "offset": 0
}
```

### Handler (ilustrativo)

```python
# apps/bff/app/automations/example.py (trecho)
from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter()
SLUG = "example"

@router.get(f"/{SLUG}/submissions")
def list_submissions(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    # TODO: ler do banco real (db.py), aplicar filtros e paginação
    items = []  # substitua por consulta
    total = 0
    return {"items": items, "total": total, "limit": limit, "offset": offset}
```

---

## 3) Detalhe — `GET /submissions/`**`{id}`**

Retorna a **submissão completa**, incluindo `payload` original, `status`, `result` (quando `done`) e `error` (quando `failed`).

### Exemplo de resposta (done)

```json
{
  "id": "s_abcd1234",
  "status": "done",
  "result": { "artifact": "/downloads/s_abcd1234.pdf" },
  "error": null
}
```

### Handler (ilustrativo)

```python
# apps/bff/app/automations/example.py (trecho)
from fastapi import HTTPException
from ..errors import err

@router.get(f"/{SLUG}/submissions/{{id}}")
def get_submission(id: str):
    # TODO: buscar no banco; exemplo com erro 404 padronizado
    submission = None  # substitua por consulta
    if not submission:
        raise HTTPException(404, err("submission not found", 404))
    return submission
```

---

## 4) cURLs úteis

```bash
# Lista (todos)
curl -s "http://localhost:8000/api/automations/example/submissions" | jq .

# Lista (filtrando por status)
curl -s "http://localhost:8000/api/automations/example/submissions?status=done&limit=10" | jq .

# Detalhe por id
curl -s "http://localhost:8000/api/automations/example/submissions/s_abcd1234" | jq .
```

> Via Host (proxy do Vite), troque `8000` por `5173`.

---

## 5) Erros e códigos

* **404**: submissão inexistente (`"submission not found"`).
* **401/403**: se a automação exigir sessão/roles.
* **400**: parâmetros inválidos (ex.: `limit` fora do intervalo).

**Envelope de erro sugerido**: `{ "error": "...", "code": 4xx }` (ver página de **Mapeamento de erros**).

---

## 6) Boas práticas

* **Não** retornar `payload` sensível no detalhe; mas mantenha o suficiente para depuração.
* Incluir **`Location`** no `POST /submit` apontando para o detalhe, para facilitar polling.
* Ordenar lista por `created_at desc` (padrão usual).
* Paginação por `limit/offset` é suficiente; se necessário, evolua para **cursor**.

---

## 7) Troubleshooting

* **`404` inesperado**: id pode estar incorreto; verifique a origem (header `Location` do submit).
* **Sem resultados**: confirme filtros (`status`) e limites.
* **Campos nulos**: `result` só existe quando `status = done`; `error` só quando `failed`.

---

## Próximos passos

* **[POST /submit (BackgroundTasks)](./post-submit-backgroundtasks)**
* **[POST /submissions/`{id}`/download](./post-submissions-id-download)**

---

> _Criado em 2025-11-18_
