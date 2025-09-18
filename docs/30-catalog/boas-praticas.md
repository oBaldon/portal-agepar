# Boas Práticas para Catálogo

Este documento reúne recomendações para a construção e manutenção dos catálogos no Portal AGEPAR.  
O objetivo é garantir **consistência**, **segurança** e **usabilidade** na forma como categorias e blocos são definidos.

---

## 🎯 Estrutura e Clareza

- **IDs consistentes**: use slugs simples, em minúsculas e sem espaços (`dfd`, `compras`, `contratos`).
- **Labels claros**: evite siglas pouco conhecidas. Prefira nomes que façam sentido para qualquer servidor público.
- **Ordem explícita**: sempre que possível, defina `order` em categorias e blocos para evitar ambiguidades de exibição.

---

## 🔐 Segurança

- **RBAC obrigatório**: defina `requiredRoles` para qualquer automação que não seja pública.  
- **Hidden**: use `hidden: true` para esconder recursos internos, experimentais ou não liberados.  
- **Defesa em profundidade**: o BFF deve reforçar o RBAC. O catálogo no front **não é confiável sozinho**.

---

## 📐 Organização

- Agrupe blocos em categorias com significado funcional (`Compras`, `Gestão`, `Contratos`).  
- Prefira várias categorias menores a uma categoria superlotada.  
- Sempre use `description` para orientar usuários sobre o propósito do bloco.  
- Utilize ícones (`icon`) apenas quando ajudarem na **identificação rápida**.

---

## 🧭 Navegação

- Configure `navigation[]` nos blocos que precisam de breadcrumbs.  
- Use `routes` amigáveis e estáveis (`/compras/dfd` em vez de `/c1/b1`).  
- Nunca repita rotas entre blocos. O Host deve ser capaz de montar rotas únicas.  

---

## 🛠️ Evolução

- Valide o catálogo contra o **JSON Schema** (`docs/30-catalog/schema-de-categoria-e-bloco.md`) antes de subir para `main`.  
- Mantenha consistência entre ambientes:
  - `/catalog/dev`: pode conter blocos experimentais ou em homologação.
  - `/catalog/prod`: deve ter apenas blocos aprovados para produção.  
- Documente **cada nova automação** em `docs/10-bff/automations/`.

---

## ✅ Checklist de PR

- [ ] IDs de categoria e bloco seguem o padrão slug (`[a-z0-9-]+`).  
- [ ] Labels revisados e compreensíveis.  
- [ ] Roles aprovadas com equipe de segurança.  
- [ ] Nenhuma duplicidade em rotas.  
- [ ] Catálogo validado contra JSON Schema.  
- [ ] Descrição e ícone adicionados (quando aplicável).  

---

## 🔮 Futuro

- Criar CLI para gerar **templates de blocos** automaticamente.  
- Implementar **feature flags** (ativar/desativar blocos sem alterar JSON principal).  
- Suporte a **multilíngue** em labels e descrições.  
- Ferramenta de **lint** dedicada para catálogo no pipeline CI/CD.  
