---
id: checklist-de-validacao-para-mudancas-futuras
title: "Checklist de validação para mudanças futuras"
sidebar_position: 6
---
Este checklist serve como smoke mínimo para mudanças futuras no Plataforma AGEPAR.

A ideia não é substituir testes automatizados, e sim criar um roteiro repetível para validar que a stack continua íntegra após alterações em backend, host, catálogo, docs ou automações.

## 1) Subir a stack da forma recomendada

Na raiz do projeto:

```bash
cp .env.example .env
./infra/scripts/dev.sh up
```

Resultado esperado:

- Host disponível em `http://localhost:5173`
- BFF disponível em `http://localhost:8000`
- Docs disponíveis em `http://localhost:5173/devdocs/`
- OpenAPI em `http://localhost:8000/api/docs`

## 2) Conferir o modo efetivo do backend

```bash
curl -s http://localhost:8000/version | jq .
```

Resultado esperado:

- resposta HTTP 200;
- informações coerentes com o modo de autenticação em uso (`local`, `mock` ou legado habilitado por ambiente).

## 3) Validar catálogo e sessão

### 3.1. Sessão do usuário

```bash
curl -i http://localhost:8000/api/me
```

Resultado esperado:

- sem login, retorno 401 ou equivalente coerente com a política atual;
- após autenticação válida, retorno 200 com `roles`, `auth_mode` e, quando aplicável, `is_superuser`.

### 3.2. Catálogo

```bash
curl -s http://localhost:8000/catalog/dev | jq .
```

Resultado esperado:

- retorno 200;
- categorias e blocos coerentes com o catálogo atual;
- metadados sincronizados com `AUTOMATION_META`, quando a automação os publica.

## 4) Validar Host e proxy de docs

### 4.1. Host

Abrir no navegador:

- `http://localhost:5173`

Resultado esperado:

- login ou tela inicial carregando sem erro de proxy;
- navegação principal sem quebrar o catálogo.

### 4.2. Docs via Host

Abrir no navegador:

- `http://localhost:5173/devdocs/`

Resultado esperado:

- docs renderizadas com assets corretos;
- sem 404 em arquivos estáticos;
- sem erro de `baseUrl`.

## 5) Validar pelo menos uma automação de negócio

Abrir no Host uma automação já conhecida, por exemplo:

- `dfd`
- `ferias`

Resultado esperado:

- UI carregando no iframe;
- chamadas ao BFF funcionando;
- sem erro de proxy, RBAC ou sessão.

## 6) Validar o fluxo de suporte

### 6.1. Abertura de chamado padrão

Abrir:

- `GET /api/automations/support/padrao.html`

Enviar um chamado simples.

Resultado esperado:

- submissão criada em `submissions`;
- auditoria registrada;
- `payload.ticket_type = "padrao"` para novos registros.

### 6.2. Abertura de chamado técnico

Abrir:

- `GET /api/automations/support/ui`
- ou `GET /api/automations/support/ui.html`

Enviar um chamado técnico.

Resultado esperado:

- submissão criada em `submissions`;
- `payload.ticket_type = "tecnico"` para novos registros;
- campos técnicos persistidos quando informados.

## 7) Validar leitura administrativa de suporte

Autenticar com perfil apto e abrir:

- `whoisonline`
- botão **Chamados de suporte**

Resultado esperado:

- navegação disponível somente no contexto esperado;
- listagem administrativa carregando;
- filtros funcionando;
- detalhe abrindo corretamente;
- downloads JSON/PDF operacionais.

## 8) Validar um cenário de RBAC

Escolha pelo menos um bloco restrito do catálogo.

Resultado esperado:

- usuário sem role não vê o bloco no Host;
- acesso forçado à rota protegida recebe 403 no BFF;
- superuser enxerga o que precisa enxergar.

## 9) Validar documentação após a mudança

Sempre confirmar se a mudança exigia atualização de:

- `README.md`
- `apps/docs-site/docs/dev-guide.md`
- inventário de automações
- inventário de tabelas e domínios
- esta própria página de checklist, se o fluxo validado mudou

## 10) Critério mínimo de aceite

Antes de considerar a mudança encerrada, confirme:

- bootstrap reproduzível;
- Host, BFF e docs acessíveis;
- catálogo íntegro;
- ao menos uma automação funcional;
- fluxo de suporte íntegro;
- RBAC básico preservado;
- documentação alinhada ao comportamento real.
