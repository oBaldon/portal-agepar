---
id: convenções-icon-order-hidden
title: "Convenções (icon, order, hidden)"
sidebar_position: 3
---

Esta página define **convenções e boas práticas** para os campos **`icon`**, **`order`** e **`hidden`** no catálogo servido em **`/catalog/dev`**.

> Fonte: `catalog/catalog.dev.json` (carregado pelo BFF e consumido pelo Host).  
> Regras gerais: **ordem do arquivo preservada por padrão**, **RBAC ANY-of** por bloco quando aplicável, e **campos extras são ignorados** com tolerância a futuro.

---

## 1) Onde cada campo aparece

- **`icon`**
  - Pode existir em **categories** (para exibição na navbar/cards).
  - Pode existir em **blocks** (opcional; o Host pode usar para ícones contextuais).
- **`order`**
  - Pode existir em **categories** e/ou **blocks**.
  - **Só** tem efeito quando a UI **optar por ordenar explicitamente**. Caso contrário, a ordem é a do JSON.
- **`hidden`**
  - Pode existir em **categories** e **blocks**.
  - Quando `true`, **omite** o item da UI (após filtros de RBAC).

```mermaid
flowchart LR
  C[categories] --> IC[icon string]
  C --> OC[order number]
  C --> HC[hidden boolean]
  B[blocks] --> IB[icon string]
  B --> OB[order number]
  B --> HB[hidden boolean]
````

---

## 2) Exemplos práticos

### 2.1) Ícones em categorias

```json
{
  "categories": [
    { "id": "compras",   "label": "Compras",   "icon": "mdi-cart" },
    { "id": "contratos", "label": "Contratos", "icon": "lucide-file-text" }
  ],
  "blocks": []
}
```

**Como o Host interpreta**

* `icon` é uma **string livre**. A UI decide como mapear para uma lib (MDI/Lucide/etc.).
* Caso a classe/slug não exista na UI, trate como **texto** ou use um **ícone padrão**.

### 2.2) Ordenação explícita (opcional)

```json
{
  "categories": [
    { "id": "orcamento", "label": "Orçamento", "order": 0 },
    { "id": "contratos", "label": "Contratos", "order": 1 },
    { "id": "compras",   "label": "Compras" }  // sem order
  ],
  "blocks": [
    { "categoryId": "compras", "ui": { "type": "iframe", "url": "/api/automations/pca/ui" }, "order": 0 },
    { "categoryId": "compras", "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" } }
  ]
}
```

**Comportamento recomendado**

* **Padrão**: **não** aplicar sort → usa a ordem do arquivo.
* **Variante** (se solicitado): aplicar um sort estável por `order` (itens sem `order` vão **para o fim**, preservando ordem relativa).

### 2.3) Itens ocultos (rascunho)

```json
{
  "categories": [
    { "id": "analise", "label": "Análise", "hidden": true }
  ],
  "blocks": [
    {
      "categoryId": "compras",
      "ui": { "type": "iframe", "url": "/api/automations/tr/ui" },
      "hidden": true
    }
  ]
}
```

* Itens com `hidden: true` **não aparecem** na UI. Útil para **WIP** sem excluir o histórico do JSON.

---

## 3) Tipos de referência (Host – TS)

```ts
export type CatalogCategory = {
  id: string;
  label: string;
  icon?: string;   // ex.: "mdi-cart", "lucide-file-text"
  order?: number;  // usado somente se optar por ordenar
  hidden?: boolean;
};

export type CatalogBlock = {
  categoryId: string;
  ui: { type: "iframe"; url: string } | { type: "link"; href: string };
  // extras de navegação/RBAC omitidos aqui
  icon?: string;   // opcional; ícone do próprio bloco
  order?: number;  // idem
  hidden?: boolean;
};
```

---

## 4) Boas práticas

* **`icon`**

  * Use um **namespace/classe** claro (ex.: `mdi-cash`, `lucide-lock`).
  * Evite acentos e espaços; prefira **kebab-case**.
  * Garanta **fallback** no Host (ícone padrão quando não suportado).

* **`order`**

  * Use **inteiros pequenos** (0, 1, 2…) apenas quando **realmente** precisar ordenar.
  * Não repita `order` sem necessidade; quando repetir, a UI deve usar **sort estável**.

* **`hidden`**

  * Marque itens em desenvolvimento com `hidden: true`.
  * Remova `hidden` quando a automação estiver pronta para uso.

* **Compatibilidade**

  * Mantenha **nomes estáveis** (não renomeie `icon`, `order`, `hidden`).
  * Campos extras são tolerados pelo BFF (extra: ignore), mas **não** sobrescreva chaves existentes.

---

## 5) Testes e verificação

```bash
# Catálogo direto do BFF
curl -s http://localhost:8000/catalog/dev | jq .

# Via Host (proxy)
curl -s http://localhost:5173/catalog/dev | jq .

# Ver navbar (visualmente): categorias devem refletir icon/order/hidden
```

Se estiver usando a variante **ordenada**, valide que:

* Itens com `order` aparecem **antes** dos sem `order`.
* Itens sem `order` mantêm a **ordem relativa** original.

---

## 6) Problemas comuns

* **Ícone não aparece**
  O slug não existe na lib da UI. Ajuste o mapeamento ou use um slug suportado.

* **Ordem “mudando sozinha”**
  Algum helper aplicou `sort` por padrão. A regra do projeto é **preservar a ordem do arquivo**, a menos que a página peça ordenação.

* **Categoria aparece vazia**
  Pode não haver blocos visíveis (RBAC/hidden). Confirme `requiredRoles` e `hidden`.

* **Item não aparece**
  Verifique `hidden: true` herdado ou aplicado no próprio item.

---

## 7) Dicas de manutenção

* Defina **ícones consistentes** por domínio funcional (ex.: compras, contratos, orçamento).
* **Documente** quando ativar ordenação por `order` em alguma tela.
* Use `hidden` para **releases graduais** (feature flag simples no JSON).

---

## Próximos passos

* **[Esquema de bloco (categoryId, ui, navigation, routes, ...)](./esquema-de-bloco-categoryid-ui-navigation-routes)**
* **[Exemplos e extensão](./exemplos-e-extensao)**

---

> _Criado em 2025-11-18_