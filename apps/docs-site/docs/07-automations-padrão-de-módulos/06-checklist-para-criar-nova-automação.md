---
id: checklist-para-criar-nova-automação
title: "Checklist para criar nova automação"
sidebar_position: 6
---

## Checklist alinhado ao repositório atual

### Backend
- [ ] criar `apps/bff/app/automations/<slug>.py`
- [ ] definir router com prefixo em `/api/automations/<slug>`
- [ ] adicionar UI HTML simples quando o módulo for embutido via iframe
- [ ] decidir se haverá `/schema`
- [ ] implementar persistência em `submissions` quando fizer sentido
- [ ] registrar auditoria
- [ ] definir RBAC do módulo

### Registro no app
- [ ] importar o router em `apps/bff/app/main.py`
- [ ] incluir `APP.include_router(...)` com `Depends(require_password_changed)` quando aplicável

### Catálogo
- [ ] adicionar bloco em `catalog/catalog.dev.json`
- [ ] preencher `categoryId`, `ui.url`, `navigation`, `routes`, `requiredRoles`, `order`

### Host
- [ ] validar navegação
- [ ] validar RBAC de vitrine
- [ ] validar comportamento do iframe

### Docs
- [ ] documentar o módulo em `apps/docs-site/docs/07-automations-padrão-de-módulos/`
- [ ] atualizar README/guia se a automação alterar o contrato do portal

## Observação
No estado atual, nem toda automação segue exatamente o mesmo conjunto de
endpoints. Use o padrão recorrente como base, mas documente o contrato real do módulo.
