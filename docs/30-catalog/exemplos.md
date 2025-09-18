# Exemplos de Catálogo

Este documento apresenta **exemplos práticos** de catálogos em diferentes níveis de complexidade.  
Eles servem como referência para testes, desenvolvimento e validação do Host.

---

## 📘 Catálogo Mínimo

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
````

* Apenas uma categoria.
* Um bloco simples sem descrição ou roles.

---

## 📗 Catálogo com Ordem e RBAC

```json
{
  "categories": [
    { "id": "compras", "label": "Compras", "order": 1 },
    { "id": "gestao", "label": "Gestão", "order": 2 }
  ],
  "blocks": [
    {
      "id": "dfd",
      "label": "DFD",
      "categoryId": "compras",
      "description": "Formalização da demanda",
      "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" },
      "routes": ["/compras/dfd"],
      "requiredRoles": ["compras_editor"]
    },
    {
      "id": "form2json",
      "label": "Form2JSON",
      "categoryId": "gestao",
      "description": "Transforma formulários em JSON",
      "ui": { "type": "iframe", "url": "/api/automations/form2json/ui" },
      "routes": ["/gestao/form2json"],
      "order": 5
    }
  ]
}
```

* Categorias e blocos ordenados explicitamente.
* RBAC aplicado no bloco `dfd`.

---

## 📕 Catálogo Completo (com navegação e ocultos)

```json
{
  "categories": [
    { "id": "compras", "label": "Compras", "icon": "shopping-cart" },
    { "id": "gestao", "label": "Gestão" }
  ],
  "blocks": [
    {
      "id": "dfd",
      "label": "DFD",
      "categoryId": "compras",
      "description": "Geração automática do Documento de Formalização da Demanda",
      "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" },
      "routes": ["/compras/dfd"],
      "navigation": [
        { "path": "/compras", "label": "Compras" },
        { "path": "/compras/dfd", "label": "DFD" }
      ],
      "requiredRoles": ["compras_editor"],
      "order": 1
    },
    {
      "id": "form2json",
      "label": "Form2JSON",
      "categoryId": "gestao",
      "ui": { "type": "iframe", "url": "/api/automations/form2json/ui" },
      "routes": ["/gestao/form2json"],
      "hidden": true
    }
  ]
}
```

* Breadcrumbs configurados (`navigation`).
* Bloco `form2json` oculto (`hidden: true`).

---

## 🔮 Recomendações para Testes

* Usar catálogo mínimo para validar o **pipeline de build**.
* Usar catálogo com RBAC para validar **filtros no front**.
* Usar catálogo completo para validar **breadcrumbs e hidden**.

````

---

### `docs/30-catalog/boas-praticas.md`

```markdown
# Boas Práticas para Catálogo

Este documento reúne recomendações para a construção e manutenção dos catálogos do Portal AGEPAR.

---

## 🎯 Estrutura e Clareza

- **IDs consistentes**: usar slugs simples (`dfd`, `compras`, `contratos`).
- **Labels claros**: evitar abreviações obscuras; preferir nomes que usuários reconhecem.
- **Ordem explícita**: definir `order` sempre que possível para evitar ambiguidades.

---

## 🔐 Segurança

- **RBAC**: sempre definir `requiredRoles` quando a automação não é pública.
- **Hidden**: use `hidden: true` para recursos internos ou em desenvolvimento.
- O **BFF** deve reforçar RBAC, não apenas o front.

---

## 📐 Organização

- Agrupar blocos de forma lógica em categorias (`Compras`, `Gestão`, `Contratos`).
- Não sobrecarregar categorias: preferir mais categorias com menos blocos cada.
- Usar `description` para orientar o usuário sobre a finalidade do bloco.

---

## 🧭 Navegação

- Definir `navigation[]` para blocos complexos, ajudando em breadcrumbs.
- Usar `routes` claras e amigáveis (`/compras/dfd` em vez de `/x1/dfd`).
- Evitar duplicidade de rotas entre blocos.

---

## 🛠️ Evolução

- Sempre validar o catálogo contra o **JSON Schema** antes de commitar.
- Manter **consistência** entre `/catalog/dev` e `/catalog/prod`:
  - `dev`: pode incluir blocos experimentais.
  - `prod`: apenas blocos validados e liberados para usuários finais.
- Documentar novas categorias/blocos em `docs/`.

---

## ✅ Checklist de PR

- [ ] IDs consistentes (`[a-z0-9-]+`).
- [ ] Labels claros e revisados.
- [ ] Roles revisadas com a equipe de segurança.
- [ ] Rotas sem duplicidade.
- [ ] Catalogo validado contra `catalog.schema.json`.

---

## 🔮 Futuro

- Ferramenta CLI para gerar **templates de bloco**.
- Integração com **feature flags** (ativar/desativar blocos sem alterar JSON principal).
- Catálogo multilíngue (labels em mais de um idioma).
````

---
