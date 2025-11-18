---
id: esquema-de-bloco-categoryid-ui-navigation-routes
title: "Esquema de bloco `{categoryId, ui, navigation, routes, ...}`"
sidebar_position: 2
---

Esta página formaliza o **esquema de um bloco** do catálogo (`/catalog/dev`) e como cada campo é interpretado pelo Host (React/Vite/TS) e pelo BFF (FastAPI).

> Arquivo fonte: `catalog/catalog.dev.json`  
> Regras gerais: **RBAC ANY-of** em `requiredRoles`, **ordem do arquivo preservada** por padrão, campos **extras são ignorados** no BFF.

---

## 1) Visão rápida (mínimo e completo)

**Bloco mínimo** (público, renderizado por `iframe`):
```json
{
  "categoryId": "compras",
  "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" }
}
````

**Bloco completo** (com todos os campos usuais):

```json
{
  "categoryId": "compras",
  "ui": { "type": "iframe", "url": "/api/automations/tr/ui" },
  "description": "Termo de Referência",
  "navigation": ["/guia/tr", "/docs/automacoes/tr"],
  "routes": ["/compras/tr", "/compras/tr/historico"],
  "requiredRoles": ["editor", "admin"],
  "order": 10,
  "hidden": false
}
```

---

## 2) Esquema de tipos (Host – TypeScript)

```ts
// Representação canônica usada no Host
export type CatalogBlockUI =
  | { type: "iframe"; url: string }
  | { type: "link"; href: string };

export type CatalogBlock = {
  // Obrigatório: vincula o bloco a uma categoria existente
  categoryId: string;

  // Obrigatório: descreve como o bloco é renderizado
  ui: CatalogBlockUI;

  // Opcionais
  description?: string;      // texto curto para card/tooltip
  navigation?: string[];     // links auxiliares (docs, tutoriais, atalhos)
  routes?: string[];         // rotas internas do Host para deep-linking
  requiredRoles?: string[];  // RBAC ANY-of (qualquer uma habilita)
  order?: number;            // usado somente se adotar ordenação explícita
  hidden?: boolean;          // quando true, oculta o bloco
};
```

**Interpretação no Host**

* `ui.type === "iframe"` → conteúdo embedado (preferido para automations internas).
* `ui.type === "link"` → abre nova aba (fallback quando o destino **não** permite `frame-ancestors`).
* `routes` e `navigation` são **metadados de navegação** que a UI pode usar para atalhos/menus secundários.
* `requiredRoles` usa **regra ANY-of** (basta uma role coincidir para liberar).
* `order` só tem efeito se você **optar** por ordenar; por padrão a UI **preserva a ordem do arquivo**.

---

## 3) Validação recomendada (BFF – Pydantic v2)

> O BFF deve aceitar campos **extras** sem falhar (tolerância a futuro), e normalizar entradas.

```python
# apps/bff/app/schemas/catalog.py (exemplo)
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal, Union

class UIIframe(BaseModel):
    type: Literal["iframe"]
    url: str

class UILink(BaseModel):
    type: Literal["link"]
    href: str

CatalogBlockUI = Union[UIIframe, UILink]

class CatalogBlock(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    category_id: str = Field(alias="categoryId")
    ui: CatalogBlockUI
    description: Optional[str] = None
    navigation: Optional[List[str]] = None
    routes: Optional[List[str]] = None
    required_roles: Optional[List[str]] = Field(default=None, alias="requiredRoles")
    order: Optional[int] = None
    hidden: Optional[bool] = None
```

Pontos-chave:

* `extra="ignore"` → campos desconhecidos **não** geram 422.
* `populate_by_name=True` → permite `categoryId` (JSON) mapear para `category_id` (Python).

---

## 4) Regras e convenções por campo

* **`categoryId` (obrigatório)**
  Deve existir em `categories[].id`. Use ids curtos, sem espaços/acentos.

* **`ui` (obrigatório)**

  * `iframe.url`: prefira **caminhos relativos** internos (`/api/automations/<slug>/ui`).
  * `link.href`: use para domínios externos que bloqueiam `iframe`.

* **`description`**
  Texto curto para cards/tooltip. Evite parágrafos longos.

* **`navigation` / `routes`**

  * `navigation`: lista de URLs úteis (docs/guias).
  * `routes`: caminhos SPA do próprio Host (deep links).

* **`requiredRoles` (RBAC ANY-of)**
  Ausente ou vazio ⇒ **público**. Ex.: `["viewer"]`, `["editor","admin"]`.

* **`order`**
  Útil só quando se **optar** por ordenar; caso contrário, preserve a ordem do arquivo.

* **`hidden`**
  Use `true` enquanto estiver em rascunho, sem remover o histórico do JSON.

---

## 5) Boas práticas de URL (iframe vs link)

* Prefira `iframe` para **automations do BFF**.
* Teste o endpoint alvo:

```bash
curl -I http://localhost:8000/api/automations/<slug>/ui
```

Se o serviço externo retornar `X-Frame-Options: DENY` ou `Content-Security-Policy` com `frame-ancestors` restritivo, use `ui.type = "link"`.

---

## 6) Exemplo: três blocos na mesma categoria

```json
{
  "categories": [
    { "id": "compras", "label": "Compras" }
  ],
  "blocks": [
    {
      "categoryId": "compras",
      "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" },
      "description": "DFD",
      "requiredRoles": ["editor","admin"],
      "order": 0
    },
    {
      "categoryId": "compras",
      "ui": { "type": "iframe", "url": "/api/automations/pca/ui" },
      "description": "PCA"
    },
    {
      "categoryId": "compras",
      "ui": { "type": "link", "href": "https://transparencia.exemplo.gov.br" },
      "description": "Portal externo",
      "hidden": false
    }
  ]
}
```

---

## 7) Checklist ao criar/editar um bloco

* [ ] `categoryId` existe em `categories[].id`.
* [ ] `ui` definido corretamente (`iframe.url` **ou** `link.href`).
* [ ] `requiredRoles` confere com o RBAC do BFF (se usado).
* [ ] Avaliou `hidden` enquanto em rascunho.
* [ ] Evitou ordenar se não for necessário (preserve a ordem do JSON).
* [ ] Para externos, confirmou permissões de `iframe`.

---

## 8) Erros comuns e diagnósticos

* **Bloco não aparece** → pode estar `hidden: true` ou bloqueado por `requiredRoles`.
* **Iframe em branco** → alvo bloqueia embedding; troque para `link`.
* **Ordem “estranha”** → algum helper aplicou `sort`; remova para preservar o arquivo.
* **422 no BFF** → verifique aliases/nomes dos campos e mantenha `extra="ignore"`.

---

## 9) Esquema JSON (validador básico – opcional)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.org/catalog-block.schema.json",
  "type": "object",
  "required": ["categoryId", "ui"],
  "additionalProperties": true,
  "properties": {
    "categoryId": { "type": "string", "minLength": 1 },
    "ui": {
      "oneOf": [
        {
          "type": "object",
          "required": ["type", "url"],
          "properties": {
            "type": { "const": "iframe" },
            "url": { "type": "string", "minLength": 1 }
          },
          "additionalProperties": true
        },
        {
          "type": "object",
          "required": ["type", "href"],
          "properties": {
            "type": { "const": "link" },
            "href": { "type": "string", "minLength": 1 }
          },
          "additionalProperties": true
        }
      ]
    },
    "description": { "type": "string" },
    "navigation": { "type": "array", "items": { "type": "string" } },
    "routes": { "type": "array", "items": { "type": "string" } },
    "requiredRoles": { "type": "array", "items": { "type": "string" } },
    "order": { "type": "integer" },
    "hidden": { "type": "boolean" }
  }
}
```

---

## 10) Próximos passos

* **[Convenções (icon, order, hidden)](./convencoes-icon-order-hidden)**
* **[Exemplos e extensão](./exemplos-e-extensao)**

---

> _Criado em 2025-11-18_