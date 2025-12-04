---
id: index
title: "Automations – Padrão de Módulos"
sidebar_position: 0
---

Nesta seção está documentado o **padrão oficial de módulos de automação** do Portal AGEPAR.  
Cada automação é um módulo isolado em `apps/bff/app/automations/{slug}.py`, com UI HTML própria, exposta via **iframe** e integrada ao **catálogo** (`/catalog/dev`).

## Objetivos
- Explicar onde cada automação vive: `apps/bff/app/automations/{slug}.py` e `apps/bff/app/automations/templates/{slug}/*.html`.
- Documentar o contrato de endpoints de uma automação:
  - `GET /schema` (opcional, metadados para o front),
  - `GET /ui` (UI HTML para `<iframe>`),
  - `POST /submit` (criação de submission + `BackgroundTasks`),
  - `GET /submissions` e `GET /submissions/{id}` (consulta de submissions),
  - `POST /submissions/{id}/download` (geração/retorno de artefatos).
- Consolidar o **checklist** para criar uma nova automação de ponta a ponta (código, UI, integração com catálogo, RBAC, auditoria).
- Descrever como a UI de automations é exposta via **iframe** e como se integra com o **catálogo** e o **Host**.
- Reforçar padrões de **validação**, **persistência** (submissions/audits) e **tratamento de erros** comuns entre automations.

## Sumário Rápido
- `01-local-apps-bff-app-automations-slugpy` — onde o módulo mora, estrutura mínima de arquivos e visão geral do padrão.
- `02-get-schema-opcional-get-ui` — contrato sugerido para `GET /schema` e `GET /ui` (HTML embutível em iframe).
- `03-post-submit-backgroundtasks` — fluxo de `POST /submit`, validação com Pydantic e uso de `BackgroundTasks`.
- `04-get-submissions-get-submissions-id` — como listar e detalhar submissões por automação.
- `05-post-submissions-id-download` — padrão para gerar/retornar artefatos (PDF/DOCX/ZIP) a partir de uma submission.
- `06-checklist-para-criar-nova-automação` — passo a passo completo, de `slug.py` ao bloco no catálogo.
- `07-ui-via-iframe-e-integração-com-catálogo` — ligação entre UI HTML, catálogo (`/catalog/dev`) e renderização no Host.

## Visão geral do padrão de módulos

Uma automação típica:

1. **Módulo Python** em `apps/bff/app/automations/{slug}.py`:
   - define o `router` com prefixo `/api/automations/{slug}`;
   - implementa os endpoints padrão (`/schema`, `/ui`, `/submit`, `/submissions`, `/submissions/{id}`, `/submissions/{id}/download`);
   - usa os helpers de **submissions** e **auditoria** em `apps/bff/app/db.py`.

2. **Templates HTML** em `apps/bff/app/automations/templates/{slug}/`:
   - `ui.html` é a UI principal (sem build; HTML/JS/CSS simples);
   - opcionais como `history.html` podem complementar a experiência.

3. **Bloco no catálogo** (`catalog/catalog.dev.json`):
   - bloco com `ui: { "type": "iframe", "url": "/api/automations/{slug}/ui" }`;
   - categoria (`categoryId`), `requiredRoles`, `tags`, `order`, etc.

O Host lê o catálogo em `/catalog/dev` e renderiza a automação em um `<iframe>`, isolando o módulo, mas mantendo uma experiência unificada para o usuário.

## Contrato de endpoints

O contrato recomendado para toda automação inclui:

- `GET /api/automations/{slug}/schema` (opcional)
  - retorna schema/metadata para UI avançada, testes, ferramentas de suporte.
- `GET /api/automations/{slug}/ui`
  - retorna HTML pronto para ser usado em `<iframe>`;
  - faz checagens de autenticação/RBAC e exibe mensagens amigáveis em 401/403.
- `POST /api/automations/{slug}/submit`
  - recebe payload validado com Pydantic;
  - cria **submission** na tabela `submissions`;
  - dispara processamento via `BackgroundTasks` quando necessário.
- `GET /api/automations/{slug}/submissions`
  - lista submissões do usuário (ou com filtros específicos).
- `GET /api/automations/{slug}/submissions/{id}`
  - traz os detalhes de uma submission (status, payload, result, erros).
- `POST /api/automations/{slug}/submissions/{id}/download`
  - gera ou recupera o artefato (ex.: DOCX) referente à submission.

Esse padrão garante consistência entre automations, simplificando suporte, logs e UX no Host.

## Checklist resumido para nova automação

1. **Criar arquivos:**
   - `apps/bff/app/automations/{slug}.py`
   - `apps/bff/app/automations/templates/{slug}/ui.html`
2. **Implementar endpoints:**
   - pelo menos `GET /ui`, `POST /submit`, `GET /submissions`, `GET /submissions/{id}`, `POST /submissions/{id}/download`;
   - adicionar `GET /schema` se fizer sentido.
3. **Persistência e auditoria:**
   - usar os helpers de `submissions` e `automation_audits` de `db.py`.
4. **Validação e erros:**
   - modelos Pydantic claros;
   - erros com mensagens legíveis e códigos HTTP corretos.
5. **Catálogo:**
   - adicionar bloco em `catalog.dev.json` com `ui.url: "/api/automations/{slug}/ui"`;
   - configurar `categoryId`, `requiredRoles`, `hidden`, `order` conforme necessidade.
6. **Testes manuais:**
   - cURLs para todos os endpoints da automação;
   - verificar renderização via Host (iframe).

## Troubleshooting

- **Automação não aparece no Host**
  - Verificar se o bloco foi adicionado ao `catalog.dev.json` com o `categoryId` correto.
  - Conferir `hidden` e `requiredRoles` (RBAC) da categoria/bloco.
- **Iframe carrega erro 401/403**
  - Checar sessão do usuário (`/api/me`) e regras de RBAC no módulo.
- **`POST /submit` retornando 422**
  - Revisar modelo Pydantic da automação e payload enviado pela UI.
- **Download não funciona ou retorna 500**
  - Verificar implementação de `POST /submissions/{id}/download` e se a submission existe/pertence ao usuário.
- **Dúvida sobre onde começar**
  - Seguir a página **“Checklist para criar nova automação”** e usar as automations existentes (ex.: `dfd.py`, `controle.py`) como referência.

---

> _Criado em 2025-12-04_
