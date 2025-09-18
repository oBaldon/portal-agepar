# Catálogo – Visão Geral

O **Catálogo** é o mecanismo central para **descoberta e organização** das automações dentro do Portal AGEPAR.  
Ele define **categorias** e **blocos** que o Host consome para montar a UI (navbar, cards, rotas).

---

## 🎯 Objetivos

- Fornecer uma estrutura **única e centralizada** de navegação.
- Separar **definição de automações** (BFF) da **renderização** (Host).
- Garantir que o catálogo seja **dinâmico** e **extensível**.
- Servir de base para **RBAC** (controle de visibilidade de blocos).

---

## 📦 Estrutura

Um catálogo é um objeto JSON com duas chaves principais:

```json
{
  "categories": [
    { "id": "compras", "label": "Compras", "icon": "shopping-cart", "order": 1 }
  ],
  "blocks": [
    {
      "id": "dfd",
      "label": "Documento de Formalização da Demanda",
      "categoryId": "compras",
      "description": "Gera DFD em formato oficial",
      "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" },
      "routes": ["/compras/dfd"],
      "requiredRoles": ["compras_editor"],
      "order": 1,
      "hidden": false
    }
  ]
}
````

---

## 🔹 Categorias

* **`id`**: identificador único (ex.: `"compras"`).
* **`label`**: rótulo exibido no Host.
* **`icon`** (opcional): nome de ícone (lucide-react).
* **`order`** (opcional): define ordenação (menor → primeiro).
* Se ausente, ordem segue **definição no JSON**.

---

## 🔹 Blocos

* **`id`**: identificador único (slug).
* **`label`**: nome exibido no card/navbar.
* **`categoryId`**: vínculo com uma categoria existente.
* **`description`** (opcional): ajuda/tooltip.
* **`ui`**:

  * `type: "iframe"` → renderizado dentro de `<iframe>`.
  * `url`: endereço fornecido pelo BFF (ex.: `/api/automations/dfd/ui`).
* **`routes`**: lista de paths que apontam para este bloco.
* **`navigation`** (opcional): breadcrumbs personalizados.
* **`requiredRoles`** (opcional): restringe visibilidade.
* **`order`** (opcional): controla ordenação entre blocos.
* **`hidden`** (opcional): se `true`, bloco não aparece em navbar/cards.

---

## 🧭 Fluxo de Uso

1. **BFF** expõe catálogo em `/catalog/dev` e `/catalog/prod`.
2. **Host** consome catálogo e gera UI automaticamente:

   * Navbar → `categories[]`.
   * Cards → `blocks[]` por categoria.
   * Rotas → `routes[]` de cada bloco.
3. **RBAC** aplicado:

   * Front oculta blocos sem roles necessárias.
   * BFF reforça (não retorna blocos proibidos em `/catalog/prod`).

---

## 🔐 Segurança

* O catálogo de **produção** deve filtrar blocos de acordo com roles do usuário autenticado.
* Blocos ocultos (hidden=true) não aparecem no front.
* BFF reforça segurança em endpoints de automação (`/api/automations/...`).

---

## 🧪 Testes

* **Validação JSON Schema**: garantir que catálogo está no formato esperado.
* **Ordem**: categorias/blocos respeitam `order`.
* **RBAC**: catálogo de prod não deve expor blocos fora das roles do usuário.
* **Fallback**: Host deve funcionar mesmo que catálogo venha vazio (mostrar mensagem amigável).

---

## 🔮 Futuro

* Suporte a **ícones customizados** e cores por categoria.
* Versões diferentes de catálogo (ex.: ambiente homologação).
* Catálogo incremental para **feature flags**.
* Extensão de `ui.type` além de `iframe` (ex.: `native`, `modal`).
