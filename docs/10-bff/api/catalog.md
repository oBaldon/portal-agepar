# API – Catálogo

O **catálogo** define a organização de **categorias** e **blocos** exibidos no frontend do Portal AGEPAR.  
Ele é consumido pelo **Host (React/Vite)** e determina a navegação e os módulos disponíveis para cada usuário.

---

## 📌 Endpoints

### 🔹 `GET /catalog/dev`
- **Descrição:** Retorna o catálogo de desenvolvimento.  
- **Uso:** Utilizado em ambiente local para testes.  
- **Status esperado:** `200 OK`  

### 🔹 `GET /catalog/prod`
- **Descrição:** Retorna o catálogo de produção.  
- **Uso:** Utilizado em ambiente produtivo, refletindo as automações homologadas.  
- **Status esperado:** `200 OK`  

---

## 📂 Estrutura do Catálogo

O catálogo é um JSON com duas seções principais:

- **categories[]** → agrupamentos de blocos.  
- **blocks[]** → automações ou páginas exibidas no frontend.  

### 🔹 Exemplo de Resposta
```json
{
  "categories": [
    {
      "id": "compras",
      "label": "Compras",
      "icon": "shopping-cart",
      "order": 1
    },
    {
      "id": "gestao",
      "label": "Gestão",
      "icon": "settings",
      "order": 2
    }
  ],
  "blocks": [
    {
      "id": "dfd",
      "label": "DFD",
      "categoryId": "compras",
      "description": "Documento de Formalização da Demanda",
      "ui": { "type": "iframe", "url": "/api/automations/dfd/ui" },
      "routes": ["/dfd"],
      "navigation": [{ "path": "/dfd", "label": "DFD" }],
      "requiredRoles": ["admin", "compras"],
      "order": 1
    },
    {
      "id": "form2json",
      "label": "Form2JSON",
      "categoryId": "gestao",
      "description": "Transforma formulários em JSON",
      "ui": { "type": "iframe", "url": "/api/automations/form2json/ui" },
      "routes": ["/form2json"],
      "navigation": [{ "path": "/form2json", "label": "Form2JSON" }],
      "order": 2
    }
  ]
}
````

---

## 🔑 Campos Importantes

### Categorias

* `id` → identificador único.
* `label` → nome exibido no frontend.
* `icon` → ícone (usado no menu).
* `order` → ordenação opcional.

### Blocos

* `id` → identificador único.
* `label` → nome do bloco.
* `categoryId` → vínculo com categoria.
* `description` → descrição opcional.
* `ui` → tipo e URL (ex.: `iframe`).
* `routes[]` → rotas de frontend associadas.
* `navigation[]` → entradas de menu.
* `requiredRoles[]` → roles permitidas (opcional).
* `order` → ordenação dentro da categoria.
* `hidden` → se `true`, não aparece no menu.

---

## 🧪 Testes de Exemplo

### Dev

```bash
curl -i http://localhost:8000/catalog/dev
```

### Prod

```bash
curl -i http://localhost:8000/catalog/prod
```

---

## 🚀 Próximos Passos

* [Automations API](automations.md)
* [Auth API](auth.md)

