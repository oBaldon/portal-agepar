# Schema de Categoria e Bloco (Catálogo)

Este documento define formalmente os **schemas** do Catálogo consumido pelo Host e servido pelo BFF.  
Inclui **JSON Schema**, exemplos válidos, regras de **ordenação**, **RBAC**, campos opcionais e recomendações de **validação**.

---

## 🎯 Objetivo do Schema

- Garantir **consistência** entre ambientes (dev/prod).
- Permitir **validação automática** no BFF e em pipelines CI.
- Servir de contrato para o Host (tipos/rotas/visibilidade).

---

## 🧱 Estrutura em Alto Nível

```json
{
  "categories": [/* CatalogCategory */],
  "blocks": [/* CatalogBlock */]
}
````

---

## ✅ JSON Schema (v2020-12)

> Salve como `docs/30-catalog/catalog.schema.json` (recomendado).
> O Host/BFF podem usar este schema para validar arquivos/objetos de catálogo.

```json
{
  "$id": "https://portal-agepar/catalog.schema.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Portal AGEPAR Catalog",
  "type": "object",
  "required": ["categories", "blocks"],
  "additionalProperties": false,
  "properties": {
    "categories": {
      "type": "array",
      "items": { "$ref": "#/$defs/CatalogCategory" },
      "minItems": 1
    },
    "blocks": {
      "type": "array",
      "items": { "$ref": "#/$defs/CatalogBlock" },
      "minItems": 0
    }
  },
  "$defs": {
    "CatalogCategory": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "label"],
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[a-z0-9-]+$",
          "description": "Slug único da categoria (ex.: 'compras')."
        },
        "label": { "type": "string", "minLength": 1 },
        "icon": {
          "type": "string",
          "description": "Nome do ícone (ex.: lucide-react). Opcional."
        },
        "order": {
          "type": "integer",
          "minimum": 0,
          "description": "Ordem ascendente; se ausente, usa ordem do array."
        }
      }
    },

    "CatalogBlock": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "label", "categoryId", "ui", "routes"],
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[a-z0-9-]+$",
          "description": "Slug único do bloco (ex.: 'dfd')."
        },
        "label": { "type": "string", "minLength": 1 },
        "categoryId": {
          "type": "string",
          "pattern": "^[a-z0-9-]+$",
          "description": "Referência a CatalogCategory.id."
        },
        "description": { "type": "string" },

        "ui": { "$ref": "#/$defs/BlockUI" },

        "routes": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "string",
            "pattern": "^\\/[a-zA-Z0-9\\-\\/_:]*$"
          },
          "description": "Paths do Host que devem abrir este bloco."
        },

        "navigation": {
          "type": "array",
          "items": { "$ref": "#/$defs/NavItem" },
          "description": "Breadcrumbs opcionais."
        },

        "requiredRoles": {
          "type": "array",
          "items": { "type": "string", "minLength": 1 },
          "uniqueItems": true,
          "description": "Qualquer uma das roles permite acesso (ANY-of)."
        },

        "order": {
          "type": "integer",
          "minimum": 0,
          "description": "Ordem ascendente dentro da categoria; se ausente, ordem do array."
        },

        "hidden": {
          "type": "boolean",
          "default": false,
          "description": "Se true, não aparece em navbar/cards/rotas do Host."
        }
      }
    },

    "BlockUI": {
      "oneOf": [
        { "$ref": "#/$defs/IframeUI" }
        /* futura expansão: NativeUI, ModalUI, etc. */
      ],
      "description": "UI declara como o bloco é renderizado no Host."
    },

    "IframeUI": {
      "type": "object",
      "additionalProperties": false,
      "required": ["type", "url"],
      "properties": {
        "type": { "const": "iframe" },
        "url": {
          "type": "string",
          "pattern": "^\\/[a-zA-Z0-9\\-\\/_:.?=&#%+]*$",
          "description": "URL servida pelo BFF (ex.: /api/automations/dfd/ui)."
        }
      }
    },

    "NavItem": {
      "type": "object",
      "additionalProperties": false,
      "required": ["path", "label"],
      "properties": {
        "path": {
          "type": "string",
          "pattern": "^\\/[a-zA-Z0-9\\-\\/_:]*$"
        },
        "label": { "type": "string", "minLength": 1 }
      }
    }
  }
}
```

---

## 🔗 Regras de Integridade

* `blocks[].categoryId` **deve existir** em `categories[].id`.
* `blocks[].routes` **não podem** colidir entre si (Host pode validar duplicatas).
* `blocks[].id` e `categories[].id` são **únicos**.
* `hidden: true` → o Host **não rende** o bloco (navbar/cards/rotas).
* `requiredRoles` → **ANY-of**: possuir **uma** das roles já permite.
* `ui.type = "iframe"` → `ui.url` **deve** apontar para rota do BFF.

> Recomenda-se validar também **duplicidade de path** em `routes` na pipeline CI.

---

## 🧭 Regras de Ordenação

* **Categorias**: ordenar por `order` (asc). Se `order` ausente, **respeitar ordem do array**.
* **Blocos na categoria**: ordenar por `order` (asc). Se ausente, **respeitar ordem do array**.

> O Host deve **preservar a ordem de escrita** quando `order` não for informado (requisito do produto).

---

## 🧪 Exemplos

### Catálogo Mínimo Válido

```json
{
  "categories": [
    { "id": "compras", "label": "Compras" }
  ],
  "blocks": [
    {
      "id": "dfd",
      "label": "DFD",
      "categoryId": "compras",
      "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" },
      "routes": ["/dfd"]
    }
  ]
}
```

### Catálogo com RBAC, Navegação e Ordem

```json
{
  "categories": [
    { "id": "compras", "label": "Compras", "icon": "shopping-cart", "order": 1 },
    { "id": "gestao", "label": "Gestão", "order": 2 }
  ],
  "blocks": [
    {
      "id": "dfd",
      "label": "Documento de Formalização da Demanda",
      "categoryId": "compras",
      "description": "Gera o DFD padronizado",
      "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" },
      "routes": ["/compras/dfd"],
      "navigation": [{ "path": "/compras/dfd", "label": "DFD" }],
      "requiredRoles": ["admin", "compras"],
      "order": 1
    },
    {
      "id": "form2json",
      "label": "Form2JSON",
      "categoryId": "gestao",
      "description": "Converte formulários HTML em JSON",
      "ui": { "type": "iframe", "url": "/api/automations/form2json/ui" },
      "routes": ["/gestao/form2json"],
      "order": 2
    }
  ]
}
```

---

## 🧰 Validação (Node + AJV)

```ts
// scripts/validate-catalog.ts
import Ajv from "ajv";
import addFormats from "ajv-formats";
import schema from "./catalog.schema.json";
import fs from "node:fs";

const ajv = new Ajv({ allErrors: true });
addFormats(ajv);
const validate = ajv.compile(schema);

const json = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
if (!validate(json)) {
  console.error("Catálogo inválido:", validate.errors);
  process.exit(1);
}
console.log("Catálogo válido ✅");
```

**CI (exemplo):**

```bash
node scripts/validate-catalog.js catalog/dev.json
```

---

## 🧪 Validação (Python + Pydantic v2 – opcional)

```python
from pydantic import BaseModel, ConfigDict, field_validator
from typing import List, Optional, Literal

class CatalogCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str
    icon: Optional[str] = None
    order: Optional[int] = None

class IframeUI(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["iframe"]
    url: str

class NavItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    label: str

class CatalogBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str
    categoryId: str
    description: Optional[str] = None
    ui: IframeUI
    routes: List[str]
    navigation: Optional[List[NavItem]] = None
    requiredRoles: Optional[List[str]] = None
    order: Optional[int] = None
    hidden: bool = False

class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    categories: List[CatalogCategory]
    blocks: List[CatalogBlock]

    @field_validator("blocks")
    @classmethod
    def unique_ids_and_routes(cls, v, info):
        ids = set()
        paths = set()
        for b in v:
            if b.id in ids:
                raise ValueError(f"block id duplicado: {b.id}")
            ids.add(b.id)
            for p in b.routes:
                if p in paths:
                    raise ValueError(f"rota duplicada: {p}")
                paths.add(p)
        return v

    @field_validator("blocks")
    @classmethod
    def category_fk(cls, blocks, info):
        cats = {c.id for c in info.data["categories"]}
        for b in blocks:
            if b.categoryId not in cats:
                raise ValueError(f"categoryId inexistente: {b.categoryId} (bloco {b.id})")
        return blocks
```

---

## 🔐 Considerações de Segurança

* `ui.type = "iframe"` recomenda sandbox no Host:
  `sandbox="allow-forms allow-scripts allow-same-origin"`, `referrerPolicy="no-referrer"`.
* Em produção, **CSP** deve limitar `frame-src` ao domínio do BFF.
* O BFF **não deve** expor em `/catalog/prod` blocos fora do RBAC do usuário autenticado.

---

## 🧭 Diretrizes de Evolução

* Quando introduzir **novos tipos de UI** (ex.: `native`), expanda `$defs.BlockUI.oneOf`.
* Para **feature flags**, adicione campos opcionais precedidos de `x-` (ex.: `x-flag`) para não quebrar consumidores.
* Versione o catálogo (ex.: `x-version`) se for necessário migrar clientes.

---

## ✅ Checklist de PR

* [ ] JSON do catálogo validado contra `catalog.schema.json`.
* [ ] `categories[].id` únicos e consistentes.
* [ ] `blocks[].id` únicos e `categoryId` válidos.
* [ ] `routes[]` sem duplicidade global.
* [ ] Ordem (`order`) revisada; ausência mantém ordem do arquivo.
* [ ] RBAC revisado (`requiredRoles` coerentes).
* [ ] `ui.url` aponta para endpoint **válido** do BFF.
