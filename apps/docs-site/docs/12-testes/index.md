---
id: index
title: "Testes"
sidebar_position: 0
---

Esta seção descreve como testar o Portal AGEPAR hoje — e como preparar o terreno
para **testes automatizados mais robustos** no futuro — cobrindo:

- **cURLs de fumaça** e testes de API (pytest),
- o estado atual e o plano para **testes do Host** (Vitest),
- e **roteiros de testes manuais** (RBAC, navegação, proxy de docs).

## Objetivos
- Descrever os **testes de API** existentes e recomendados:
  - cURLs de fumaça (login, sessão, catálogo, automations),
  - esqueleto para testes automatizados com **pytest**.
- Explicar o estado atual dos **testes do Host**:
  - ausência de suíte automatizada hoje,
  - plano sugerido com **Vitest + Testing Library** e cobertura mínima.
- Documentar **testes manuais guiados**:
  - RBAC (roles, requiredRoles, superuser),
  - navegação por categorias/blocos no catálogo,
  - proxy de docs (`/devdocs`) em ambiente de desenvolvimento.
- Consolidar boas práticas para que **novos endpoints** e **novas telas** já nasçam “testáveis”.

## Sumário Rápido
- `01-testes-de-api-curl-pytest-e-exemplos` — cURLs de fumaça para BFF (login, sessão, catálogo, automations) e modelo sugerido de testes pytest.
- `02-testes-do-host-vitest-se-houver` — estado atual do Host (sem testes) e roteiro para introduzir Vitest + Testing Library.
- `03-testes-manuais-rbac-navegação-proxy-de-docs` — roteiros de testes manuais para RBAC, navegação e proxy de docs.
- `99-referencias.mdx` — arquivos do repositório relacionados a testes (cURLs, configurações, exemplos).

## Visão geral dos tipos de teste

Hoje o projeto combina:

- **Testes de API “de fumaça”** via cURL (descritivos no `README.md`),
- **Sugestões de pytest** focadas em:
  - modelos Pydantic (normalização/validação),
  - endpoints chave de automations (trilha feliz + erros),
- **Testes manuais guiados**, essenciais para:
  - validar RBAC (BFF + Host),
  - conferir navegação pelo catálogo,
  - garantir que o proxy de docs (`/devdocs`) está funcionando.

Testes automatizados do Host ainda **não existem**, mas a estrutura atual (`apps/host`) já está pronta para receber Vitest com pouco atrito.

## Testes de API (cURL/pytest)

- **cURLs de fumaça**:
  - login mock (`POST /api/auth/login`),
  - verificação de sessão (`GET /api/me`),
  - catálogo (`GET /catalog/dev`),
  - automations (`/api/automations/{slug}/...`).
- **pytest (recomendado)**:
  - testes de trilha feliz (`status 200`, payload/response esperados),
  - testes de erro (`400/403/404/409/422`) seguindo os padrões de erro & DX,
  - testes de modelos Pydantic (normalização, regras simples de negócio).

A ideia é que cada automação tenha um pequeno “kit” de testes de API, reaproveitando os mesmos cenários dos cURLs.

## Testes do Host (Vitest, quando adicionados)

Embora o Host ainda **não tenha Vitest configurado**, a seção detalha:

- como adicionar:
  - `vitest`, `@testing-library/react`, `@testing-library/user-event`,
- quais partes priorizar:
  - `HomeDashboard`,
  - `CategoryView` (filtros de RBAC, exibição de blocos),
  - componentes de erro (`Forbidden`, `NotFound`),
- como integrar os testes ao **CI**:
  - `npm test` rodando junto com `pytest` do BFF.

O objetivo é que, quando a suíte de testes do Host for criada, ela já siga o padrão descrito aqui.

## Testes manuais (RBAC, navegação, proxy de docs)

A seção de testes manuais propõe **roteiros repetíveis**, por exemplo:

- **RBAC**:
  - usuário sem roles → vê apenas blocos “públicos” da organização,
  - usuário com roles específicas → vê categorias/blocos corretos,
  - superusuário (`is_superuser`) → acesso ampliado onde aplicável.
- **Navegação**:
  - categorias do catálogo aparecem corretamente,
  - blocos aparecem na categoria certa e abrem as automations via iframe,
  - falhas no `/catalog/dev` resultam em mensagens claras, não em tela branca.
- **Proxy de docs** (`/devdocs`):
  - site de Dev Docs abre via Host,
  - navegação interna mantém o prefixo `/devdocs`,
  - falhas do container `docs` não derrubam o Host, apenas o proxy.

Esses roteiros funcionam como **checklist pós-deploy** e também como base para futuros testes automatizados de UI.

## Troubleshooting

- **cURLs do README não funcionam (timeout ou 5xx)**  
  - Verificar se BFF e Postgres estão no ar (Docker Compose) e se as portas coincidem com os exemplos.
- **Diferença entre o que o cURL mostra e o que o Host exibe**  
  - Checar CORS, cookies de sessão e se o navegador está enviando o cookie corretamente.
- **Dúvida sobre por onde começar a automatizar testes**  
  - Começar pela página de “Testes de API (cURL/pytest)” e pelos cURLs já existentes no `README.md`.
- **Host sem nenhum teste automatizado**  
  - Usar a página de “Testes do Host (Vitest, se houver)” como roteiro para o primeiro PR de testes.
- **RBAC parece correto no backend, mas errado na UI**  
  - Repetir os testes manuais da seção de RBAC, verificando `user.roles`, `requiredRoles` e `superuserOnly` no catálogo.

---

> _Criado em 2025-12-04_
