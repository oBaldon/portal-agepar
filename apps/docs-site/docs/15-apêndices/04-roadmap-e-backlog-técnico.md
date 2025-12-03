---
id: roadmap-e-backlog-técnico
title: "Roadmap e backlog técnico"
sidebar_position: 4
---

Esta página consolida o **roadmap técnico** e um **backlog organizado** do Portal AGEPAR, com foco em:

- evolução do produto (fluxo de compras público e automações paralelas),
- consolidação da plataforma (BFF, Host, catálogo e docs),
- qualidade técnica (testes, observabilidade, segurança e DX).

> Esta não é uma promessa de datas, e sim um **mapa de prioridades técnicas**.
> Serve como referência para organizar sprints, issues e PRs.

---

## 1) Eixos do roadmap

O roadmap é organizado em três eixos principais:

- **Produto (fluxo de compras público)**
  - DFD → PCA → ETP → TR → Cotação/Dispensa/Licitação → Contrato → Execução/Empenho/Pagamento.
  - Automações paralelas (ex.: cruzador de orçamento, controles gerenciais).

- **Plataforma (BFF + Host + Catálogo + Docs)**
  - Padrão de módulos em `/api/automations/{slug}`.
  - Catálogo em `/catalog/dev` como fonte única da UI.
  - Host React/Vite lendo o catálogo e renderizando blocos por `<iframe>`.
  - Portal de documentação em `/devdocs`.

- **Qualidade & Operação**
  - Observabilidade (logs, healthchecks, auditoria).
  - Testes (API, UI, manuais).
  - Convenções de commit/branch/versionamento.
  - DX (scripts de dev, mensagens de erro, exemplos).

Diagrama conceitual:

```mermaid
flowchart LR
  PROD["Produto<br/>(Fluxo de Compras)"] --> PLAT["Plataforma<br/>(BFF + Host + Docs)"]
  PLAT --> QUAL["Qualidade & Operação<br/>(Testes, Logs, CI)"]
  QUAL --> PROD

  %% Observação: os <br/> nos labels são apenas visuais; se der erro no Mermaid,
  %% trocar por strings simples: "Produto (Fluxo de Compras)", etc.
````

> Se o Mermaid acusar erro com `<br/>`, simplifique os labels para:
> `PROD["Produto (Fluxo de Compras)"]`, etc.

---

## 2) Roadmap macro (por horizonte)

Os itens abaixo agrupam as principais linhas de trabalho em **horizontes**:
curto, médio e longo prazo. Eles não são exaustivos, mas dão o “guia mental”
para priorizar backlog.

### 2.1) Curto prazo — H1 (próximos ciclos)

**Eixo Produto**

* [ ] Consolidar a automação **DFD**:

  * refinar templates DOCX/PDF,
  * melhorar mensagens de validação,
  * documentar exemplos de payload e de saída.
* [ ] Consolidar a automação **Férias**:

  * garantir cobertura dos principais cenários (1–3 períodos),
  * revisar regras de substituição e mensagens de erro,
  * documentar o fluxo ponta a ponta (submissão → zip).

**Eixo Plataforma**

* [ ] Padronizar automations atuais (`dfd`, `ferias`, `controle`, `controle_ferias`, `form2json`, `accounts`, `usuarios`, etc.) com o checklist de módulo:

  * `GET /schema` (quando fizer sentido),
  * `GET /ui`,
  * `POST /submit`,
  * `GET /submissions`,
  * `GET /submissions/{id}`,
  * `POST /submissions/{id}/download`.
* [ ] Consolidar o **catálogo dev**:

  * revisar `catalog/catalog.dev.json`,
  * conferir `categoryId`, `requiredRoles`, `order` e `hidden`,
  * garantir que todos os blocos relevantes já aparecem no Host.

**Eixo Qualidade & Operação**

* [ ] Finalizar a primeira rodada de documentação técnica:

  * preencher páginas chave que ainda estão em **stub** (Guias de Produto, parte das Automations, etc.),
  * consolidar Apêndices (tipos TS, Pydantic, catálogo, convenções de commit).
* [ ] Revisar logs e erros:

  * garantir uso consistente de níveis **INFO/ERROR**,
  * revisar mensagens 400/401/403/404/409/422 para clareza.

---

### 2.2) Médio prazo — H2 (evolução da plataforma)

**Eixo Produto**

* [ ] Começar automações do fluxo de compras além do DFD:

  * **PCA** (Planejamento de Compras Anual) – automação inicial.
  * **ETP** (Estudo Técnico Preliminar).
  * **TR** (Termo de Referência).
* [ ] Prototipar automação paralela **“cruzador de orçamento”**:

  * receber insumos de orçamento (planilha/JSON),
  * gerar saídas de apoio à decisão.

**Eixo Plataforma**

* [ ] Evoluir catálogo para suportar:

  * novos campos de **metadata** (ex.: flags de “experimental”, “somente dev”),
  * melhor organização de categorias (por fluxo, por área).
* [ ] Ampliar recursos do Host:

  * filtros de blocos por tags/categoria,
  * busca simples no catálogo,
  * exibição de “recentes” e/ou “favoritos” (baseado na navegação do usuário).

**Eixo Qualidade & Operação**

* [ ] Fortalecer testes:

  * suíte inicial de **pytest** cobrindo rotas principais do BFF,
  * exemplos de testes end-to-end com `curl` para automations-chave.
* [ ] Observabilidade:

  * revisar se o padrão de logs descrito em `10-observabilidade` está sendo seguido na prática,
  * considerar métricas adicionais para health (ex.: tempo de resposta).

---

### 2.3) Longo prazo — H3+ (escala e integração)

**Eixo Produto**

* [ ] Completar o fluxo de compras público:

  * automações para **Cotação/Dispensa/Licitação**, **Contrato** e **Execução/Empenho/Pagamento**.
* [ ] Refinar automações paralelas:

  * cruzador de orçamento,
  * dashboards gerenciais (consumindo `submissions` e `automation_audits`).

**Eixo Plataforma**

* [ ] Integração com **OIDC/SSO**:

  * hoje o Host já prevê `auth_mode: "oidc"` em `User`, mas o BFF ainda não expõe esse fluxo;
  * planejar e implementar autenticação com provedores institucionais.
* [ ] Evolução do engine de blocos:

  * suporte a blocos do tipo `"react"` (além de `"iframe"`),
  * estratégia de build e deploy para blocos mais ricos.

**Eixo Qualidade & Operação**

* [ ] Observabilidade avançada:

  * métricas formais (Prometheus, etc.),
  * correlação de logs por **request id**,
  * dashboards de saúde.
* [ ] Automação de release:

  * integração de versionamento semver (BFF/Host/Docs) com pipeline de CI/CD,
  * geração automática de changelog a partir de Conventional Commits.

---

## 3) Backlog técnico por área

Abaixo, um **backlog técnico condensado**, separado por área. Cada item pode virar
issue/PR com descrição detalhada.

### 3.1) Infra & Dev Experience

* [ ] Revisar e documentar scripts de dev (`infra/scripts/*.sh`):

  * `dev_up.sh`, `dev.sh`, scripts de smoke test de DB.
* [ ] Garantir dev UX previsível:

  * `docker-compose.dev.yml` subindo sempre: BFF, Host, Docs, Postgres,
  * documentação clara da ordem de start e dependências.
* [ ] Documentar claramente variáveis de ambiente:

  * `DATABASE_URL`, `SESSION_SECRET`, CORS, flags de mock, etc.

### 3.2) BFF (FastAPI & automations)

* [ ] Extrair padrões comuns de automations:

  * helper para criar `submissions` + `automation_audits` de forma uniforme,
  * padronizar estrutura de `result` e `error`.
* [ ] Melhorar mensagens de validação:

  * seguir o padrão de Pydantic v2 com `ConfigDict(populate_by_name=True, extra="ignore")`,
  * textos claros em pt-BR para CPF, e-mail, campos obrigatórios.
* [ ] Revisar endpoints de **accounts/usuarios**:

  * garantir RBAC adequado (apenas `admin`/superuser),
  * documentar fluxos de criação/edição/bloqueio de usuário.

### 3.3) Host (React/Vite/TS)

* [ ] Evoluir UI do catálogo:

  * filtros por categoria/role/tag,
  * cards mais ricos (descrição, badges, ícones consistentes).
* [ ] Endurecer comunicação via `iframe`:

  * implementar/validar origem (`origin`) no canal de `postMessage`,
  * documentar contrato de mensagens entre Host e blocos.
* [ ] Melhorar experiência de autenticação:

  * telas de erro de sessão expirada,
  * fluxo de **force change password** (já existente) com feedback mais claro.

### 3.4) Catálogo

* [ ] Completar/ajustar blocos existentes em `catalog/catalog.dev.json`:

  * garantir que todos os slugs de automations tenham um bloco correspondente,
  * revisar `requiredRoles` com apoio das áreas de negócio.
* [ ] Preparar catálogo para ambientes futuros:

  * planejar como diferenciar `catalog.dev`, `catalog.homolog`, `catalog.prod`,
  * alinhar com o JSON Schema documentado no apêndice.

### 3.5) Documentação (Docusaurus)

* [ ] Preencher **Guias de Produto** (seção 14):

  * detalhar fluxo DFD → PCA → ETP → TR → Cotação/Dispensa/Licitação → Contrato → Execução/Empenho/Pagamento,
  * mapear cada etapa para blocos/automations.
* [ ] Completar páginas de automations de negócio:

  * DFD, Férias, Controle, etc., cada uma com:

    * contexto de negócio,
    * exemplos de payload (JSON),
    * exemplos de utilização (cURL/TS).
* [ ] Manter Apêndices atualizados:

  * quando tipos TS ou modelos Pydantic mudarem, atualizar o apêndice correspondente,
  * quando o catálogo ganhar campos novos, atualizar o JSON Schema.

---

## 4) Como usar e manter este roadmap

Sugestão de processo para manter este documento vivo:

1. **Para cada PR relevante**, verificar se:

   * introduz nova automação, ou
   * muda contrato de API, ou
   * altera fluxo de produto.
2. Se sim, atualizar:

   * a seção de roadmap (se mudar prioridade ou horizonte),
   * o backlog por área (marcar itens como concluídos/adicionados).
3. Periodicamente (por exemplo, a cada trimestre):

   * revisar este apêndice junto com o time,
   * mover itens entre horizontes (curto ↔ médio ↔ longo),
   * remover itens que não fazem mais sentido.

> A ideia é que este arquivo funcione como **referência de alto nível**,
> enquanto o detalhamento de tarefas permanece em issues, PRs e nos demais docs.

---

> _Criado em 2025-12-03_