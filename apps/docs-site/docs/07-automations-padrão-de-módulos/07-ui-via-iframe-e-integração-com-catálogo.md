---
id: ui-via-iframe-e-integração-com-catálogo
title: "UI via iframe e integração com catálogo"
sidebar_position: 7
---

Esta página mostra como **expor a UI** de cada automação via **`<iframe>`** e como **integrá-la ao catálogo** (`/catalog/dev`) para ser renderizada pelo **Host (React/Vite/TS)**.

> Referências no repo:  
> `apps/bff/app/automations/templates/*/ui.html`, `apps/bff/app/automations/*.py`,  
> `catalog/catalog.dev.json`, `apps/host/src/pages/CategoryView.tsx`, `apps/host/src/lib/catalog.ts`

---

## 1) Conceito

- Cada automação oferece uma página **HTML simples** em ``GET /api/automations/{slug}/ui``.  
- O **catálogo** aponta um bloco `ui` do tipo **`iframe`** com a `url` dessa página.  
- O **Host** lê o catálogo e **renderiza o `<iframe>`** dentro de um card.

```mermaid
flowchart LR
  Catalog[Catalog JSON] --> Host[Host React]
  Host --> Navbar
  Host --> Card[Card com iframe]
  Card --> Iframe[UI da automacao]
  Iframe --> Submit[POST submit]
  Submit --> BFF
  BFF --> DB
````

---

## 2) Catálogo — como declarar o bloco

No `catalog.dev.json`, cada bloco que usa UI embutida deve ser declarado como:

```json
{
  "categoryId": "compras",
  "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" },
  "description": "Elaboração do DFD",
  "requiredRoles": ["editor"]  // opcional (RBAC ANY-of)
}
```

**Regras**

* `type = "iframe"` e `url` deve apontar para o **endpoint `/ui`** da automação.
* O Host aplica **RBAC ANY-of** e **oculta** blocos com `hidden: true`.

---

## 3) BFF — endpoint `GET /ui`

Cada automação serve um **HTML estático** (sem build) em `templates/<slug>/ui.html`:

```python
# apps/bff/app/automations/dfd.py (trecho)
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path

router = APIRouter()
SLUG = "dfd"
TEMPLATES = Path(__file__).parent / "templates" / SLUG

@router.get(f"/{SLUG}/ui", response_class=HTMLResponse)
def ui():
    html = (TEMPLATES / "ui.html").read_text(encoding="utf-8")
    return HTMLResponse(html)
```

> **Iframe-friendly**: evite enviar cabeçalhos que bloqueiem embedding (ex.: `X-Frame-Options: DENY`).
> Para usar **cookies de sessão**, as requisições do HTML devem usar `credentials: "include"`.

---

## 4) Host — renderização do `<iframe>`

O Host consome o catálogo e, para blocos com `ui.type === "iframe"`, cria um card com `<iframe>`:

```tsx
// apps/host/src/pages/CategoryView.tsx (trecho ilustrativo)
{visible.map((b) => (
  <div key={`${b.categoryId}-${b.ui['url']}`} className="card">
    {b.ui['type'] === "iframe" ? (
      <iframe
        title={b.ui['url']}
        src={b.ui['url']}
        style={{ width: "100%", height: 600, border: 0 }}
      />
    ) : null}
  </div>
))}
```

**Dicas de UX**

* Defina **altura fixa** ou responsiva (ex.: usar `ResizeObserver` para ajustar a altura).
* Mostre **loading** enquanto o iframe carrega.
* Opcional: **título/descrição** do bloco acima do iframe.

---

## 5) UI HTML — exemplo mínimo

```html
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Minha Automacao</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body { font-family: system-ui, sans-serif; margin: 0; padding: 16px; }
      label { display:block; margin-top: 8px; }
      button { margin-top: 12px; padding: 8px 12px; border-radius: 8px; }
      pre { background:#f8fafc; padding:12px; border-radius: 8px; }
    </style>
  </head>
  <body>
    <h1>Formulário</h1>
    <form id="f">
      <label>Nome
        <input name="fullName" required />
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
        const res = await fetch("/api/automations/example/submit", {
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

## 6) Segurança e CORS (dev e prod)

* **Mesmo host** em dev: via proxy do Vite, os requests do iframe para `/api/...` são **same-origin** (cookies funcionam).
* **Produção com domínios distintos**: ajuste **CORS** e **cookies** (domínio, `SameSite`, `Secure`) e permita `frame-ancestors` na CSP.
* **RBAC**: se necessário, verifique `roles` no BFF para `submit`/`download`.

---

## 7) Testes rápidos

```bash
# Ver a UI (HTML) direto no BFF
curl -I http://localhost:8000/api/automations/example/ui

# Via Host (proxy)
curl -I http://localhost:5173/api/automations/example/ui

# Conferir catálogo pelo Host
curl -s http://localhost:5173/catalog/dev | jq .
```

Abra o Host e confirme que o **card** da categoria renderiza a UI no iframe.

---

## 8) Problemas comuns

* **Iframe em branco**
  HTML inválido ou cabeçalho que bloqueia `frame`. Garanta que o `/ui` retorna **200** com HTML.

* **Sessão não persiste**
  Faltou `credentials: "include"` no `fetch` da UI, ou CORS sem `allow_credentials=True`.

* **Rolagem dupla**
  Ajuste altura do iframe (fixa/responsiva). Remova margens no `body` do HTML.

* **URL do iframe 404**
  Cheque a `url` no catálogo e o registro do router no `main.py`.

---

## Próximos passos

* **[Local: apps/bff/app/automations/`{slug}`.py](./local-apps-bff-app-automations-slugpy)**
* **[GET /schema (opcional), GET /ui](./get-schema-opcional-get-ui)**
* **[POST /submit (BackgroundTasks)](./post-submit-backgroundtasks)**

---

> _Criado em 2025-11-18_