---
id: post-submissions-id-download
title: "POST /submissions/`{id}`/download"
sidebar_position: 5
---

Esta página define o contrato do endpoint de **download de artefatos** gerados por uma automação:

- **`POST /api/automations/{slug}/submissions/{id}/download`**  
  Gera **on-demand** (ou recupera) o arquivo associado à submissão e retorna como **download** (PDF/DOCX/ZIP, etc.).

> Referências no repo: `apps/bff/app/automations/*.py`, `apps/bff/app/utils/docx_tools.py`, `apps/bff/app/db.py`  
> Relacionado: **[POST /submit (BackgroundTasks)](./post-submit-backgroundtasks)**, **[GET /submissions, GET /submissions/`{id}`](./get-submissions-get-submissions-id)**

---

## 1) Quando usar `POST` (vs `GET`)
- **`POST` recomendado** quando o download pode **(re)gerar** o artefato ou requer **payload adicional/side-effects**.  
- **`GET` aceitável** se o artefato já existe e é **puramente estático** (sem efeitos nem parâmetros sensíveis).

Neste projeto, padronizamos **`POST`** para que o back-end possa:
- revalidar permissão/estado,  
- re-gerar documento se necessário,  
- auditar o evento de **download**.

---

## 2) Resposta esperada (headers)

Retorne **arquivo binário** com:
- `Content-Type: application/pdf` *(exemplo)*  
- `Content-Disposition: attachment; filename="<nome>.pdf"`  
- `Cache-Control`: conforme estratégia (geralmente `no-store` para docs sensíveis)

---

## 3) Handler FastAPI — exemplos

### 3.1) Retornando **arquivo existente** (disco)
```python
# apps/bff/app/automations/example.py (trecho)
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from ..errors import err
from ..logging_utils import info, error

router = APIRouter()
SLUG = "example"
ARTIFACTS = Path("/data/artifacts")  # ajuste para seu storage

@router.post(f"/{SLUG}/submissions/{{id}}/download")
def download_submission(id: str):
    # 1) Buscar submissão e checar estado/perm
    sub = _get_submission(id)  # implemente via db.py
    if not sub:
        raise HTTPException(404, err("submission not found", 404))
    if sub.get("status") != "done":
        raise HTTPException(409, err("submission not ready", 409))

    # 2) Descobrir caminho do artefato
    #   Convenção: sub["result"]["artifact"] pode guardar caminho absoluto ou relativo
    artifact = sub.get("result", {}).get("artifact")
    if not artifact:
        raise HTTPException(404, err("artifact not found", 404))

    path = Path(artifact)
    if not path.is_absolute():
        path = ARTIFACTS / path
    if not path.exists():
        raise HTTPException(404, err("artifact file missing", 404))

    info("download_ok", submission_id=id, file=str(path.name))
    # 3) Devolver como anexo
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=path.name,
    )
````

### 3.2) **Gerando em memória** (PDF/DOCX) e devolvendo

```python
# apps/bff/app/automations/example.py (trecho)
from fastapi.responses import StreamingResponse
from io import BytesIO

@router.post(f"/{SLUG}/submissions/{{id}}/download")
def download_submission_inline(id: str):
    sub = _get_submission(id)
    if not sub:
        raise HTTPException(404, err("submission not found", 404))

    # Exemplo: gerar PDF/DOCX usando dados do payload/result
    content = BytesIO()
    content.write(b"%PDF-1.4\n% ... (bytes de um PDF gerado) ...")
    content.seek(0)

    filename = f"{SLUG}-{id}.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(content, media_type="application/pdf", headers=headers)
```

> Dica: use `apps/bff/app/utils/docx_tools.py` se a automação gera **DOCX** a partir de templates.
> Para arquivos grandes, prefira `FileResponse` com caminho no disco.

---

## 4) Estados e validações recomendadas

1. **`404`** para submissão inexistente.
2. **`409`** quando `status` **≠ `done`** (não finalizada).
3. **`403`** se o usuário **não tem permissão** (RBAC).
4. **`404`** para artefato ausente/inconsistente.

> Padronize o envelope de erro `{ "error": "...", "code": 4xx }`.
> Registre auditoria `download` para rastreabilidade.

---

## 5) Auditoria e logging

* **Audit**: `add_audit(kind=SLUG, submission_id=id, event="download")`
* **Log INFO**: `download_ok` com `submission_id` e `filename`.
* **Log ERROR** em falhas com contexto mínimo (sem PII).

---

## 6) cURLs úteis

```bash
# Download via BFF (salva o nome do servidor com -OJ)
curl -s -X POST -OJ http://localhost:8000/api/automations/example/submissions/s_abcdef1234/download

# Via Host (proxy Vite)
curl -s -X POST -OJ http://localhost:5173/api/automations/example/submissions/s_abcdef1234/download
```

> `-O` salva com o nome do path da URL; `-J` respeita `Content-Disposition` do servidor.

---

## 7) Segurança

* Exigir **sessão** e (opcional) **RBAC** (roles) para baixar.
* **Não** exponha caminhos internos; normalize caminhos e **não** permita path traversal.
* Considere TTL/assinaturas quando o link for compartilhável.
* Para documentos sensíveis, use `Cache-Control: no-store`.

---

## 8) Boas práticas

* Persistir no `result.artifact` o **caminho lógico** do artefato.
* Usar **extensão e `Content-Type`** corretos.
* Nomear arquivos de forma **determinística**: `"{slug}-{id}.{ext}"`.
* Para re-geração determinística, armazene **hash** do payload e versão do template.

---

## 9) Problemas comuns

* **`409 submission not ready`** → a submissão ainda está `processing`. Aguarde e consulte o status.
* **Arquivo sumiu do disco** → garanta política de retenção; re-gere ou marque como `failed`.
* **Download “corrompido”** → verifique `Content-Type`, encoding e geração do binário.
* **Permissão negada** → roles do usuário não cobrem a automação.

---

## Próximos passos

* **[GET /submissions, GET /submissions/`{id}`](./get-submissions-get-submissions-id)**
* **[Local: apps/bff/app/automations/`{slug}`.py](./local-apps-bff-app-automations-slugpy)**
* **[GET /schema (opcional), GET /ui](./get-schema-opcional-get-ui)**

---

> _Criado em 2025-11-18_