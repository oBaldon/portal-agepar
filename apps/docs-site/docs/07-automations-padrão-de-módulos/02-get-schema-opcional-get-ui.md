---
id: get-schema-opcional-get-ui
title: "GET /schema (opcional), GET /ui"
sidebar_position: 2
---

Esta página define o **contrato mínimo** e as **boas práticas** dos endpoints de uma automação para:  
- **`GET /schema`** (opcional): metadados para o front (validação/UX).  
- **`GET /ui`**: página **HTML simples** para ser embutida no Host via `<iframe>`.

> Referências no repo: `apps/bff/app/automations/*.py`, `apps/bff/app/automations/templates/*/ui.html`  
> Integração no catálogo: a UI é usada em `ui.url` (`/api/automations/<slug>/ui`).

---

## 1) Visão geral

```mermaid
flowchart LR
  HOST(Host React) -->|fetch| SCHEMA(/api/automations/:slug/schema)
  HOST -->|iframe| UI(/api/automations/:slug/ui)
  SCHEMA --> UX(Montar formulários/validar)
  UI --> USER(Interação do usuário)
````

* **`/schema`**: ajuda o Host a **montar formulários**, **pré-validar** campos e **exibir dicas**.
* **`/ui`**: entrega a **tela pronta** (HTML/JS/CSS puros), independente do build do Host.

---

## 2) `GET /schema` — contrato sugerido

* **Opcional**, mas recomendado quando o Host precisa de **conhecimento de domínio** (rótulos, tipos, máscaras).
* Resposta **JSON** com versão e campos.
* Pode incluir **defaults**, **placeholders**, **enumerações** e **regras básicas**.

### Exemplo (mínimo)

```json
{
  "version": "1",
  "title": "Form2JSON",
  "fields": {
    "fullName": { "type": "string", "required": true, "minLength": 1 },
    "email": { "type": "string", "required": false, "format": "email" }
  }
}
```

### Handler (FastAPI)

```python
# apps/bff/app/automations/form2json.py (trecho)
from fastapi import APIRouter

router = APIRouter()
SLUG = "form2json"

@router.get(f"/{SLUG}/schema")
def schema():
    return {
        "version": "1",
        "title": "Form2JSON",
        "fields": {
            "fullName": {"type": "string", "required": True, "minLength": 1},
            "email": {"type": "string", "required": False, "format": "email"},
        },
    }
```

### Caching (opcional)

Se o schema muda pouco, adicione cabeçalhos:

```python
from fastapi.responses import JSONResponse

@router.get(f"/{SLUG}/schema")
def schema():
    data = { "version": "1", "fields": { /* ... */ } }
    resp = JSONResponse(data)
    resp.headers["Cache-Control"] = "public, max-age=60"
    return resp
```

---

## 3) `GET /ui` — HTML embutível (iframe)

* **HTML/JS/CSS puros** em `apps/bff/app/automations/templates/<slug>/ui.html`.
* Sem bundlers; **carrega rápido** e é **isolado** do Host.
* O Host **embute** a rota em um `<iframe src="/api/automations/<slug>/ui">`.

### Handler (FastAPI)

```python
from fastapi.responses import HTMLResponse
from pathlib import Path

TEMPLATES = Path(__file__).parent / "templates" / SLUG

@router.get(f"/{SLUG}/ui", response_class=HTMLResponse)
def ui():
    html = (TEMPLATES / "ui.html").read_text(encoding="utf-8")
    return HTMLResponse(html)
```

### Template (exemplo mínimo)

```html
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Form2JSON</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body { font-family: system-ui, sans-serif; padding: 16px; }
      label { display: block; margin-top: 8px; }
      button { margin-top: 12px; padding: 8px 12px; border-radius: 8px; }
      pre { background: #f8fafc; padding: 12px; border-radius: 8px; }
    </style>
  </head>
  <body>
    <h1>Form2JSON</h1>
    <form id="f">
      <label>Nome completo
        <input name="fullName" required />
      </label>
      <label>E-mail
        <input name="email" type="email" />
      </label>
      <button type="submit">Enviar</button>
    </form>
    <pre id="out" hidden></pre>
    <script>
      const f = document.getElementById("f");
      const out = document.getElementById("out");
      f.addEventListener("submit", async (e) => {
        e.preventDefault();
        const payload = Object.fromEntries(new FormData(f));
        const res = await fetch("/api/automations/form2json/submit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify(payload),
        });
        out.hidden = false;
        out.textContent = JSON.stringify(await res.json(), null, 2);
      });
    </script>
  </body>
</html>
```

---

## 4) Segurança e cabeçalhos úteis

* **CORS**: não afeta o `<iframe>`, mas as **chamadas AJAX** do UI precisam de CORS se a origem diferir.
* **Embutir em iframe**: evite enviar `X-Frame-Options: DENY` na resposta do `/ui`.
* **CSP** (opcional): defina `frame-ancestors` permitindo o domínio do Host em produção.
* **Cookies/sessão**: use `credentials: "include"` no fetch da UI.

Checklist:

* [ ] UI carrega sem bloqueio de `iframe`.
* [ ] CORS com `allow_credentials=True` no BFF.
* [ ] Cookies corretos (domain/path/SameSite) conforme ambiente.

---

## 5) Integração com o catálogo

No `catalog.dev.json`, aponte o bloco para o `/ui`:

```json
{
  "categoryId": "compras",
  "ui": { "type": "iframe", "url": "/api/automations/form2json/ui" },
  "description": "Conversão de formulário em JSON"
}
```

O Host renderiza via `<iframe>` e usa `/schema` (se existir) para melhorar UX.

---

## 6) cURLs e testes rápidos

```bash
# Schema
curl -s http://localhost:8000/api/automations/form2json/schema | jq .

# UI (apenas headers)
curl -I http://localhost:8000/api/automations/form2json/ui

# Via Host (proxy Vite)
curl -I http://localhost:5173/api/automations/form2json/ui
```

No navegador, abra o Host e confirme que o card **abre o iframe** corretamente.

---

## 7) Problemas comuns

* **UI em branco no iframe**
  Verifique se o `/ui` retorna **HTML válido** e não há cabeçalhos que bloqueiem embedding.

* **Form não envia (CORS)**
  Adicione as origens do Host no CORS do BFF (`http://localhost:5173`, `http://host:5173`) e `allow_credentials=True`.

* **Schema ignorado no front**
  O Host pode **não** depender do `/schema`. Use-o apenas quando houver ganho real (rótulos, máscaras, enums).

---

## 8) Boas práticas

* **Versão** do schema (`version`) para facilitar cache e compatibilidade.
* **UI leve**: sem bundlers, CSS/JS mínimos, feedback de carregamento.
* **Mensagens claras** em erros do submit (mapa 400/422).
* **Observabilidade**: logue `submit/ui_opened` com `req_id`.

---

## 9) Próximos passos

* **[POST /submit (BackgroundTasks)](./post-submit-backgroundtasks)**
* **[GET /submissions e detalhes](./get-submissions-get-submissions-id)**
* **[POST /submissions/`{id}`/download](./post-submissions-id-download)**

---

> _Criado em 2025-11-18_

